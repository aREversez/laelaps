"""The QA-check tool's page: run every check in ``language_tools.qa``
against an already-existing corpus file (tmx/sdltm) and let the user
browse/filter/export the results.

This is the standalone counterpart to the QA checkbox in
``corpus_convert``'s page: that one runs QA as a side effect of
conversion, this one runs QA as the whole point, against a corpus you
already have. Both ultimately call the same ``language_tools.qa.run()``
-- see ``language_tools/tm/qa_report.py`` for the thin wiring that reads
an existing file and calls it (this page just wraps that module in a UI,
same "no HTTP layer" shape as every other tool page).

Same conventions as the other two tools: ``section()``/``CallableWorker``
from ``toolbox.widgets``/``toolbox.workers`` (this is the third tool using
both, which is why they're shared modules and not another private copy),
``objectName('primaryButton')``/``objectName('logConsole')``.

Result presentation follows tm_maintenance's stats-tab precedent (a
``QTableWidget``, not a log dump) but goes further: QA output is
per-segment, potentially thousands of rows for a large TM, so simply
listing everything would bury the handful of rows that actually need a
human's attention. Two controls narrow the view: a "只显示有问题的条目"
checkbox (checked by default -- the useful default view for someone who
just wants the punch list) and an issue-type filter dropdown. Both are
display-only filters over data already in memory (``self._last_units``)
-- neither re-runs QA or touches the file, so toggling them is instant.

Export is deliberately NOT filtered by the current view: "导出 CSV"
always writes the full corpus (every unit, QA columns included) via the
existing ``csv_writer.write(..., include_qa=True)``, unfiltered. Two
reasons: (1) reusing that function exactly as the convert pipeline already
does means there's no second "filtered CSV" code path to keep in sync,
and (2) a reviewer opening the CSV in Excel can filter/sort there with
full context (they can still see what passed, not just what failed) --
narrowing to "problems only" at export time would silently discard that.

Issue codes (TAG_MISMATCH, etc.) are translated to Chinese labels for
display -- both here (results table + filter dropdown, via
``_issue_label()``) and in the exported CSV (``csv_writer.py``'s own use
of the same ``qa.ISSUE_LABELS`` table) -- since a bare code means nothing
to a translator/reviewer who isn't the one who wrote the QA checks. The
codes themselves stay untouched as ``self._last_units[i].meta['qa_issues']``
and as the filter dropdown's underlying ``currentData()`` values; only the
*rendered* text changes.
"""
import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from language_tools import qa as qa_module
from language_tools.tm import io as tm_io
from language_tools.tm import qa_report as qa_report_module
from language_tools.writers import csv_writer
from toolbox.widgets import section
from toolbox.workers import CallableWorker

_CORPUS_FILTER = 'Corpus files (*.tmx *.sdltm)'
_CSV_FILTER = 'CSV (*.csv)'

_LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

# Short tooltip per issue type, for the filter dropdown. The *label* text
# (used both in the dropdown and now in the results table's "问题类型"
# column -- that's the bug this comment is here to prevent recurring)
# comes from ``qa.ISSUE_LABELS``, not a second copy here: two independent
# label dicts is exactly how "标签不匹配" in the dropdown and a raw
# "TAG_MISMATCH" in the table ended up saying different things for the
# same code. Tooltips stay local since they're GUI-only extra detail with
# no equivalent need to match the CSV export.
_ISSUE_TOOLTIPS = {
    'EMPTY_SOURCE': '这一条的原文是空的',
    'EMPTY_TARGET': '这一条还没有翻译',
    'LENGTH_RATIO_OUTLIER': '译文长度和原文长度的比例明显偏离整个语料库的平均水平',
    'NUMBER_MISMATCH': '原文和译文里出现的数字对不上，可能是漏译或多译',
    'PLACEHOLDER_MISMATCH': '{name}/%s 这类代码占位符在译文里被改动或丢失',
    'URL_MISMATCH': '原文里的链接在译文里丢失或被改动',
    'TAG_MISMATCH': '原文和译文的格式标签（如加粗）数量对不上',
    'SOURCE_CONFLICT': '同一句原文在语料库里对应了不止一种译文',
    'TARGET_CONFLICT': '同一句译文在语料库里对应了不止一种原文',
}


def _issue_label(issue_code):
    return qa_module.ISSUE_LABELS.get(issue_code, issue_code)


