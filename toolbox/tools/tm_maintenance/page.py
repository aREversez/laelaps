"""The TM-maintenance tool's page: three tabs (clean/merge/stats), each a
thin form wrapping ``language_tools.tm.*`` directly -- same "no HTTP
layer, just import and call the library" shape as
``corpus_convert/page.py``, and the same ``QThread`` pattern
(``toolbox.workers.CallableWorker``) so a large TM doesn't freeze the UI
while it's being processed.

Unlike ``ConvertWorker`` (specific to ``api.convert()``'s kwargs shape),
``CallableWorker`` is a generic "run this zero-arg callable off the UI
thread" wrapper -- shared across all three tabs, since none of
clean/merge/stats needs a specialized ``run()`` body, just a function call
that shouldn't block. Each tab wires its own callable (``_clean_job``/
``_merge_job``/``_stats_job``, module-level so they're callable/testable
without a QWidget) plus its own start/success/error handlers.

Copy and layout conventions follow ``corpus_convert/page.py`` (see that
file's docstring for the reasoning): short section titles, explanation in
tooltips, ``section()`` (from ``toolbox.widgets``) for headers,
``objectName('primaryButton')`` for the action button,
``objectName('logConsole')`` for output -- shared here across all three
tabs rather than one log per tab, so the user has a single place to look
regardless of which action they just ran.

The stats tab is the one exception to "results go in the log": stats
produces several distinct numbers at once (total, dedup rate, empty
counts, per-language-pair breakdown), which reads as a wall of text in a
scrolling console and is hard to scan back to after the fact -- so it
gets its own ``QTableWidget`` instead, populated fresh on every run
(``_set_stats_table_rows``). Clean/merge stay log-based: each produces
one outcome (how many were removed/merged), which a single log line
already states clearly.
"""
import html
import os

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCheckBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from language_tools.tm import clean as clean_module
from language_tools.tm import io as tm_io
from language_tools.tm import merge as merge_module
from language_tools.tm import stats as stats_module
from toolbox.widgets import compact_combo, labeled_field, section
from toolbox.workers import CallableWorker

_CORPUS_FILTER = 'Corpus files (*.tmx *.sdltm)'
_SAVE_FILTER = 'TMX (*.tmx);;SDLTM (*.sdltm)'

_LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

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


class TmMaintenancePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._clean_worker = None
        self._merge_worker = None
        self._stats_worker = None
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('语料维护')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('清理、合并、统计翻译记忆库文件（tmx/sdltm）')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_clean_tab(), '清理')
        self.tabs.addTab(self._build_merge_tab(), '合并')
        self.tabs.addTab(self._build_stats_tab(), '统计')
        outer.addWidget(self.tabs)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setPlaceholderText('操作结果会显示在这里')
        outer.addWidget(self.log, 1)

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
        layout.addStretch(1)
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
        layout.addStretch(1)
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
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.stats_btn)
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
        layout.addWidget(section('统计结果', self.stats_table), 1)
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

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = _LOG_COLORS.get(kind, _LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))

    # ------------------------------------------------------- file dialogs
    def _browse_clean_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _CORPUS_FILTER)
        if path:
            self.clean_input_edit.setText(path)

    def _browse_clean_output(self):
        path, _ = QFileDialog.getSaveFileName(self, '另存为', '', _SAVE_FILTER)
        if path:
            self.clean_output_edit.setText(path)

    def _browse_merge_inputs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择文件（可多选）', '', _CORPUS_FILTER)
        existing = {self.merge_list.item(i).text() for i in range(self.merge_list.count())}
        for path in paths:
            if path not in existing:
                self.merge_list.addItem(path)

    def _remove_selected_merge_inputs(self):
        for item in self.merge_list.selectedItems():
            self.merge_list.takeItem(self.merge_list.row(item))

    def _browse_merge_output(self):
        path, _ = QFileDialog.getSaveFileName(self, '另存为', '', _SAVE_FILTER)
        if path:
            self.merge_output_edit.setText(path)

    def _browse_stats_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _CORPUS_FILTER)
        if path:
            self.stats_input_edit.setText(path)

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
        self._set_stats_table_rows(rows)
        self._log('统计完成', 'success')

    def _on_stats_err(self, message):
        self.stats_btn.setEnabled(True)
        self._set_stats_table_rows([])
        self._log('出错了：%s' % message, 'error')
