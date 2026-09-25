"""The TM-maintenance tool's page: five tabs (clean/merge/leverage/
compare/stats), each a thin form wrapping ``language_tools.tm.*``
directly -- same "no HTTP layer, just import and call the library" shape
as ``corpus_convert/page.py``, and the same ``QThread`` pattern
(``toolbox.workers.CallableWorker``) so a large TM doesn't freeze the UI
while it's being processed.

Unlike ``ConvertWorker`` (specific to ``api.convert()``'s kwargs shape),
``CallableWorker`` is a generic "run this zero-arg callable off the UI
thread" wrapper -- shared across all five tabs, since none of
clean/merge/leverage/compare/stats needs a specialized ``run()`` body,
just a function call that shouldn't block. Each tab wires its own
callable (``_clean_job``/``_merge_job``/``_leverage_job``/
``_compare_job``/``_stats_job``, module-level so they're callable/
testable without a QWidget) plus its own start/success/error handlers.

Copy and layout conventions follow ``corpus_convert/page.py`` (see that
file's docstring for the reasoning): short section titles, explanation in
tooltips, ``section()`` (from ``toolbox.widgets``) for headers,
``objectName('primaryButton')`` for the action button,
``objectName('logConsole')`` for output -- shared here across all five
tabs rather than one log per tab, so the user has a single place to look
regardless of which action they just ran.

The stats/leverage/compare tabs are the exceptions to "results go in the
log": each produces several distinct numbers/rows at once, which reads as
a wall of text in a scrolling console and is hard to scan back to after
the fact -- so each gets its own ``QTableWidget`` instead, populated
fresh on every run. leverage's table is fixed-shape (one row per
``leverage.BANDS`` entry); compare's is genuinely variable-width (one
column per input being compared, via ``_set_dynamic_table_rows()``) since
the whole point of comparing N files is that N isn't fixed. Clean/merge
stay log-based: each produces one outcome (how many were removed/merged/
resolved), which a single log line already states clearly.

``tmtool``'s leverage/compare/qa_check/stats subcommands all have a
``--report`` flag (HTML/PDF summary export, see ``language_tools/
reports/``); of those, leverage/compare/stats are tabs in this file, and
each gets a "导出报告…" button wired to the shared
``_start_export_report()`` (only the adapter call and the source data
differ per tab) -- a second export button next to the existing CSV one
for leverage/compare, and the only export button for stats, which has
no CSV export of its own.

Settings persistence: implements the optional ``restore_settings()``/
``save_settings()`` hooks ``main_window.py`` checks for (see
``corpus_convert/page.py``'s docstring for the full reasoning) -- 清理
选项四个复选框、合并的冲突处理策略、and the last-used directory shared
across every browse dialog on all five tabs round-trip across launches
via ``toolbox/settings.py``, under the ``tm_maintenance/`` key prefix.
Stats/leverage/compare have nothing of their own to persist beyond the
shared last-used directory -- file pickers (plus, for leverage, a fixed
default fuzzy-match floor not exposed as a control here) with no other
options.
"""
import html
import os

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCheckBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from language_tools.reports import adapters as report_adapters
from language_tools.reports import render as report_render
from language_tools.tm import clean as clean_module
from language_tools.tm import compare as compare_module
from language_tools.tm import io as tm_io
from language_tools.tm import leverage as leverage_module
from language_tools.tm import merge as merge_module
from language_tools.tm import stats as stats_module
from language_tools.writers import csv_writer
from toolbox import settings
from toolbox.widgets import (
    CORPUS_FILTER, LOG_COLORS, CurrentPageTabWidget, compact_combo,
    labeled_field, page_shell, section,
)
from toolbox.workers import CallableWorker, wait_for_running

_SAVE_FILTER = 'TMX (*.tmx);;SDLTM (*.sdltm)'
_CSV_FILTER = 'CSV (*.csv)'
_REPORT_FILTER = 'HTML (*.html);;PDF (*.pdf)'
_SETTINGS_PREFIX = 'tm_maintenance/'

_CLEAN_TOOLTIPS = {
    'normalize': 'Unicode/空白标准化，让格式不同但内容相同的条目能被正确识别为重复',
    'dedupe': '去除原文+译文完全相同的重复条目',
    'remove_empty': '去除原文或译文为空的条目',
    'remove_identical': '连原文=译文的条目也去掉（默认保留——有些内容本来就该原文译文一致，比如产品名）',
}
_CLEAN_OUTPUT_TOOLTIP = '留空则覆盖原文件'