class QaCheckPage(QWidget):
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

        title = QLabel('QA 检查')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('对已有的翻译记忆库（tmx/sdltm）跑质量检查，生成审阅报告')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('选择要检查的 tmx/sdltm 文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_input)
        file_layout.addWidget(self.input_edit, 1)
        file_layout.addWidget(browse_btn)
        outer.addWidget(section('选择文件', file_row))

        action_row = QHBoxLayout()
        self.check_btn = QPushButton('开始检查')
        self.check_btn.setObjectName('primaryButton')
        self.check_btn.clicked.connect(self._start_check)
        self.export_btn = QPushButton('导出 CSV…')
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('导出全部条目（含未标记问题的），不受下面的筛选影响')
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
        self.hide_clean_chk.setChecked(True)
        self.hide_clean_chk.stateChanged.connect(self._refresh_table)
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItem('全部问题类型', None)
        for issue_type in qa_report_module.ISSUE_TYPES:
            label = _issue_label(issue_type)
            tip = _ISSUE_TOOLTIPS.get(issue_type, '')
            self.type_filter_combo.addItem(label, issue_type)
            if tip:
                self.type_filter_combo.setItemData(
                    self.type_filter_combo.count() - 1, tip, Qt.ToolTipRole)
        self.type_filter_combo.currentIndexChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.hide_clean_chk)
        filter_layout.addWidget(self.type_filter_combo)
        filter_layout.addStretch(1)
        outer.addWidget(section('筛选', filter_row))

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(['#', '原文', '译文', '问题类型', '置信度'])
        self.results_table.verticalHeader().setVisible(False)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        # Header text defaults to centered, item text to left-aligned;
        # with 原文/译文 stretched to fill the window (and their content
        # often long) that mismatch reads as messy, especially maximized.
        # Left-align both so the header sits above its column's content.
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setShowGrid(False)
        self.results_table.setAlternatingRowColors(True)
        outer.addWidget(section('QA 结果', self.results_table), 1)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText('状态信息会显示在这里')
        outer.addWidget(self.log)

    # ------------------------------------------------------------- dialogs
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _CORPUS_FILTER)
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
        return None

    def _start_check(self):
        self._last_units = None
        self.results_table.setRowCount(0)
        self.summary_label.setText('')
        self.export_btn.setEnabled(False)

        error = self._validate_check()
        if error:
            self._log(error, 'error')
            return

        input_path = self.input_edit.text().strip()
        self.check_btn.setEnabled(False)
        self._log('正在检查…')
        self._check_worker = CallableWorker(lambda: qa_report_module.run(input_path), parent=self)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.finished_err.connect(self._on_check_err)
        self._check_worker.start()

    def _on_check_ok(self, units):
        self.check_btn.setEnabled(True)
        self._last_units = units
        s = qa_report_module.summarize(units)
        rate = (s['flagged'] / s['total'] * 100) if s['total'] else 0.0
        self.summary_label.setText(
            '共 %d 条，%d 条有问题（%.1f%%）' % (s['total'], s['flagged'], rate))
        self.export_btn.setEnabled(bool(units))
        self._refresh_table()
        self._log('检查完成', 'success')

    def _on_check_err(self, message):
        self.check_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    # ----------------------------------------------------------- filtering
    def _refresh_table(self):
        self.results_table.setRowCount(0)
        if not self._last_units:
            return

        hide_clean = self.hide_clean_chk.isChecked()
        selected_type = self.type_filter_combo.currentData()

        rows = []
        for i, u in enumerate(self._last_units, 1):
            issues = u.meta.get('qa_issues', [])
            if hide_clean and not issues:
                continue
            if selected_type and selected_type not in issues:
                continue
            rows.append((i, u, issues))

        self.results_table.setRowCount(len(rows))
        for row, (i, u, issues) in enumerate(rows):
            conf = u.meta.get('qa_confidence', 1.0)
            issue_text = '、'.join(_issue_label(code) for code in issues) if issues else '-'
            self.results_table.setItem(row, 0, QTableWidgetItem(str(i)))
            self.results_table.setItem(row, 1, QTableWidgetItem(u.src_text))
            self.results_table.setItem(row, 2, QTableWidgetItem(u.tgt_text))
            self.results_table.setItem(row, 3, QTableWidgetItem(issue_text))
            self.results_table.setItem(row, 4, QTableWidgetItem('%.2f' % conf))

    # ------------------------------------------------------------ export
    def _start_export(self):
        # export_btn is only ever enabled after a successful check sets
        # self._last_units, so this can't be hit via the UI -- kept as a
        # silent guard against a future caller invoking this directly
        # (e.g. a keyboard shortcut wired to the same slot later) while no
        # results exist yet, rather than crashing on an empty CSV write.
        if not self._last_units:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', '', _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'

        units = self._last_units
        src_lang, tgt_lang = tm_io.infer_langs(units)
        self.export_btn.setEnabled(False)
        self._log('正在导出…')
        self._export_worker = CallableWorker(
            lambda: csv_writer.write(path, units, src_lang or 'SRC', tgt_lang or 'TGT', include_qa=True),
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
