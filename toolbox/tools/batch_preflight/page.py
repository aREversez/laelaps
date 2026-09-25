"""The batch preflight tool's page: same idea as ``batch_alignment_check``
(add files/folders, set shared options once, run one check per file, one
row per file in a queue-and-progress table) but for
``language_tools.readers.docx_preflight.check()`` instead of
``align_report``/``align_report.summarize()`` -- see that module's
docstring for what preflight actually checks (layout confidence, merged
cells, empty tables, language-direction sanity) and why. Closes the
【批量预检】DESIGN.md 15.2 backlog item.

Structure is cloned from ``batch_alignment_check/page.py`` (itself cloned
from ``batch_convert/page.py`` -- see that docstring for the shared
QThread-worker/one-table-as-queue-and-progress/completed-rows-dropped-on-
add pattern) with the differences preflight's narrower scope calls for:

- DOCX only, not every bilingual format: preflight's checks (layout
  confidence, merged cells, empty tables) are specific to auto-detecting
  among the three docx layouts (``readers/docx.py``) and don't apply to
  xlsx/csv at all. The file picker filter and folder-walk both only
  accept .docx; a non-.docx slipping in via 添加文件夹 (shouldn't happen
  given the filter, but matches batch_alignment_check's own defensive
  backstop for the analogous case) is marked as a per-row error rather
  than silently skipped or crashing the batch.
- No 排版方式 combo: preflight's whole point is reporting confidence for
  *all three* layouts side by side (so a low/ambiguous score is exactly
  the signal worth surfacing), not reading the file with one layout
  already chosen -- there's nothing here for a layout override to do.
- Status coloring is two-way, not three: green = 未发现问题, red = either
  N 项问题 found or a genuine per-file failure (bad zip, no tables at
  all) -- both are "needs a look" the same way batch_alignment_check's
  GAP/QA-flagged and 检查失败 both do, so they share plain red rather
  than getting a third color; the message text itself (预检失败： prefix
  vs 项问题) is what tells them apart, same as that page's own reasoning
  for keeping to the design tokens' "semantic status only" red.
- Each row's 结果 cell carries the full issue list as a tooltip
  (``setToolTip()``) -- the cell itself only has room for a one-line
  summary (layout + issue count), and a reviewer scanning a batch wants
  the detail on hover for the rows that need it, not a wall of text for
  every row.
"""
import csv
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from language_tools.readers import docx_preflight
from toolbox import settings
from toolbox.widgets import LANG_TOOLTIP, LOG_COLORS, compact_combo, labeled_field, lang_combo_code
from toolbox.widgets import make_lang_combo, page_shell, set_lang_combo_code
from toolbox.widgets import section as _section
from toolbox.workers import wait_for_running

_DOCX_FILTER = 'DOCX files (*.docx)'
_CSV_FILTER = 'CSV (*.csv)'

_STATUS_PENDING = '等待中'
_STATUS_RUNNING = '检查中…'

_SETTINGS_PREFIX = 'batch_preflight/'


class BatchPreflightWorker(QThread):
    """Runs ``docx_preflight.check()`` once per file, off the UI thread.
    Same keep-going-past-a-single-file's-error contract as
    ``BatchConvertWorker``/``BatchAlignWorker``; ``file_done`` carries the
    full result dict alongside the status text so the page can tally
    "needs review" and build the CSV export without re-parsing the
    message.
    """
    file_done = Signal(int, bool, str, object)  # row, ran_ok, status text, result-or-None
    all_done = Signal(int, int, int)            # checked, failed, needs-review

    def __init__(self, input_paths, shared, parent=None):
        super().__init__(parent)
        self._input_paths = input_paths
        self._shared = shared  # src_lang, tgt_lang

    def run(self):
        checked = failed = needs_review = 0
        for row, input_path in enumerate(self._input_paths):
            ran_ok, message, result = _check_one(input_path, self._shared)
            if ran_ok:
                checked += 1
                if result['issues']:
                    needs_review += 1
            else:
                failed += 1
            self.file_done.emit(row, ran_ok, message, result)
        self.all_done.emit(checked, failed, needs_review)


def _check_one(input_path, shared):
    """One file's full check: returns the ``(ok, message, result)`` triple
    ``BatchPreflightWorker`` emits per row. Module-level (not a worker
    method) so tests can exercise the message wording directly."""
    if os.path.splitext(input_path)[1].lower() != '.docx':
        return False, '预检仅支持 .docx，已跳过', None
    try:
        result = docx_preflight.check(input_path, shared['src_lang'], shared['tgt_lang'])
    except Exception as e:  # noqa: BLE001 -- surfaced per-row, doesn't stop the batch
        return False, '预检失败：%s' % e, None

    if result['issues']:
        message = '版式 %s(%.2f)，%d 项问题' % (
            result['best_layout'], result['best_score'], len(result['issues']))
    else:
        message = '版式 %s(%.2f)，未发现问题' % (result['best_layout'], result['best_score'])
    return True, message, result


class BatchPreflightPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = []     # str, in the same order as the table's rows
        self._row_done = []  # bool per row -- True once it has a terminal (checked/error) result
        self._results = []   # docx_preflight.check() dict per row, or None (pending/failed)
        self._worker = None
        self._ran_count = 0  # rows with a terminal "check ran" result, drives 导出汇总 CSV
        self._last_dir = ''  # overwritten by restore_settings() when wired through MainWindow
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer, _, _ = page_shell(
            '批量预检',
            '批量转换前先体检：版式置信度、合并单元格、空表格、语言方向是否对',
            spacing=18,
        )

        # --- file list (queue + progress display in one table, same as
        # batch_alignment_check/batch_convert) ---
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)

        btn_row = QHBoxLayout()
        self.add_files_btn = QPushButton('添加文件…')
        self.add_files_btn.clicked.connect(self._add_files)
        self.add_folder_btn = QPushButton('添加文件夹…')
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_btn = QPushButton('移除选中')
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton('清空')
        self.clear_btn.clicked.connect(self._clear_all)
        for b in (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        list_layout.addLayout(btn_row)

        self.count_label = QLabel('共 0 个文件')
        self.count_label.setStyleSheet('color: #6B7280;')
        list_layout.addWidget(self.count_label)

        self.file_table = QTableWidget(0, 2)
        self.file_table.setHorizontalHeaderLabels(['文件', '结果'])
        self.file_table.verticalHeader().setVisible(False)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_table.setShowGrid(False)
        self.file_table.setAlternatingRowColors(True)
        list_layout.addWidget(self.file_table, 1)

        outer.addWidget(_section('待检查文件（仅 .docx）', list_widget), 1)

        # --- language, for the direction-sanity check only (the other
        # three checks don't need a language pair at all) ---
        opts_widget = QWidget()
        opts_layout = QHBoxLayout(opts_widget)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.setSpacing(28)

        self.src_edit = make_lang_combo('en-US')
        self.tgt_edit = make_lang_combo('zh-CN')
        self.src_edit.setToolTip(LANG_TOOLTIP)
        self.tgt_edit.setToolTip(LANG_TOOLTIP)
        for combo in (self.src_edit, self.tgt_edit):
            compact_combo(combo)

        opts_layout.addLayout(labeled_field('原文语言', self.src_edit))
        opts_layout.addLayout(labeled_field('译文语言', self.tgt_edit))
        opts_layout.addStretch(1)
        outer.addWidget(_section('语言（应用到本批所有文件，用于语言方向核对）', opts_widget))

        action_row = QHBoxLayout()
        self.start_btn = QPushButton('开始批量预检')
        self.start_btn.setObjectName('primaryButton')
        self.start_btn.clicked.connect(self._start_batch)
        self.export_btn = QPushButton('导出汇总 CSV…')
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('导出每个文件的版式置信度/合并单元格/空表格/问题数汇总（含失败的），不受显示影响')
        self.export_btn.clicked.connect(self._start_export)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('color: #4B5262;')
        outer.addWidget(self.summary_label)

    # ------------------------------------------------------------ file list
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件', self._last_dir, _DOCX_FILTER)
        if not paths:
            return
        self._clear_completed_rows()
        for path in paths:
            self._append_path(path)
        self._last_dir = os.path.dirname(paths[-1])
        self._refresh_count()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹', self._last_dir)
        if not folder:
            return
        self._clear_completed_rows()
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() == '.docx':
                    self._append_path(os.path.join(root, name))
        self._last_dir = folder
        self._refresh_count()

    def _clear_completed_rows(self):
        """Drop every row that already has a terminal result from a
        previous run, keeping only rows still 等待中 -- same as
        batch_alignment_check/batch_convert's helper of the same name.
        Also re-tallies the export-enabled state.
        """
        for row in reversed(range(len(self._row_done))):
            if self._row_done[row]:
                self.file_table.removeRow(row)
                del self._paths[row]
                del self._row_done[row]
                del self._results[row]
                self._ran_count -= 1
        self.export_btn.setEnabled(self._ran_count > 0)
        self._refresh_count()

    def _append_path(self, path):
        if path in self._paths:
            return  # already queued -- adding the same file twice would double-check it
        self._paths.append(path)
        self._row_done.append(False)
        self._results.append(None)
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)
        name_item = QTableWidgetItem(os.path.basename(path))
        name_item.setToolTip(path)
        self.file_table.setItem(row, 0, name_item)
        self._set_row_status(row, _STATUS_PENDING, 'info')

    def _remove_selected(self):
        rows = sorted({idx.row() for idx in self.file_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.file_table.removeRow(row)
            if self._row_done[row]:
                self._ran_count -= 1
            del self._paths[row]
            del self._row_done[row]
            del self._results[row]
        self.export_btn.setEnabled(self._ran_count > 0)
        self._refresh_count()

    def _clear_all(self):
        self.file_table.setRowCount(0)
        self._paths.clear()
        self._row_done.clear()
        self._results.clear()
        self._ran_count = 0
        self.export_btn.setEnabled(False)
        self._refresh_count()

    def _refresh_count(self):
        self.count_label.setText('共 %d 个文件' % len(self._paths))

    def _set_row_status(self, row, text, kind, tooltip=None):
        item = QTableWidgetItem(text)
        item.setForeground(QColor(LOG_COLORS.get(kind, LOG_COLORS['info'])))
        if tooltip:
            item.setToolTip(tooltip)
        self.file_table.setItem(row, 1, item)

    # ------------------------------------------------------------ lifecycle
    def cleanup(self):
        """Called by ``main_window.py`` on a real window close. See
        ``toolbox.workers.wait_for_running()`` for why a page with a
        worker needs this.
        """
        wait_for_running(self._worker)

    # ------------------------------------------------------------ settings
    def restore_settings(self):
        set_lang_combo_code(self.src_edit, settings.get_str(_SETTINGS_PREFIX + 'srcLang', 'en-US'))
        set_lang_combo_code(self.tgt_edit, settings.get_str(_SETTINGS_PREFIX + 'tgtLang', 'zh-CN'))
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        settings.set_value(_SETTINGS_PREFIX + 'srcLang', lang_combo_code(self.src_edit))
        settings.set_value(_SETTINGS_PREFIX + 'tgtLang', lang_combo_code(self.tgt_edit))
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)

    # ------------------------------------------------------------ actions
    def _validate(self):
        """Returns an error string, or None if the form is valid."""
        if not self._paths:
            return '请先添加要预检的文件'
        return None

    def _set_controls_enabled(self, enabled):
        for w in (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn,
                  self.start_btn, self.export_btn, self.src_edit, self.tgt_edit):
            w.setEnabled(enabled)

    def _start_batch(self):
        self._ran_count = 0
        self._results = [None] * len(self._paths)
        self.export_btn.setEnabled(False)
        for row in range(len(self._row_done)):
            self._row_done[row] = False

        error = self._validate()
        if error:
            self.summary_label.setText(error)
            self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS['error'])
            return

        shared = dict(
            src_lang=lang_combo_code(self.src_edit) or None,
            tgt_lang=lang_combo_code(self.tgt_edit) or None,
        )

        for row in range(self.file_table.rowCount()):
            self._set_row_status(row, _STATUS_RUNNING, 'info')
        self.summary_label.setText('正在预检 %d 个文件…' % len(self._paths))
        self.summary_label.setStyleSheet('color: #4B5262;')
        self._set_controls_enabled(False)

        self._worker = BatchPreflightWorker(list(self._paths), shared, parent=self)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_file_done(self, row, ran_ok, message, result):
        self._row_done[row] = True
        tooltip = '\n'.join(result['issues']) if (ran_ok and result and result['issues']) else None
        if ran_ok:
            self._ran_count += 1
            self._results[row] = result
            self._set_row_status(row, message, 'error' if result['issues'] else 'success', tooltip)
        else:
            self._set_row_status(row, message, 'error')
        self.export_btn.setEnabled(self._ran_count > 0)

    def _on_all_done(self, checked, failed, needs_review):
        self._set_controls_enabled(True)
        if failed == 0 and needs_review == 0:
            text = '全部完成：%d 个文件全部通过预检，没有发现问题' % checked
            kind = 'success'
        elif failed == 0:
            text = ('全部完成：%d 个文件已预检，其中 %d 个需要看一眼（详见上面各行，鼠标悬停看具体问题）'
                    % (checked, needs_review))
            kind = 'info'
        else:
            text = '完成：%d 个已预检，%d 个失败（详情见上面各行的结果）' % (checked, failed)
            kind = 'error'
        self.summary_label.setText(text)
        self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS[kind])

    # ------------------------------------------------------------- export
    def _start_export(self):
        if self._ran_count <= 0:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '导出汇总 CSV', os.path.join(self._last_dir, '批量预检汇总'), _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        self._last_dir = os.path.dirname(path)
        try:
            self._write_summary_csv(path)
        except OSError as e:
            self.summary_label.setText('导出失败：%s' % e)
            self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS['error'])
            return
        self.summary_label.setText('汇总 CSV 已导出到 %s' % path)
        self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS['success'])

    def _write_summary_csv(self, path):
        """One row per file -- the table's own 结果 column plus the
        structured counts behind it (not just the one-line message),
        machine-readable. utf-8-sig for the same reason
        ``writers/csv_writer`` uses it (Excel needs the BOM to open CJK
        content correctly)."""
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'best_layout', 'best_score', 'layout_ambiguous',
                              'merged_cell_count', 'empty_table_count',
                              'direction_issue_count', 'status'])
            for row, input_path in enumerate(self._paths):
                r = self._results[row]
                status_item = self.file_table.item(row, 1)
                status = status_item.text() if status_item else ''
                if r is None:
                    writer.writerow([input_path, '', '', '', '', '', '', status or '未检查'])
                else:
                    writer.writerow([
                        input_path, r['best_layout'], r['best_score'], r['layout_ambiguous'],
                        r['merged_cell_count'], r['empty_table_count'],
                        len(r['direction_issues']), status,
                    ])
