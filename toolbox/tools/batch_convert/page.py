"""The batch-conversion tool's page: same idea as ``corpus_convert`` (a
form wrapping ``language_tools.api.convert()``, run off the UI thread) but
applied to a whole list of files instead of one -- add files and/or whole
folders, set the language pair/layout/output formats once, and it calls
``api.convert()`` once per file, same as if you'd run the single-file tool
that many times by hand.

Design decisions locked in with Eliot before writing this (2026-09-12):
- Output for each file goes right next to that file (``output_base =``
  the input path minus its extension), identical to the single-file tool
  -- no separate "pick an output folder" step to keep the form simple.
- Files can be added individually (multi-select) or by picking a whole
  folder, which is scanned recursively for supported extensions.
- Language pair/layout/output-formats/QA are one shared setting applied
  to every file in the batch, not per-file -- per-file overrides would be
  more flexible but are explicitly out of scope for this first pass.

``_BILINGUAL_EXTS``/``_SUPPORTED_FILTER``/``_FORMAT_TOOLTIPS``/
``_QA_TOOLTIP`` are duplicated from ``corpus_convert/page.py`` rather than
imported -- this is the second call site, and per this toolbox's own
promote-at-the-third-site convention (see ``toolbox/widgets.py``) that's
still a coincidence, not yet a pattern worth sharing.

Unlike ``corpus_convert``'s single QLineEdit + browse button, the file
list here is a ``QTableWidget`` from the start (文件/状态 columns) so the
same widget serves as both the "what's queued" list before conversion and
the live per-file progress display during/after it -- no separate log
widget needed the way the single-file tool has one.
"""
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from language_tools import api
from toolbox.widgets import LANG_TOOLTIP, LOG_COLORS, compact_combo, labeled_field, lang_combo_code
from toolbox.widgets import make_lang_combo, make_layout_combo
from toolbox.widgets import section as _section

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}
_CORPUS_EXTS = {'.tmx', '.sdltm'}
_SUPPORTED_EXTS = _BILINGUAL_EXTS | _CORPUS_EXTS
_SUPPORTED_FILTER = 'Supported files (*.docx *.xlsx *.xlsm *.csv *.tsv *.tmx *.sdltm)'

_FORMAT_TOOLTIPS = {
    'sdltm': 'Trados 记忆库格式',
    'tmx': 'CAT 工具通用记忆库格式',
    'csv': '可人工核对的表格',
}
_QA_TOOLTIP = '检查漏译、数字不一致等问题'

# extension -> the one output format it'd be a same-format no-op to
# generate for a file already in that format; same idea as
# corpus_convert's _sync_format_checkboxes, but applied per-file here
# since a batch's files can be a mix of formats (a single greyed-out
# checkbox couldn't represent "skip tmx for this file but not that one").
_SAME_FORMAT_SKIP = {'.tmx': 'tmx', '.sdltm': 'sdltm', '.csv': 'csv'}

_STATUS_PENDING = '等待中'
_STATUS_RUNNING = '转换中…'


