"""The alignment-check tool's page: run ``language_tools.align_report``
against a bilingual source (docx/xlsx/csv/tsv) and let the user browse/
filter/export the resulting per-sentence diagnostics -- without writing
any tmx/sdltm/csv output. This is deliberately NOT a second conversion
entry point (that's ``corpus_convert``); it answers a narrower question
before you convert: "did my document get split and paired the way I
expect?"

Same three-part shape as ``qa_check`` (its closest sibling -- see that
page's docstring for the full reasoning this one doesn't repeat):
``section()``/``CallableWorker`` from the shared toolbox modules, a
``QTableWidget`` results view with a "只显示有问题的条目" filter, an
export that always writes the full unfiltered set. Three differences
from qa_check worth calling out:

- The filter defaults to UNCHECKED here (qa_check's defaults to checked).
  qa_check's job is finding the needles in a large existing corpus, so
  hiding clean rows by default is the useful view. This tool's job is
  "let me see how my one document got aligned" -- a well-aligned document
  with zero problems is a *good* outcome the user should see confirmed
  (e.g. "12 条，全部一一对应"), not an empty table with no visible
  explanation for why nothing's there. Filtering down to problems is
  still available (and worth turning on for a long document with a lot
  of GAPs to sift through), just not the first thing shown.
- The file/language/layout inputs are the exact same three controls
  ``corpus_convert`` uses (``toolbox.widgets.make_lang_combo()``/
  ``make_layout_combo()``) -- aligning a document needs the same
  src/tgt language and (for .docx) layout hint that converting one does,
  so this reuses those widgets rather than re-collecting the same inputs
  with different wording.
- "Has a problem" here means align_gap OR qa_issues, not qa_issues alone
  -- a GAP move (one side had no corresponding sentence at all) is
  exactly the kind of alignment defect this tool exists to surface, and
  it's orthogonal to the standard QA checks (a GAP row's src or tgt text
  is often empty, which already trips EMPTY_SOURCE/EMPTY_TARGET, but not
  every GAP does -- e.g. a short leftover fragment might not read as
  "empty" to QA but is still a GAP the aligner had to punt on).
"""
import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from language_tools import align_report
from language_tools import qa as qa_module
from language_tools.writers import csv_writer
from toolbox.widgets import LANG_TOOLTIP, lang_combo_code, make_lang_combo, make_layout_combo
from toolbox.widgets import section
from toolbox.workers import CallableWorker

_BILINGUAL_FILTER = 'Bilingual source files (*.docx *.xlsx *.xlsm *.csv *.tsv)'
_CSV_FILTER = 'CSV (*.csv)'

_LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

_MOVE_TOOLTIPS = {
    '1:1': '一句对一句，最常见的情况',
    '2:1': '两句原文合并成了一句译文',
    '1:2': '一句原文拆成了两句译文',
    '1:0': '这句原文在译文里完全找不到对应内容',
    '0:1': '这句译文在原文里完全找不到对应内容',
}


class AlignmentCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_units = None
        self._check_worker = None
        self._export_worker = None
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('对齐检查')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('预览双语文档的句子对齐结果，不生成任何文件')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        # --- file ---
        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('选择要检查的双语文档…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_input)
        file_layout.addWidget(self.input_edit, 1)
        file_layout.addWidget(browse_btn)
        outer.addWidget(section('第一步：选择文件', file_row))

        # --- language ---
        lang_widget = QWidget()
        lang_form = QFormLayout(lang_widget)
        lang_form.setContentsMargins(0, 0, 0, 0)
        self.src_edit = make_lang_combo('en-US')
        self.tgt_edit = make_lang_combo('zh-CN')
        self.src_edit.setToolTip(LANG_TOOLTIP)
        self.tgt_edit.setToolTip(LANG_TOOLTIP)
        lang_form.addRow('原文语言', self.src_edit)
        lang_form.addRow('译文语言', self.tgt_edit)
        outer.addWidget(section('第二步：确认语言', lang_widget))

        # --- docx layout ---
        layout_widget = QWidget()
        layout_form = QFormLayout(layout_widget)
        layout_form.setContentsMargins(0, 0, 0, 0)
        self.layout_combo = make_layout_combo()
        self.layout_combo.setToolTip('仅 .docx 需要关心')
        layout_form.addRow('文档排版方式', self.layout_combo)
        outer.addWidget(section('文档排版方式', layout_widget))

        action_row = QHBoxLayout()
        self.check_btn = QPushButton('开始检查')
        self.check_btn.setObjectName('primaryButton')
        self.check_btn.clicked.connect(self._start_check)
        self.export_btn = QPushButton('导出 CSV…')
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('导出全部条目（含没有问题的），不受下面的筛选影响')
        self.export_btn.clicked.connect(self._start_export)
        action_row.addWidget(self.check_btn)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('color: #4B5262;')
        outer.addWidget(self.summary_label)

        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self.hide_clean_chk = QCheckBox('只显示有问题的条目')
        self.hide_clean_chk.setChecked(False)
        self.hide_clean_chk.setToolTip('有问题 = 存在 GAP（跳过）或被 QA 标记')
        self.hide_clean_chk.stateChanged.connect(self._refresh_table)
        self.move_filter_combo = QComboBox()
        self.move_filter_combo.addItem('全部对齐方式', None)
        self.move_filter_combo.currentIndexChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.hide_clean_chk)
        filter_layout.addWidget(self.move_filter_combo)
        filter_layout.addStretch(1)
        outer.addWidget(section('筛选', filter_row))

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(['段落', '原文', '译文', '对齐方式', '成本', 'QA'])
        self.results_table.verticalHeader().setVisible(False)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        # See toolbox/tools/qa_check/page.py's regression test for why
        # this matters: header text defaults to centered, item text to
        # left, and the mismatch reads as messy once 原文/译文 stretch
        # wide with often-long content.
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setShowGrid(False)
        self.results_table.setAlternatingRowColors(True)
        outer.addWidget(section('对齐结果', self.results_table), 1)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText('状态信息会显示在这里')
        outer.addWidget(self.log)

    # ------------------------------------------------------------- dialogs
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _BILINGUAL_FILTER)
        if path:
            self.input_edit.setText(path)

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = _LOG_COLORS.get(kind, _LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))

    # ------------------------------------------------------------- check
    def _validate_check(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            return '请先选择要检查的文件'
        if not os.path.exists(input_path):
            return '找不到这个文件，请重新选择'
        if not lang_combo_code(self.src_edit) or not lang_combo_code(self.tgt_edit):
            return '请先填写原文语言和译文语言'
        return None

    def _start_check(self):
        self._last_units = None
        self.results_table.setRowCount(0)
        self.summary_label.setText('')
        self.export_btn.setEnabled(False)
        self._reset_move_filter()

        error = self._validate_check()
        if error:
            self._log(error, 'error')
            return

        input_path = self.input_edit.text().strip()
        reader_opts = {}
        if input_path.lower().endswith('.docx') and self.layout_combo.currentData() != 'auto':
            reader_opts['layout'] = self.layout_combo.currentData()
        src_lang = lang_combo_code(self.src_edit)
        tgt_lang = lang_combo_code(self.tgt_edit)

        self.check_btn.setEnabled(False)
        self._log('正在对齐…')
        self._check_worker = CallableWorker(
            lambda: align_report.run(input_path, src_lang, tgt_lang, reader_opts=reader_opts),
            parent=self)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.finished_err.connect(self._on_check_err)
        self._check_worker.start()

    def _on_check_ok(self, units):
        self.check_btn.setEnabled(True)
        self._last_units = units
        s = align_report.summarize(units)
        self.summary_label.setText(
            '共 %d 条，%d 条 GAP，%d 条被 QA 标记' % (s['total'], s['gap_count'], s['qa_flagged']))
        self.export_btn.setEnabled(bool(units))
        self._populate_move_filter(s['move_counts'])
        self._refresh_table()
        if s['total'] and not s['gap_count'] and not s['qa_flagged']:
            # Otherwise "检查完成" alone, sitting above a table that (if
            # 只显示有问题的条目 got checked) would then be legitimately
            # empty, reads exactly like the silent-nothing-happened
            # confusion this default was changed to avoid -- say the good
            # outcome out loud instead of just implying it via row count.
            self._log('检查完成，%d 条全部对齐正常，没有发现问题' % s['total'], 'success')
        else:
            self._log('检查完成', 'success')

    def _on_check_err(self, message):
        self.check_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    # ----------------------------------------------------------- filtering
    def _reset_move_filter(self):
        self.move_filter_combo.blockSignals(True)
        self.move_filter_combo.clear()
        self.move_filter_combo.addItem('全部对齐方式', None)
        self.move_filter_combo.blockSignals(False)

    def _populate_move_filter(self, move_counts):
        """Only lists moves that actually occurred in this document (not
        every code align_report.MOVE_LABELS knows about) -- an empty
        dropdown full of moves that never happened would just be noise
        for a document that's e.g. entirely 1:1.
        """
        self._reset_move_filter()
        self.move_filter_combo.blockSignals(True)
        for move_code in sorted(move_counts):
            label = '%s（%d）' % (align_report.move_label(move_code), move_counts[move_code])
            self.move_filter_combo.addItem(label, move_code)
            idx = self.move_filter_combo.count() - 1
            tip = _MOVE_TOOLTIPS.get(move_code)
            if tip:
                self.move_filter_combo.setItemData(idx, tip, Qt.ToolTipRole)
        self.move_filter_combo.blockSignals(False)

    def _refresh_table(self):
        self.results_table.setRowCount(0)
        if not self._last_units:
            return

        hide_clean = self.hide_clean_chk.isChecked()
        selected_move = self.move_filter_combo.currentData()

        rows = []
        for u in self._last_units:
            has_problem = u.meta.get('align_gap') or u.meta.get('qa_issues')
            if hide_clean and not has_problem:
                continue
            if selected_move and u.meta.get('align_move') != selected_move:
                continue
            rows.append(u)

        self.results_table.setRowCount(len(rows))
        for row, u in enumerate(rows):
            move_code = u.meta.get('align_move', '')
            issues = u.meta.get('qa_issues', [])
            self.results_table.setItem(row, 0, QTableWidgetItem(u.source_key or ''))
            self.results_table.setItem(row, 1, QTableWidgetItem(u.src_text))
            self.results_table.setItem(row, 2, QTableWidgetItem(u.tgt_text))
            self.results_table.setItem(row, 3, QTableWidgetItem(align_report.move_label(move_code)))
            self.results_table.setItem(row, 4, QTableWidgetItem('%.2f' % u.meta.get('alignment_cost', 0.0)))
            qa_text = '、'.join(qa_module.ISSUE_LABELS.get(code, code) for code in issues) if issues else '-'
            self.results_table.setItem(row, 5, QTableWidgetItem(qa_text))

    # ------------------------------------------------------------ export
    def _start_export(self):
        # export_btn is only ever enabled after a successful check sets
        # self._last_units, so this can't be hit via the UI -- kept as a
        # silent guard against a future caller invoking this directly.
        if not self._last_units:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', '', _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'

        units = self._last_units
        src_lang = lang_combo_code(self.src_edit) or 'SRC'
        tgt_lang = lang_combo_code(self.tgt_edit) or 'TGT'
        self.export_btn.setEnabled(False)
        self._log('正在导出…')
        self._export_worker = CallableWorker(
            lambda: csv_writer.write(path, units, src_lang, tgt_lang, include_qa=True, include_align=True),
            parent=self)
        self._export_worker.finished_ok.connect(lambda _=None: self._on_export_ok(path))
        self._export_worker.finished_err.connect(self._on_export_err)
        self._export_worker.start()

    def _on_export_ok(self, path):
        self.export_btn.setEnabled(True)
        self._log('已导出到 %s' % path, 'success')

    def _on_export_err(self, message):
        self.export_btn.setEnabled(True)
        self._log('导出失败：%s' % message, 'error')
