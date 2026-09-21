"""The batch alignment-check tool's page: same idea as ``alignment_check``
(run ``language_tools.align_report`` and report diagnostics without
writing any corpus output) but applied to a whole list of files instead of
one -- add files and/or whole folders, set the language pair/layout once,
and it calls ``align_report.run()`` + ``summarize()`` once per file, the
same as if you'd run the single-file tool that many times by hand. This
closes the 【对齐检查】 half of DESIGN.md section 15's 批量处理 backlog
item (the 【语料转换】 half became ``batch_convert``).

Structure is deliberately cloned from ``batch_convert/page.py`` (its
closest sibling -- QThread worker with per-file ``file_done``/final
``all_done`` signals, one ``QTableWidget`` serving as both queue and
progress display, completed rows dropped when new files are added,
``_last_dir``-shared browse starts, settings round-trip) with three
differences worth calling out:

- Only bilingual formats are offered (.tmx/.sdltm have no alignment to
  diagnose -- ``align_report.run()`` raises ``ValueError`` on them and the
  row is simply marked as an error if one slips in via 添加文件夹).
  Because every input needs a language pair, validation requires
  src/tgt up front, unlike batch_convert where a corpus-only batch doesn't.
- One file finishing successfully but *finding problems* (GAP/QA-flagged
  rows) is the tool working as intended, not a failure -- so the status
  column colors split three ways rather than batch_convert's two:
  green = 全部对齐正常, red = 需要人工看一眼 (GAP/QA 标记数), and gray
  info only for 等待中/进行中. A truly failed check (unreadable file) is
  red too, with a 检查失败： prefix so the two reds are distinguishable.
  This matches the danger color's "semantic status only" role in
  style.qss's design tokens -- the whole point of scanning a batch is to
  spot which documents need attention without reading every row.
- The useful take-away from a batch of summaries is a checklist, so
  导出汇总 CSV writes one row per file (path/units/gaps/QA-flagged/
  status), the same shape the table shows. Synchronous, like qa_check's
  report export -- tens of rows, nothing a worker thread buys.
"""
import csv
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from language_tools import align_report
from toolbox import settings
from toolbox.widgets import LANG_TOOLTIP, LOG_COLORS, compact_combo, labeled_field, lang_combo_code
from toolbox.widgets import make_lang_combo, make_layout_combo, set_lang_combo_code
from toolbox.widgets import section as _section

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}
_BILINGUAL_FILTER = 'Bilingual source files (*.docx *.xlsx *.xlsm *.csv *.tsv)'
_CSV_FILTER = 'CSV (*.csv)'

_STATUS_PENDING = '等待中'
_STATUS_RUNNING = '检查中…'

_SETTINGS_PREFIX = 'batch_alignment_check/'


class BatchAlignWorker(QThread):
    """Runs ``align_report.run()`` + ``summarize()`` once per file, off
    the UI thread. Same keep-going-past-a-single-file's-error contract as
    ``batch_convert.BatchConvertWorker`` (see that class's docstring);
    ``file_done`` carries the per-file summary counts alongside the
    status text so the page can tally "needs review" without re-parsing
    the message.
    """
    file_done = Signal(int, bool, str, object)  # row, ran_ok, status text, summary-or-None
    all_done = Signal(int, int, int)            # checked, failed, needs-review

    def __init__(self, input_paths, shared, parent=None):
        super().__init__(parent)
        self._input_paths = input_paths
        self._shared = shared  # src_lang, tgt_lang, layout

    def run(self):
        checked = failed = needs_review = 0
        for row, input_path in enumerate(self._input_paths):
            ran_ok, message, summary = _check_one(input_path, self._shared)
            if ran_ok:
                checked += 1
                if summary['gap_count'] or summary['qa_flagged'] or not summary['total']:
                    needs_review += 1
            else:
                failed += 1
            self.file_done.emit(row, ran_ok, message, summary)
        self.all_done.emit(checked, failed, needs_review)