class BatchConvertWorker(QThread):
    """Runs ``api.convert()`` once per file, off the UI thread. Unlike
    ``corpus_convert.ConvertWorker`` (one file, one result), this keeps
    going past a single file's error -- one bad file in a batch of fifty
    shouldn't block the other forty-nine -- and reports each file's
    outcome as it happens via ``file_done``, plus a final tally via
    ``all_done`` once every file has been attempted.
    """
    file_done = Signal(int, bool, str)  # row, ok, status message
    all_done = Signal(int, int)         # succeeded, failed

    def __init__(self, input_paths, shared_kwargs, parent=None):
        super().__init__(parent)
        self._input_paths = input_paths
        self._shared = shared_kwargs  # src_lang, tgt_lang, reader_opts, qa, formats

    def run(self):
        succeeded = failed = 0
        for row, input_path in enumerate(self._input_paths):
            ok, message = self._convert_one(input_path)
            if ok:
                succeeded += 1
            else:
                failed += 1
            self.file_done.emit(row, ok, message)
        self.all_done.emit(succeeded, failed)

    def _convert_one(self, input_path):
        ext = os.path.splitext(input_path)[1].lower()
        skip_fmt = _SAME_FORMAT_SKIP.get(ext)
        formats = tuple(f for f in self._shared['formats'] if f != skip_fmt)
        if not formats:
            return False, '跳过：勾选的生成格式和源文件格式相同'
        if ext in _BILINGUAL_EXTS and (not self._shared['src_lang'] or not self._shared['tgt_lang']):
            return False, '跳过：这类文件需要原文/译文语言'

        try:
            result = api.convert(
                input_path=input_path,
                output_base=os.path.splitext(input_path)[0],
                src_lang=self._shared['src_lang'] or None,
                tgt_lang=self._shared['tgt_lang'] or None,
                formats=formats,
                reader_opts=self._shared['reader_opts'],
                qa=self._shared['qa'],
            )
        except Exception as e:  # noqa: BLE001 -- surfaced per-file, doesn't stop the batch
            return False, str(e)

        units, exported = result['units'], result['exported']
        message = '成功：%d 组' % units if exported == units else \
            '成功：%d 组（%d 组被过滤）' % (units, units - exported)
        if len(formats) < len(self._shared['formats']):
            message += '，已跳过同格式选项'
        return True, message


class BatchConvertPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = []  # str, in the same order as the table's rows
        self._worker = None
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('批量转换')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('一次性转换多个文件，每个结果保存在各自源文件旁边')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        # --- file list ---
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)

        btn_row = QHBoxLayout()
        add_files_btn = QPushButton('添加文件…')
        add_files_btn.clicked.connect(self._add_files)
        add_folder_btn = QPushButton('添加文件夹…')
        add_folder_btn.clicked.connect(self._add_folder)
        self.remove_btn = QPushButton('移除选中')
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton('清空')
        self.clear_btn.clicked.connect(self._clear_all)
        for b in (add_files_btn, add_folder_btn, self.remove_btn, self.clear_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        list_layout.addLayout(btn_row)

        self.count_label = QLabel('共 0 个文件')
        self.count_label.setStyleSheet('color: #6B7280;')
        list_layout.addWidget(self.count_label)

        self.file_table = QTableWidget(0, 2)
        self.file_table.setHorizontalHeaderLabels(['文件', '状态'])
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

        outer.addWidget(_section('待转换文件', list_widget), 1)

        # --- language + docx layout, all inline in one row (same layout
        # as corpus_convert's 语言与排版方式 section) ---
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

        # --- output formats ---
        fmt_widget = QWidget()
        fmt_row = QHBoxLayout(fmt_widget)
        fmt_row.setContentsMargins(0, 0, 0, 0)
        self.chk_sdltm = QCheckBox('sdltm')
        self.chk_tmx = QCheckBox('tmx')
        self.chk_csv = QCheckBox('csv')
        for cb, key in ((self.chk_sdltm, 'sdltm'), (self.chk_tmx, 'tmx'), (self.chk_csv, 'csv')):
            cb.setChecked(True)
            cb.setToolTip(_FORMAT_TOOLTIPS[key])
            fmt_row.addWidget(cb)
        fmt_row.addStretch(1)
        outer.addWidget(_section('生成格式', fmt_widget))

        self.chk_qa = QCheckBox('运行内容检查')
        self.chk_qa.setToolTip(_QA_TOOLTIP)
        outer.addWidget(self.chk_qa)

        self.start_btn = QPushButton('开始批量转换')
        self.start_btn.setObjectName('primaryButton')
        self.start_btn.clicked.connect(self._start_batch)
        start_row = QHBoxLayout()
        start_row.addWidget(self.start_btn)
        start_row.addStretch(1)
        outer.addLayout(start_row)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('color: #4B5262;')
        outer.addWidget(self.summary_label)

    # ------------------------------------------------------------ file list
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件', '', _SUPPORTED_FILTER)
        for path in paths:
            self._append_path(path)
        self._refresh_count()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹')
        if not folder:
            return
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in _SUPPORTED_EXTS:
                    self._append_path(os.path.join(root, name))
        self._refresh_count()

    def _append_path(self, path):
        if path in self._paths:
            return  # already queued -- adding the same file twice would double-convert it
        self._paths.append(path)
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
            del self._paths[row]
        self._refresh_count()

    def _clear_all(self):
        self.file_table.setRowCount(0)
        self._paths.clear()
        self._refresh_count()

    def _refresh_count(self):
        self.count_label.setText('共 %d 个文件' % len(self._paths))

    def _set_row_status(self, row, text, kind):
        item = QTableWidgetItem(text)
        item.setForeground(QColor(LOG_COLORS.get(kind, LOG_COLORS['info'])))
        self.file_table.setItem(row, 1, item)

    # ------------------------------------------------------------ actions
    def _validate(self):
        """Returns an error string, or None if the form is valid."""
        if not self._paths:
            return '请先添加要转换的文件'
        has_bilingual = any(os.path.splitext(p)[1].lower() in _BILINGUAL_EXTS for p in self._paths)
        if has_bilingual and (not lang_combo_code(self.src_edit) or not lang_combo_code(self.tgt_edit)):
            return '本批文件里有双语文档，需要先填写原文语言和译文语言'
        if not any(cb.isChecked() for cb in (self.chk_sdltm, self.chk_tmx, self.chk_csv)):
            return '请至少勾选一种要生成的格式'
        return None

    def _set_controls_enabled(self, enabled):
        for w in (self.remove_btn, self.clear_btn, self.start_btn,
                  self.src_edit, self.tgt_edit, self.layout_combo,
                  self.chk_sdltm, self.chk_tmx, self.chk_csv, self.chk_qa):
            w.setEnabled(enabled)

    def _start_batch(self):
        error = self._validate()
        if error:
            self.summary_label.setText(error)
            self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS['error'])
            return

        reader_opts = {}
        if self.layout_combo.currentData() != 'auto':
            # Passed through for every file regardless of its own format --
            # readers other than docx ignore an unrecognized 'layout' opt
            # (see toolbox/widgets.py's LAYOUT_CHOICES docstring), so this
            # doesn't need to be conditioned on each file's own extension.
            reader_opts['layout'] = self.layout_combo.currentData()

        shared_kwargs = dict(
            src_lang=lang_combo_code(self.src_edit) or None,
            tgt_lang=lang_combo_code(self.tgt_edit) or None,
            formats=tuple(f for f, cb in (
                ('sdltm', self.chk_sdltm), ('tmx', self.chk_tmx), ('csv', self.chk_csv)) if cb.isChecked()),
            reader_opts=reader_opts,
            qa=self.chk_qa.isChecked(),
        )

        for row in range(self.file_table.rowCount()):
            self._set_row_status(row, _STATUS_RUNNING, 'info')

        self.summary_label.setText('正在转换 %d 个文件…' % len(self._paths))
        self.summary_label.setStyleSheet('color: #4B5262;')
        self._set_controls_enabled(False)

        self._worker = BatchConvertWorker(list(self._paths), shared_kwargs, parent=self)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_file_done(self, row, ok, message):
        self._set_row_status(row, message, 'success' if ok else 'error')

    def _on_all_done(self, succeeded, failed):
        self._set_controls_enabled(True)
        if failed == 0:
            text = '全部完成：%d 个文件都转换成功' % succeeded
            kind = 'success'
        else:
            text = '完成：%d 个成功，%d 个失败（详情见上面各行的状态）' % (succeeded, failed)
            kind = 'error'
        self.summary_label.setText(text)
        self.summary_label.setStyleSheet('color: %s;' % LOG_COLORS[kind])