# (short label, technical value, tooltip detail) -- same shape as
# corpus_convert's _LAYOUT_CHOICES.
_STRATEGY_CHOICES = [
    ('全部保留（默认）', 'keep-all', '不处理冲突，全部保留，交给后续人工/QA 检查'),
    ('保留先出现的', 'prefer-first', '同一原文对应不同译文时，保留先出现的那条'),
    ('保留后出现的', 'prefer-last', '同一原文对应不同译文时，保留后出现的那条'),
    ('按修改时间取新', 'prefer-newer', '按时间戳保留较新的译文；没有时间戳的条目视为最旧'),
]


def _clean_job(input_path, output_path, normalize, dedupe, remove_empty, remove_identical):
    units = tm_io.read_corpus(input_path)
    src_lang, tgt_lang = tm_io.infer_langs(units)
    kept, report = clean_module.clean(
        units, normalize=normalize, dedupe=dedupe,
        remove_empty=remove_empty, remove_identical=remove_identical)
    tm_io.write_corpus(output_path, kept, src_lang, tgt_lang)
    report['output_path'] = output_path
    return report


def _merge_job(input_paths, output_path, strategy):
    unit_lists = [tm_io.read_corpus(p) for p in input_paths]
    merged, report = merge_module.merge(unit_lists, strategy=strategy)
    src_lang, tgt_lang = tm_io.infer_langs(merged)
    tm_io.write_corpus(output_path, merged, src_lang, tgt_lang)
    report['output_path'] = output_path
    report['strategy'] = strategy
    return report


def _stats_job(input_path):
    units = tm_io.read_corpus(input_path)
    return stats_module.compute(units)


def _leverage_job(candidate_path, tm_path):
    tm_units = tm_io.read_corpus(tm_path)
    candidate_units = tm_io.read_corpus(candidate_path)
    leverage_module.analyze(tm_units, candidate_units)
    return candidate_units


def _compare_job(input_paths):
    labels = tm_io.make_labels(input_paths)
    named = list(zip(labels, (tm_io.read_corpus(p) for p in input_paths)))
    return compare_module.compare(named)


class TmMaintenancePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._clean_worker = None
        self._merge_worker = None
        self._leverage_worker = None
        self._compare_worker = None
        self._stats_worker = None
        self._leverage_units = None    # last leverage analyze() result, for export
        self._compare_report = None    # last compare() result, for export
        self._last_stats = None        # last stats.compute() result, for export
        self._last_dir = ''  # overwritten by restore_settings() when wired through MainWindow
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer, _, _ = page_shell(
            self,
            '语料维护',
            '清理、合并、统计翻译记忆库文件（tmx/sdltm）',
            spacing=18,
        )

        self.tabs = CurrentPageTabWidget()
        self.tabs.addTab(self._build_clean_tab(), '清理')
        self.tabs.addTab(self._build_merge_tab(), '合并')
        self.tabs.addTab(self._build_leverage_tab(), '杠杆分析')
        self.tabs.addTab(self._build_compare_tab(), '对比')
        self.tabs.addTab(self._build_stats_tab(), '统计')
        outer.addWidget(self.tabs)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setPlaceholderText('操作结果会显示在这里')
        outer.addWidget(section('结果', self.log), 1)

    def _build_clean_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.clean_input_edit = QLineEdit()
        self.clean_input_edit.setPlaceholderText('选择要清理的 tmx/sdltm 文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_clean_input)
        file_layout.addWidget(self.clean_input_edit, 1)
        file_layout.addWidget(browse_btn)
        layout.addWidget(section('选择文件', file_row))

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.clean_output_edit = QLineEdit()
        self.clean_output_edit.setPlaceholderText('留空则覆盖原文件')
        self.clean_output_edit.setToolTip(_CLEAN_OUTPUT_TOOLTIP)
        output_browse_btn = QPushButton('另存为…')
        output_browse_btn.clicked.connect(self._browse_clean_output)
        output_layout.addWidget(self.clean_output_edit, 1)
        output_layout.addWidget(output_browse_btn)
        layout.addWidget(section('输出到（可选）', output_row))

        opts_row = QWidget()
        opts_layout = QHBoxLayout(opts_row)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        self.clean_chk_normalize = QCheckBox('标准化')
        self.clean_chk_dedupe = QCheckBox('去重')
        self.clean_chk_remove_empty = QCheckBox('去空段')
        self.clean_chk_remove_identical = QCheckBox('去原文=译文')
        for cb, key, default in (
            (self.clean_chk_normalize, 'normalize', True),
            (self.clean_chk_dedupe, 'dedupe', True),
            (self.clean_chk_remove_empty, 'remove_empty', True),
            (self.clean_chk_remove_identical, 'remove_identical', False),
        ):
            cb.setChecked(default)
            cb.setToolTip(_CLEAN_TOOLTIPS[key])
            opts_layout.addWidget(cb)
        opts_layout.addStretch(1)
        layout.addWidget(section('清理选项', opts_row))

        self.clean_btn = QPushButton('开始清理')
        self.clean_btn.setObjectName('primaryButton')
        self.clean_btn.clicked.connect(self._start_clean)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.clean_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        return tab

    def _build_merge_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)
        self.merge_list = QListWidget()
        self.merge_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.merge_list.setToolTip('要合并的 tmx/sdltm 文件，按添加顺序参与冲突判定')
        list_layout.addWidget(self.merge_list)
        list_btn_row = QHBoxLayout()
        self.merge_add_btn = QPushButton('添加文件…')
        self.merge_add_btn.clicked.connect(self._browse_merge_inputs)
        self.merge_remove_btn = QPushButton('移除选中')
        self.merge_remove_btn.clicked.connect(self._remove_selected_merge_inputs)
        self.merge_clear_btn = QPushButton('清空')
        self.merge_clear_btn.clicked.connect(self.merge_list.clear)
        list_btn_row.addWidget(self.merge_add_btn)
        list_btn_row.addWidget(self.merge_remove_btn)
        list_btn_row.addWidget(self.merge_clear_btn)
        list_btn_row.addStretch(1)
        list_layout.addLayout(list_btn_row)
        layout.addWidget(section('选择要合并的文件（可多选）', list_widget))

        # --- output + conflict strategy, combined in one row ---
        # These used to be two stacked "第二步"/"第三步" sections. Neither
        # needs a whole section to itself -- 保存到 is one line edit plus
        # a button, 冲突处理策略 is one combo box -- so, same fix as
        # alignment_check's 语言与排版方式 row: lay both out side by side
        # in a single QHBoxLayout under one section title, with the combo
        # sized to its own content (compact_combo()) instead of stretched
        # to a QFormLayout field column's full width.
        opts_widget = QWidget()
        opts_layout = QHBoxLayout(opts_widget)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.setSpacing(28)

        output_field = QWidget()
        output_layout = QHBoxLayout(output_field)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.merge_output_edit = QLineEdit()
        self.merge_output_edit.setPlaceholderText('合并结果保存到…')
        output_browse_btn = QPushButton('另存为…')
        output_browse_btn.clicked.connect(self._browse_merge_output)
        output_layout.addWidget(self.merge_output_edit, 1)
        output_layout.addWidget(output_browse_btn)
        opts_layout.addLayout(labeled_field('保存到', output_field), 1)

        self.merge_strategy_combo = QComboBox()
        self.merge_strategy_combo.setToolTip('同一原文在不同文件里译文不一样时怎么处理')
        compact_combo(self.merge_strategy_combo)
        for i, (display_text, value, item_tip) in enumerate(_STRATEGY_CHOICES):
            self.merge_strategy_combo.addItem(display_text, value)
            self.merge_strategy_combo.setItemData(i, item_tip, Qt.ToolTipRole)
        opts_layout.addLayout(labeled_field('冲突处理策略', self.merge_strategy_combo))

        layout.addWidget(section('保存', opts_widget))

        self.merge_btn = QPushButton('开始合并')
        self.merge_btn.setObjectName('primaryButton')
        self.merge_btn.clicked.connect(self._start_merge)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.merge_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        return tab

    def _build_leverage_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        candidate_row = QWidget()
        candidate_layout = QHBoxLayout(candidate_row)
        candidate_layout.setContentsMargins(0, 0, 0, 0)
        self.leverage_input_edit = QLineEdit()
        self.leverage_input_edit.setPlaceholderText('要评估的新内容（tmx/sdltm）…')
        candidate_browse_btn = QPushButton('浏览…')
        candidate_browse_btn.clicked.connect(self._browse_leverage_input)
        candidate_layout.addWidget(self.leverage_input_edit, 1)
        candidate_layout.addWidget(candidate_browse_btn)
        layout.addWidget(section('待分析文件', candidate_row))

        tm_row = QWidget()
        tm_layout = QHBoxLayout(tm_row)
        tm_layout.setContentsMargins(0, 0, 0, 0)
        self.leverage_tm_edit = QLineEdit()
        self.leverage_tm_edit.setPlaceholderText('已有的参考 TM（tmx/sdltm）…')
        self.leverage_tm_edit.setToolTip('待分析文件里的每一句，会拿来跟这份 TM 里的原文做匹配')
        tm_browse_btn = QPushButton('浏览…')
        tm_browse_btn.clicked.connect(self._browse_leverage_tm)
        tm_layout.addWidget(self.leverage_tm_edit, 1)
        tm_layout.addWidget(tm_browse_btn)
        layout.addWidget(section('参考 TM', tm_row))

        self.leverage_btn = QPushButton('开始分析')
        self.leverage_btn.setObjectName('primaryButton')
        self.leverage_btn.clicked.connect(self._start_leverage)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.leverage_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.leverage_table = QTableWidget(0, 3)
        self.leverage_table.setHorizontalHeaderLabels(['匹配等级', '条数', '字数'])
        self.leverage_table.verticalHeader().setVisible(False)
        self.leverage_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.leverage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.leverage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.leverage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.leverage_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.leverage_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.leverage_table.setShowGrid(False)
        self.leverage_table.setAlternatingRowColors(True)
        self.leverage_table.setMinimumHeight(180)
        layout.addWidget(section('分析结果', self.leverage_table))

        export_row = QHBoxLayout()
        self.leverage_export_csv_btn = QPushButton('导出 CSV')
        self.leverage_export_csv_btn.setEnabled(False)
        self.leverage_export_csv_btn.setToolTip('导出待分析文件的每一句及其匹配等级')
        self.leverage_export_csv_btn.clicked.connect(self._export_leverage_csv)
        self.leverage_export_report_btn = QPushButton('导出报告…')
        self.leverage_export_report_btn.setEnabled(False)
        self.leverage_export_report_btn.setToolTip('导出为 HTML 或 PDF，适合给非技术干系人看')
        self.leverage_export_report_btn.clicked.connect(self._export_leverage_report)
        export_row.addWidget(self.leverage_export_csv_btn)
        export_row.addWidget(self.leverage_export_report_btn)
        export_row.addStretch(1)
        layout.addLayout(export_row)
        return tab

    def _build_compare_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)
        self.compare_list = QListWidget()
        self.compare_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.compare_list.setToolTip('要对比的 tmx/sdltm 文件，至少 2 个')
        list_layout.addWidget(self.compare_list)
        list_btn_row = QHBoxLayout()
        self.compare_add_btn = QPushButton('添加文件…')
        self.compare_add_btn.clicked.connect(self._browse_compare_inputs)
        self.compare_remove_btn = QPushButton('移除选中')
        self.compare_remove_btn.clicked.connect(self._remove_selected_compare_inputs)
        self.compare_clear_btn = QPushButton('清空')
        self.compare_clear_btn.clicked.connect(self.compare_list.clear)
        list_btn_row.addWidget(self.compare_add_btn)
        list_btn_row.addWidget(self.compare_remove_btn)
        list_btn_row.addWidget(self.compare_clear_btn)
        list_btn_row.addStretch(1)
        list_layout.addLayout(list_btn_row)
        layout.addWidget(section('选择要对比的文件（至少 2 个）', list_widget))

        self.compare_btn = QPushButton('开始对比')
        self.compare_btn.setObjectName('primaryButton')
        self.compare_btn.clicked.connect(self._start_compare)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.compare_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.compare_summary_label = QLabel('')
        self.compare_summary_label.setStyleSheet('color: #6B7280;')
        layout.addWidget(self.compare_summary_label)

        # Column count isn't fixed like leverage_table/stats_table's --
        # one column per file being compared, via _set_dynamic_table_rows()
        # -- so this starts empty and is shaped fresh on every run.
        self.compare_table = QTableWidget(0, 0)
        self.compare_table.verticalHeader().setVisible(False)
        self.compare_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.compare_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.compare_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.compare_table.setShowGrid(False)
        self.compare_table.setAlternatingRowColors(True)
        self.compare_table.setMinimumHeight(180)
        self.compare_table.setToolTip('有分歧的原文句段——同一句原文，不同文件里译文不一样')
        layout.addWidget(section('冲突明细', self.compare_table))

        export_row = QHBoxLayout()
        self.compare_export_csv_btn = QPushButton('导出冲突 CSV')
        self.compare_export_csv_btn.setEnabled(False)
        self.compare_export_csv_btn.clicked.connect(self._export_compare_csv)
        self.compare_export_report_btn = QPushButton('导出报告…')
        self.compare_export_report_btn.setEnabled(False)
        self.compare_export_report_btn.setToolTip('导出为 HTML 或 PDF，适合给非技术干系人看')
        self.compare_export_report_btn.clicked.connect(self._export_compare_report)
        export_row.addWidget(self.compare_export_csv_btn)
        export_row.addWidget(self.compare_export_report_btn)
        export_row.addStretch(1)
        layout.addLayout(export_row)
        return tab

    def _build_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_input_edit = QLineEdit()
        self.stats_input_edit.setPlaceholderText('选择要查看统计的 tmx/sdltm 文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_stats_input)
        file_layout.addWidget(self.stats_input_edit, 1)
        file_layout.addWidget(browse_btn)
        layout.addWidget(section('选择文件', file_row))

        self.stats_btn = QPushButton('查看统计')
        self.stats_btn.setObjectName('primaryButton')
        self.stats_btn.clicked.connect(self._start_stats)
        self.stats_export_report_btn = QPushButton('导出报告…')
        self.stats_export_report_btn.setEnabled(False)
        self.stats_export_report_btn.setToolTip('导出为 HTML 或 PDF，适合给非技术干系人看')
        self.stats_export_report_btn.clicked.connect(self._export_stats_report)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.stats_btn)
        btn_row.addWidget(self.stats_export_report_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(['指标', '数值'])
        self.stats_table.verticalHeader().setVisible(False)
        # Header text defaults to centered while QTableWidgetItem text
        # defaults to left-aligned -- with the value column stretched to
        # fill the window (long language-pair breakdown lines especially,
        # on a maximized window) that mismatch reads as messy. Left-align
        # both so the header sits directly above its column's content.
        self.stats_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.stats_table.setShowGrid(False)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setMinimumHeight(180)
        layout.addWidget(section('统计结果', self.stats_table))
        return tab

    def _set_stats_table_rows(self, rows):
        """``rows`` is a list of (label, value) string pairs -- kept as a
        plain list rather than the raw ``stats.compute()`` dict so this
        method (and the table it builds) stays presentation-only, with all
        the "what does this number mean" formatting decided by the caller.
        """
        self.stats_table.setRowCount(len(rows))
        for row, (label, value) in enumerate(rows):
            self.stats_table.setItem(row, 0, QTableWidgetItem(label))
            self.stats_table.setItem(row, 1, QTableWidgetItem(value))

    def _set_leverage_table_rows(self, rows):
        """Same shape/reasoning as ``_set_stats_table_rows``, one row per
        (band, count, words) triple.
        """
        self.leverage_table.setRowCount(len(rows))
        for row, (band, count, words) in enumerate(rows):
            self.leverage_table.setItem(row, 0, QTableWidgetItem(band))
            self.leverage_table.setItem(row, 1, QTableWidgetItem(count))
            self.leverage_table.setItem(row, 2, QTableWidgetItem(words))

    def _set_dynamic_table_rows(self, columns, rows):
        """Unlike ``_set_stats_table_rows``/``_set_leverage_table_rows``
        (fixed column count, set once at tab-build time), ``compare_table``'s
        column count depends on how many files were just compared -- so this
        reshapes the table itself (``setColumnCount``/header labels) on every
        call, not just its rows.
        """
        self.compare_table.setColumnCount(len(columns))
        self.compare_table.setHorizontalHeaderLabels(columns)
        self.compare_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.compare_table.setItem(r, c, QTableWidgetItem(str(value)))

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = LOG_COLORS.get(kind, LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))

    # ------------------------------------------------------- file dialogs
    def _browse_clean_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, CORPUS_FILTER)
        if path:
            self.clean_input_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_clean_output(self):
        path, _ = QFileDialog.getSaveFileName(self, '另存为', self._last_dir, _SAVE_FILTER)
        if path:
            self.clean_output_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_merge_inputs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件（可多选）', self._last_dir, CORPUS_FILTER)
        existing = {self.merge_list.item(i).text() for i in range(self.merge_list.count())}
        for path in paths:
            if path not in existing:
                self.merge_list.addItem(path)
        if paths:
            self._last_dir = os.path.dirname(paths[-1])

    def _remove_selected_merge_inputs(self):
        for item in self.merge_list.selectedItems():
            self.merge_list.takeItem(self.merge_list.row(item))

    def _browse_merge_output(self):
        path, _ = QFileDialog.getSaveFileName(self, '另存为', self._last_dir, _SAVE_FILTER)
        if path:
            self.merge_output_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_leverage_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, CORPUS_FILTER)
        if path:
            self.leverage_input_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_leverage_tm(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择参考 TM', self._last_dir, CORPUS_FILTER)
        if path:
            self.leverage_tm_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_compare_inputs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件（可多选）', self._last_dir, CORPUS_FILTER)
        existing = {self.compare_list.item(i).text() for i in range(self.compare_list.count())}
        for path in paths:
            if path not in existing:
                self.compare_list.addItem(path)
        if paths:
            self._last_dir = os.path.dirname(paths[-1])

    def _remove_selected_compare_inputs(self):
        for item in self.compare_list.selectedItems():
            self.compare_list.takeItem(self.compare_list.row(item))

    def _browse_stats_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, CORPUS_FILTER)
        if path:
            self.stats_input_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    # ---------------------------------------------------------- lifecycle
    def cleanup(self):
        """Called by ``main_window.py`` on a real window close. See
        ``toolbox.workers.wait_for_running()`` for why a page with a
        worker needs this -- this page has five separate ones (one per
        tab's action), any of which could be running when the window
        closes.
        """
        wait_for_running(
            self._clean_worker, self._merge_worker, self._leverage_worker,
            self._compare_worker, self._stats_worker)

    # ---------------------------------------------------------- settings
    def restore_settings(self):
        self.clean_chk_normalize.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'cleanNormalize', True))
        self.clean_chk_dedupe.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'cleanDedupe', True))
        self.clean_chk_remove_empty.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'cleanRemoveEmpty', True))
        self.clean_chk_remove_identical.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'cleanRemoveIdentical', False))
        idx = self.merge_strategy_combo.findData(
            settings.get_str(_SETTINGS_PREFIX + 'mergeStrategy', 'keep-all'))
        if idx >= 0:
            self.merge_strategy_combo.setCurrentIndex(idx)
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        settings.set_value(_SETTINGS_PREFIX + 'cleanNormalize', self.clean_chk_normalize.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'cleanDedupe', self.clean_chk_dedupe.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'cleanRemoveEmpty',
                            self.clean_chk_remove_empty.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'cleanRemoveIdentical',
                            self.clean_chk_remove_identical.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'mergeStrategy', self.merge_strategy_combo.currentData())
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)

    # ----------------------------------------------------------- clean
    def _validate_clean(self):
        input_path = self.clean_input_edit.text().strip()
        if not input_path:
            return '请先选择要清理的文件'
        if not os.path.exists(input_path):
            return '找不到这个文件，请重新选择'
        if not any((self.clean_chk_normalize.isChecked(), self.clean_chk_dedupe.isChecked(),
                    self.clean_chk_remove_empty.isChecked(), self.clean_chk_remove_identical.isChecked())):
            return '请至少勾选一项清理选项'
        return None

    def _start_clean(self):
        error = self._validate_clean()
        if error:
            self._log(error, 'error')
            return

        input_path = self.clean_input_edit.text().strip()
        output_path = self.clean_output_edit.text().strip() or input_path
        fn_kwargs = dict(
            input_path=input_path, output_path=output_path,
            normalize=self.clean_chk_normalize.isChecked(),
            dedupe=self.clean_chk_dedupe.isChecked(),
            remove_empty=self.clean_chk_remove_empty.isChecked(),
            remove_identical=self.clean_chk_remove_identical.isChecked(),
        )
        self.clean_btn.setEnabled(False)
        self._log('正在清理…')
        self._clean_worker = CallableWorker(lambda: _clean_job(**fn_kwargs), parent=self)
        self._clean_worker.finished_ok.connect(self._on_clean_ok)
        self._clean_worker.finished_err.connect(self._on_clean_err)
        self._clean_worker.start()

    def _on_clean_ok(self, report):
        self.clean_btn.setEnabled(True)
        self._log(
            '清理完成：%d 条 -> %d 条（去重 %d，去空段 %d，去原文=译文 %d，标准化 %d 条）'
            % (report['input'], report['output'], report['removed_duplicate'],
               report['removed_empty'], report['removed_identical'], report['normalized']),
            'success')
        self._log('已保存到 %s' % report['output_path'])

    def _on_clean_err(self, message):
        self.clean_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    # ----------------------------------------------------------- merge
    def _validate_merge(self):
        if self.merge_list.count() == 0:
            return '请先添加要合并的文件'
        if not self.merge_output_edit.text().strip():
            return '请指定合并结果的保存位置'
        return None

    def _start_merge(self):
        error = self._validate_merge()
        if error:
            self._log(error, 'error')
            return

        input_paths = [self.merge_list.item(i).text() for i in range(self.merge_list.count())]
        output_path = self.merge_output_edit.text().strip()
        strategy = self.merge_strategy_combo.currentData()
        fn_kwargs = dict(input_paths=input_paths, output_path=output_path, strategy=strategy)

        self.merge_btn.setEnabled(False)
        self._log('正在合并 %d 个文件…' % len(input_paths))
        self._merge_worker = CallableWorker(lambda: _merge_job(**fn_kwargs), parent=self)
        self._merge_worker.finished_ok.connect(self._on_merge_ok)
        self._merge_worker.finished_err.connect(self._on_merge_err)
        self._merge_worker.start()

    def _on_merge_ok(self, report):
        self.merge_btn.setEnabled(True)
        self._log(
            '合并完成：%d 条 -> %d 条（策略：%s，解决冲突 %d 处）'
            % (report['input'], report['output'], report['strategy'], report['conflicts_resolved']),
            'success')
        self._log('已保存到 %s' % report['output_path'])

    def _on_merge_err(self, message):
        self.merge_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    # ------------------------------------------------------- report export
    def _start_export_report(self, report, default_name):
        """Shared by leverage/compare: opens a save dialog restricted to
        the two ``language_tools.reports.render`` formats and dispatches
        by whichever the user picked, via ``report_render.write()`` (same
        extension-dispatch ``tmtool``'s own ``--report`` flag uses).
        """
        path, selected_filter = QFileDialog.getSaveFileName(
            self, '导出报告', os.path.join(self._last_dir, default_name), _REPORT_FILTER)
        if not path:
            return
        if '.' not in os.path.basename(path):
            path += '.pdf' if 'PDF' in selected_filter else '.html'
        self._last_dir = os.path.dirname(path)
        try:
            report_render.write(path, report)
        except (ValueError, ImportError) as e:
            self._log('出错了：%s' % e, 'error')
            return
        self._log('已导出报告到 %s' % path, 'success')

    # -------------------------------------------------------- leverage
    def _validate_leverage(self):
        candidate_path = self.leverage_input_edit.text().strip()
        tm_path = self.leverage_tm_edit.text().strip()
        if not candidate_path:
            return '请先选择要分析的文件'
        if not os.path.exists(candidate_path):
            return '找不到这个文件，请重新选择'
        if not tm_path:
            return '请选择参考 TM'
        if not os.path.exists(tm_path):
            return '找不到参考 TM 文件，请重新选择'
        return None

    def _start_leverage(self):
        self._leverage_units = None
        self._set_leverage_table_rows([])
        self.leverage_export_csv_btn.setEnabled(False)
        self.leverage_export_report_btn.setEnabled(False)

        error = self._validate_leverage()
        if error:
            self._log(error, 'error')
            return

        candidate_path = self.leverage_input_edit.text().strip()
        tm_path = self.leverage_tm_edit.text().strip()
        self.leverage_btn.setEnabled(False)
        self._log('正在分析…')
        self._leverage_worker = CallableWorker(
            lambda: _leverage_job(candidate_path, tm_path), parent=self)
        self._leverage_worker.finished_ok.connect(self._on_leverage_ok)
        self._leverage_worker.finished_err.connect(self._on_leverage_err)
        self._leverage_worker.start()

    def _on_leverage_ok(self, candidate_units):
        self.leverage_btn.setEnabled(True)
        self._leverage_units = candidate_units
        s = leverage_module.summarize(candidate_units)
        rows = [(band, str(s['bands'][band]['count']), str(s['bands'][band]['words']))
                for band in leverage_module.BANDS]
        self._set_leverage_table_rows(rows)
        self.leverage_export_csv_btn.setEnabled(bool(candidate_units))
        self.leverage_export_report_btn.setEnabled(bool(candidate_units))
        self._log('分析完成：共 %d 句，%d 字' % (s['total'], s['total_words']), 'success')

    def _on_leverage_err(self, message):
        self.leverage_btn.setEnabled(True)
        self._set_leverage_table_rows([])
        self._log('出错了：%s' % message, 'error')

    def _export_leverage_csv(self):
        if not self._leverage_units:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', self._last_dir, _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        self._last_dir = os.path.dirname(path)
        src_lang, tgt_lang = tm_io.infer_langs(self._leverage_units)
        csv_writer.write(path, self._leverage_units, src_lang or 'SRC', tgt_lang or 'TGT',
                          include_leverage=True)
        self._log('已导出到 %s' % path, 'success')

    def _export_leverage_report(self):
        if not self._leverage_units:
            return
        s = leverage_module.summarize(self._leverage_units)
        self._start_export_report(report_adapters.from_leverage_summary(s), '杠杆分析报告')

    # --------------------------------------------------------- compare
    def _validate_compare(self):
        if self.compare_list.count() < 2:
            return '请至少添加 2 个文件'
        return None

    def _start_compare(self):
        self._compare_report = None
        self.compare_summary_label.setText('')
        self._set_dynamic_table_rows([], [])
        self.compare_export_csv_btn.setEnabled(False)
        self.compare_export_report_btn.setEnabled(False)

        error = self._validate_compare()
        if error:
            self._log(error, 'error')
            return

        input_paths = [self.compare_list.item(i).text() for i in range(self.compare_list.count())]
        self.compare_btn.setEnabled(False)
        self._log('正在对比 %d 个文件…' % len(input_paths))
        self._compare_worker = CallableWorker(lambda: _compare_job(input_paths), parent=self)
        self._compare_worker.finished_ok.connect(self._on_compare_ok)
        self._compare_worker.finished_err.connect(self._on_compare_err)
        self._compare_worker.start()

    def _on_compare_ok(self, report):
        self.compare_btn.setEnabled(True)
        self._compare_report = report
        self.compare_summary_label.setText(
            '共 %d 个文件，%d 处一致，%d 处冲突'
            % (len(report['labels']), report['shared_segments'], len(report['conflicts'])))
        columns = ['原文'] + report['labels']
        rows = [[entry['src']] + [';'.join(entry['labels'].get(label, [])) for label in report['labels']]
                for entry in report['conflicts']]
        self._set_dynamic_table_rows(columns, rows)
        self.compare_export_csv_btn.setEnabled(bool(report['conflicts']))
        self.compare_export_report_btn.setEnabled(True)
        self._log('对比完成', 'success')

    def _on_compare_err(self, message):
        self.compare_btn.setEnabled(True)
        self._set_dynamic_table_rows([], [])
        self._log('出错了：%s' % message, 'error')

    def _export_compare_csv(self):
        if not self._compare_report or not self._compare_report['conflicts']:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出冲突 CSV', self._last_dir, _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        self._last_dir = os.path.dirname(path)
        compare_module.write_conflicts_csv(path, self._compare_report)
        self._log('已导出到 %s' % path, 'success')

    def _export_compare_report(self):
        if not self._compare_report:
            return
        self._start_export_report(report_adapters.from_compare_report(self._compare_report), '对比报告')

    # ----------------------------------------------------------- stats
    def _validate_stats(self):
        input_path = self.stats_input_edit.text().strip()
        if not input_path:
            return '请先选择要查看统计的文件'
        if not os.path.exists(input_path):
            return '找不到这个文件，请重新选择'
        return None

    def _start_stats(self):
        self._set_stats_table_rows([])
        self._last_stats = None
        self.stats_export_report_btn.setEnabled(False)
        error = self._validate_stats()
        if error:
            self._log(error, 'error')
            return

        input_path = self.stats_input_edit.text().strip()
        self.stats_btn.setEnabled(False)
        self._log('正在统计…')
        self._stats_worker = CallableWorker(lambda: _stats_job(input_path), parent=self)
        self._stats_worker.finished_ok.connect(self._on_stats_ok)
        self._stats_worker.finished_err.connect(self._on_stats_err)
        self._stats_worker.start()

    def _on_stats_ok(self, s):
        self.stats_btn.setEnabled(True)
        self._last_stats = s
        self.stats_export_report_btn.setEnabled(True)
        rows = [
            ('总条数', str(s['total'])),
            ('去重后条数', str(s['unique_pairs'])),
            ('重复条目', '%d（%.1f%%）' % (s['duplicate_pairs'], s['duplicate_rate'] * 100)),
            ('空原文', str(s['empty_source'])),
            ('空译文', str(s['empty_target'])),
            ('原文/译文长度比', '%.3f' % s['length_ratio']),
        ]
        for pair, count in sorted(s['lang_pairs'].items()):
            rows.append(('语言对 %s' % pair, '%d 条' % count))
        for year, count in sorted(s['aging'].items()):
            rows.append(('更新年份 %s' % ('未知' if year == 'unknown' else year), '%d 条' % count))
        for pair in sorted(s['lang_pair_by_domain']):
            for domain, count in sorted(s['lang_pair_by_domain'][pair].items()):
                rows.append(('%s / %s' % (pair, domain), '%d 条' % count))
        self._set_stats_table_rows(rows)
        self._log('统计完成', 'success')

    def _on_stats_err(self, message):
        self.stats_btn.setEnabled(True)
        self._set_stats_table_rows([])
        self._log('出错了：%s' % message, 'error')

    def _export_stats_report(self):
        if not self._last_stats:
            return
        self._start_export_report(report_adapters.from_stats_summary(self._last_stats), '语料统计报告')