def _check_one(input_path, shared):
    """One file's full check: returns the ``(ok, message, summary)``
    triple ``BatchAlignWorker`` emits per row. Module-level (not a worker
    method) so tests can exercise the message wording directly."""
    reader_opts = {}
    if input_path.lower().endswith('.docx') and shared['layout'] != 'auto':
        reader_opts['layout'] = shared['layout']
    try:
        units = align_report.run(
            input_path, shared['src_lang'], shared['tgt_lang'], reader_opts=reader_opts)
    except Exception as e:  # noqa: BLE001 -- surfaced per-row, doesn't stop the batch
        return False, '检查失败：%s' % e, None

    s = align_report.summarize(units)
    if s['total'] and not s['gap_count'] and not s['qa_flagged']:
        return True, '共 %d 条，全部对齐正常' % s['total'], s
    message = '需检查：共 %d 条，%d GAP，%d QA 标记' % (
        s['total'], s['gap_count'], s['qa_flagged'])
    if not s['total']:
        message = '需检查：读出 0 条（文件是空的？）'
    return True, message, s


class BatchAlignmentCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = []     # str, in the same order as the table's rows
        self._row_done = []  # bool per row -- True once it has a terminal (checked/error) result
        self._summaries = [] # align_report.summarize() dict per row, or None (pending/failed)
        self._worker = None
        self._ran_count = 0  # rows with a terminal "check ran" result, drives 导出汇总 CSV
        self._last_dir = ''  # overwritten by restore_settings() when wired through MainWindow
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('批量对齐检查')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('一次性检查多个双语文档的句子对齐结果，不生成任何文件')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        # --- file list (queue + progress display in one table, same as
        # batch_convert's 待转换文件 section) ---
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

        outer.addWidget(_section('待检查文件', list_widget), 1)

        # --- language + docx layout, all inline in one row (same section
        # as alignment_check/batch_convert) ---
        opts_widget = QWidget()
        opts_layout = QHBoxLayout(opts_widget)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.setSpacing(28)

        self.src_edit = make_lang_combo('en-US')
        self.tgt_edit = make_lang_combo('zh-CN')
        self.src_edit.setToolTip(LANG_TOOLTIP)
        self.tgt_edit.setToolTip(LANG_TOOLTIP)
        self.layout_combo = make_layout_combo()
        self.layout_combo.setToolTip('仅 .docx 需要关心')
        for combo in (self.src_edit, self.tgt_edit, self.layout_combo):
            compact_combo(combo)

        opts_layout.addLayout(labeled_field('原文语言', self.src_edit))
        opts_layout.addLayout(labeled_field('译文语言', self.tgt_edit))
        opts_layout.addLayout(labeled_field('文档排版方式', self.layout_combo))
        opts_layout.addStretch(1)
        outer.addWidget(_section('语言与排版方式（应用到本批所有文件）', opts_widget))

        action_row = QHBoxLayout()
        self.start_btn = QPushButton('开始批量检查')
        self.start_btn.setObjectName('primaryButton')
        self.start_btn.clicked.connect(self._start_batch)
        self.export_btn = QPushButton('导出汇总 CSV…')
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('导出每个文件的条数/GAP/QA 标记数汇总（含失败的），不受显示影响')
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
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件', self._last_dir, _BILINGUAL_FILTER)
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
                if os.path.splitext(name)[1].lower() in _BILINGUAL_EXTS:
                    self._append_path(os.path.join(root, name))
        self._last_dir = folder
        self._refresh_count()

    def _clear_completed_rows(self):
        """Drop every row that already has a terminal result from a
        previous run, keeping only rows still 等待中 -- same as
        batch_convert's helper of the same name (a freshly-added file and
        a row still showing last run's "共 12 条…" look the same without
        this). Also re-tallies the export-enabled state.
        """
        for row in reversed(range(len(self._row_done))):
            if self._row_done[row]:
                self.file_table.removeRow(row)
                del self._paths[row]
                del self._row_done[row]
                del self._summaries[row]
                self._ran_count -= 1
        self.export_btn.setEnabled(self._ran_count > 0)
        self._refresh_count()

    def _append_path(self, path):
        if path in self._paths:
            return  # already queued -- adding the same file twice would double-check it
        self._paths.append(path)
        self._row_done.append(False)
        self._summaries.append(None)
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
            del self._summaries[row]
        self.export_btn.setEnabled(self._ran_count > 0)
        self._refresh_count()

    def _clear_all(self):
        self.file_table.setRowCount(0)
        self._paths.clear()
        self._row_done.clear()
        self._summaries.clear()
        self._ran_count = 0
        self.export_btn.setEnabled(False)
        self._refresh_count()

    def _refresh_count(self):
        self.count_label.setText('共 %d 个文件' % len(self._paths))

    def _set_row_status(self, row, text, kind):
        item = QTableWidgetItem(text)
        item.setForeground(QColor(LOG_COLORS.get(kind, LOG_COLORS['info'])))
        self.file_table.setItem(row, 1, item)

    # ------------------------------------------------------------ settings
    def restore_settings(self):
        set_lang_combo_code(self.src_edit, settings.get_str(_SETTINGS_PREFIX + 'srcLang', 'en-US'))
        set_lang_combo_code(self.tgt_edit, settings.get_str(_SETTINGS_PREFIX + 'tgtLang', 'zh-CN'))
        idx = self.layout_combo.findData(settings.get_str(_SETTINGS_PREFIX + 'layout', 'auto'))
        if idx >= 0:
            self.layout_combo.setCurrentIndex(idx)
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        settings.set_value(_SETTINGS_PREFIX + 'srcLang', lang_combo_code(self.src_edit))
        settings.set_value(_SETTINGS_PREFIX + 'tgtLang', lang_combo_code(self.tgt_edit))
        settings.set_value(_SETTINGS_PREFIX + 'layout', self.layout_combo.currentData())
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)

    # ------------------------------------------------------------ actions
    def _validate(self):
        """Returns an error string, or None if the form is valid."""
        if not self._paths:
            return '请先添加要检查的文件'
        if not lang_combo_code(self.src_edit) or not lang_combo_code(self.tgt_edit):
            return '请先填写原文语言和译文语言（双语文档没有自带语言信息）'
        return None

    def _set_controls_enabled(self, enabled):
        for w in (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn,
                  self.start_btn, self.export_btn,
                  self.src_edit, self.tgt_edit, self.layout_combo):
            w.setEnabled(enabled)

    def _start_batch(self):
        self._ran_count = 0
        self._summaries = [None] * len(self._paths)
        self.export_btn.setEnabled(False)
        for row in range(len(self._row_done)):
            self._row_done[row] = False

        error = self._validate()
        if error:
            self.summary_label.setText(error)
            self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS['error'])
            return

        shared = dict(
            src_lang=lang_combo_code(self.src_edit),
            tgt_lang=lang_combo_code(self.tgt_edit),
            layout=self.layout_combo.currentData(),
        )

        for row in range(self.file_table.rowCount()):
            self._set_row_status(row, _STATUS_RUNNING, 'info')
        self.summary_label.setText('正在检查 %d 个文件…' % len(self._paths))
        self.summary_label.setStyleSheet('color: #4B5262;')
        self._set_controls_enabled(False)

        self._worker = BatchAlignWorker(list(self._paths), shared, parent=self)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_file_done(self, row, ran_ok, message, summary):
        self._row_done[row] = True
        if ran_ok:
            self._ran_count += 1
            self._summaries[row] = summary
            needs_review = bool(summary['gap_count'] or summary['qa_flagged'] or not summary['total'])
            self._set_row_status(row, message, 'error' if needs_review else 'success')
        else:
            self._set_row_status(row, message, 'error')
        self.export_btn.setEnabled(self._ran_count > 0)

    def _on_all_done(self, checked, failed, needs_review):
        self._set_controls_enabled(True)
        if failed == 0 and needs_review == 0:
            text = '全部完成：%d 个文件全部对齐正常，没有发现问题' % checked
            kind = 'success'
        elif failed == 0:
            text = ('全部完成：%d 个文件已检查，其中 %d 个需要人工看一眼（详见上面各行的结果）'
                    % (checked, needs_review))
            kind = 'info'
        else:
            text = '完成：%d 个已检查，%d 个失败（详情见上面各行的结果）' % (checked, failed)
            kind = 'error'
        self.summary_label.setText(text)
        self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS[kind])

    # ------------------------------------------------------------- export
    def _start_export(self):
        if self._ran_count <= 0:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '导出汇总 CSV', os.path.join(self._last_dir, '批量对齐检查汇总'), _CSV_FILTER)
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
        """One row per file -- the table's own 结果 column, machine-
        readable. utf-8-sig for the same reason ``writers/csv_writer``
        uses it (Excel needs the BOM to open CJK content correctly)."""
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'units', 'gap_count', 'qa_flagged', 'status'])
            for row, input_path in enumerate(self._paths):
                s = self._summaries[row]
                status_item = self.file_table.item(row, 1)
                status = status_item.text() if status_item else ''
                if s is None:
                    writer.writerow([input_path, '', '', '', status or '未检查'])
                else:
                    writer.writerow([input_path, s['total'], s['gap_count'],
                                     s['qa_flagged'], status])
