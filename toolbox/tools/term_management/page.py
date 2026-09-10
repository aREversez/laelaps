"""The term-management tool's page (DESIGN.md section 15.1, Phase G2):
maintain a bilingual glossary (csv/xlsx) and check an existing corpus
(tmx/sdltm) against it for forbidden translations.

Two tabs, same ``QTabWidget`` shape as ``tm_maintenance/page.py``:

- 术语库: CRUD over a glossary file. Additions/edits go through
  ``_TermEntryDialog`` (a modal add/edit form), NOT inline QTableWidgetItem
  editing -- same "data changes, rebuild the table" pattern as
  ``tm_maintenance``'s ``_set_stats_table_rows`` (see that method's
  docstring), chosen here for an extra reason specific to a form: a modal
  dialog validates (non-empty src/tgt term) before anything is written
  back, where an inline-edited cell has no equivalent checkpoint and would
  need its own ``itemChanged`` validation/rollback plumbing for the same
  guarantee. Glossary language pair is page-level (two compact combos),
  not per-row -- see ``language_tools/terms/glossary.py``'s docstring for
  why a glossary file doesn't store it per row.
- 一致性检查: pick a TM (tmx/sdltm) + a glossary file, run
  ``language_tools.terms.check.run()``, browse/export results. Deliberately
  mirrors ``qa_check/page.py`` almost line for line (file picker ->
  primary button -> summary label -> filter checkbox -> results table ->
  export button -> shared log) -- it's the same shape of task (run a
  check against an existing corpus, let the user narrow/export what came
  back), so reusing that page's proven layout instead of inventing a new
  one is the right call. The one structural difference: no issue-*type*
  filter dropdown, because a term hit doesn't have a fixed enumerable code
  the way ``qa.py``'s issues do (a hit names its own glossary entry) --
  just "只显示有问题的条目".

Same conventions as the other three tools: ``section()``/``CallableWorker``
(``toolbox.widgets``/``toolbox.workers``), ``compact_combo()``/
``labeled_field()`` for the inline language-pair row (``toolbox.widgets``,
promoted there once a third tool -- this one -- needed them; see that
module's docstring), ``objectName('primaryButton')``/``objectName('logConsole')``.
"""
import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from language_tools.terms import check as term_check_module
from language_tools.terms import glossary as glossary_module
from language_tools.terms.model import STATUSES, TermEntry
from language_tools.tm import io as tm_io
from language_tools.writers import csv_writer
from toolbox.widgets import LANG_TOOLTIP, compact_combo, labeled_field, lang_combo_code
from toolbox.widgets import make_lang_combo, section
from toolbox.workers import CallableWorker

_GLOSSARY_FILTER = 'Glossary files (*.csv *.xlsx)'
_CORPUS_FILTER = 'Corpus files (*.tmx *.sdltm)'
_CSV_FILTER = 'CSV (*.csv)'

_LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

_STATUS_LABELS = {'approved': '推荐译法', 'forbidden': '禁用译法'}
_STATUS_TOOLTIPS = {
    'approved': '标准/推荐译法。v1 暂不据此检查译文（详见 DESIGN.md 15.1）',
    'forbidden': '明确禁止的错误译法——一致性检查只看这一档：原文出现这个词，且译文出现这个禁用译法，就标记出来',
}


def _check_job(corpus_path, glossary_path, src_lang, tgt_lang):
    units = tm_io.read_corpus(corpus_path)
    entries = glossary_module.read(glossary_path, src_lang, tgt_lang)
    return term_check_module.run(units, entries)


def _format_term_hit(hit):
    text = '%s→%s' % (hit['src_term'], hit['tgt_term'])
    return '%s（%s）' % (text, hit['note']) if hit.get('note') else text


class _TermEntryDialog(QDialog):
    """Modal add/edit form for one glossary entry -- see this module's
    docstring for why entry_table doesn't do inline cell editing instead.
    """

    def __init__(self, parent=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle('编辑术语条目' if entry else '添加术语条目')
        self.setMinimumWidth(320)
        form = QFormLayout(self)

        self.src_term_edit = QLineEdit(entry.src_term if entry else '')
        self.tgt_term_edit = QLineEdit(entry.tgt_term if entry else '')
        self.status_combo = QComboBox()
        for status in STATUSES:
            self.status_combo.addItem(_STATUS_LABELS[status], status)
            self.status_combo.setItemData(
                self.status_combo.count() - 1, _STATUS_TOOLTIPS[status], Qt.ToolTipRole)
        if entry is not None:
            idx = self.status_combo.findData(entry.status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
        self.domain_edit = QLineEdit(entry.domain if entry and entry.domain else '')
        self.note_edit = QLineEdit(entry.note if entry and entry.note else '')

        self.error_label = QLabel('')
        self.error_label.setStyleSheet('color: #B23B3B;')
        self.error_label.setVisible(False)

        form.addRow('原文术语', self.src_term_edit)
        form.addRow('译文术语', self.tgt_term_edit)
        form.addRow('状态', self.status_combo)
        form.addRow('领域（可选）', self.domain_edit)
        form.addRow('备注（可选）', self.note_edit)
        form.addRow(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self):
        if not self.src_term_edit.text().strip() or not self.tgt_term_edit.text().strip():
            self.error_label.setText('原文术语和译文术语都不能为空')
            self.error_label.setVisible(True)
            return
        self.accept()

    def result_values(self):
        return {
            'src_term': self.src_term_edit.text().strip(),
            'tgt_term': self.tgt_term_edit.text().strip(),
            'status': self.status_combo.currentData(),
            'domain': self.domain_edit.text().strip() or None,
            'note': self.note_edit.text().strip() or None,
        }


class TermManagementPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []           # currently-loaded/edited glossary, in memory
        self._glossary_path = None   # None until opened/saved once
        self._last_units = None      # last consistency-check result
        self._check_worker = None
        self._export_worker = None
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('术语管理')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('维护双语术语表，并对照已有翻译记忆库检查禁用译法')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_glossary_tab(), '术语库')
        self.tabs.addTab(self._build_check_tab(), '一致性检查')
        outer.addWidget(self.tabs)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(90)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText('操作结果会显示在这里')
        outer.addWidget(self.log)

    # ------------------------------------------------------- glossary tab
    def _build_glossary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(10)

        lang_row = QHBoxLayout()
        self.glossary_src_lang = make_lang_combo('en-US')
        self.glossary_tgt_lang = make_lang_combo('zh-CN')
        self.glossary_src_lang.setToolTip(LANG_TOOLTIP)
        self.glossary_tgt_lang.setToolTip(LANG_TOOLTIP)
        compact_combo(self.glossary_src_lang)
        compact_combo(self.glossary_tgt_lang)
        lang_row.addLayout(labeled_field('原文语言', self.glossary_src_lang))
        lang_row.addLayout(labeled_field('译文语言', self.glossary_tgt_lang))
        lang_row.addStretch(1)
        file_layout.addLayout(lang_row)

        btn_row = QHBoxLayout()
        self.glossary_path_label = QLabel('未打开文件（当前为新建）')
        self.glossary_path_label.setStyleSheet('color: #6B7280;')
        open_btn = QPushButton('打开…')
        open_btn.clicked.connect(self._open_glossary)
        self.glossary_save_btn = QPushButton('保存')
        self.glossary_save_btn.setEnabled(False)
        self.glossary_save_btn.clicked.connect(self._save_glossary)
        save_as_btn = QPushButton('另存为…')
        save_as_btn.clicked.connect(self._save_glossary_as)
        btn_row.addWidget(self.glossary_path_label, 1)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(self.glossary_save_btn)
        btn_row.addWidget(save_as_btn)
        file_layout.addLayout(btn_row)

        layout.addWidget(section('术语库文件', file_widget))

        entry_btn_row = QHBoxLayout()
        add_btn = QPushButton('添加…')
        add_btn.clicked.connect(self._add_entry)
        self.edit_entry_btn = QPushButton('编辑所选…')
        self.edit_entry_btn.clicked.connect(self._edit_selected_entry)
        self.remove_entry_btn = QPushButton('删除所选')
        self.remove_entry_btn.clicked.connect(self._remove_selected_entries)
        entry_btn_row.addWidget(add_btn)
        entry_btn_row.addWidget(self.edit_entry_btn)
        entry_btn_row.addWidget(self.remove_entry_btn)
        entry_btn_row.addStretch(1)
        layout.addLayout(entry_btn_row)

        self.entry_table = QTableWidget(0, 5)
        self.entry_table.setHorizontalHeaderLabels(['原文术语', '译文术语', '状态', '领域', '备注'])
        self.entry_table.verticalHeader().setVisible(False)
        header = self.entry_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.entry_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.entry_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.entry_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.entry_table.setShowGrid(False)
        self.entry_table.setAlternatingRowColors(True)
        layout.addWidget(section('术语条目', self.entry_table), 1)
        return tab

    def _refresh_entry_table(self):
        self.entry_table.setRowCount(len(self._entries))
        for row, e in enumerate(self._entries):
            self.entry_table.setItem(row, 0, QTableWidgetItem(e.src_term))
            self.entry_table.setItem(row, 1, QTableWidgetItem(e.tgt_term))
            self.entry_table.setItem(row, 2, QTableWidgetItem(_STATUS_LABELS.get(e.status, e.status)))
            self.entry_table.setItem(row, 3, QTableWidgetItem(e.domain or ''))
            self.entry_table.setItem(row, 4, QTableWidgetItem(e.note or ''))

    def _add_entry(self):
        dialog = _TermEntryDialog(self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.result_values()
            self._entries.append(TermEntry(
                src_lang=lang_combo_code(self.glossary_src_lang),
                tgt_lang=lang_combo_code(self.glossary_tgt_lang), **values))
            self._refresh_entry_table()
            self._log('已添加：%s → %s' % (values['src_term'], values['tgt_term']))

    def _selected_entry_rows(self):
        return sorted({idx.row() for idx in self.entry_table.selectedIndexes()})

    def _edit_selected_entry(self):
        rows = self._selected_entry_rows()
        if len(rows) != 1:
            self._log('请先选中一条要编辑的术语（只能选一条）', 'error')
            return
        row = rows[0]
        dialog = _TermEntryDialog(self, entry=self._entries[row])
        if dialog.exec() == QDialog.Accepted:
            values = dialog.result_values()
            entry = self._entries[row]
            self._entries[row] = TermEntry(
                src_lang=entry.src_lang, tgt_lang=entry.tgt_lang, **values)
            self._refresh_entry_table()
            self._log('已更新：%s → %s' % (values['src_term'], values['tgt_term']))

    def _remove_selected_entries(self):
        rows = self._selected_entry_rows()
        if not rows:
            self._log('请先选中要删除的术语', 'error')
            return
        for row in reversed(rows):
            del self._entries[row]
        self._refresh_entry_table()
        self._log('已删除 %d 条术语' % len(rows))

    def _open_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开术语库', '', _GLOSSARY_FILTER)
        if not path:
            return
        try:
            entries = glossary_module.read(
                path, lang_combo_code(self.glossary_src_lang),
                lang_combo_code(self.glossary_tgt_lang))
        except ValueError as e:
            self._log('打开失败：%s' % e, 'error')
            return
        self._entries = entries
        self._glossary_path = path
        self.glossary_path_label.setText(path)
        self.glossary_save_btn.setEnabled(True)
        self._refresh_entry_table()
        self._log('已打开 %s，共 %d 条术语' % (path, len(entries)), 'success')

    def _save_glossary(self):
        if not self._glossary_path:
            self._save_glossary_as()
            return
        self._write_glossary(self._glossary_path)

    def _save_glossary_as(self):
        path, _ = QFileDialog.getSaveFileName(self, '另存为', '', _GLOSSARY_FILTER)
        if not path:
            return
        if not (path.lower().endswith('.csv') or path.lower().endswith('.xlsx')):
            path += '.csv'
        self._write_glossary(path)

    def _write_glossary(self, path):
        try:
            glossary_module.write(path, self._entries)
        except ValueError as e:
            self._log('保存失败：%s' % e, 'error')
            return
        self._glossary_path = path
        self.glossary_path_label.setText(path)
        self.glossary_save_btn.setEnabled(True)
        self._log('已保存到 %s' % path, 'success')

    # --------------------------------------------------------- check tab
    def _build_check_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(10)

        corpus_row = QWidget()
        corpus_layout = QHBoxLayout(corpus_row)
        corpus_layout.setContentsMargins(0, 0, 0, 0)
        self.check_corpus_edit = QLineEdit()
        self.check_corpus_edit.setPlaceholderText('选择要检查的 tmx/sdltm 文件…')
        corpus_browse_btn = QPushButton('浏览…')
        corpus_browse_btn.clicked.connect(self._browse_check_corpus)
        corpus_layout.addWidget(self.check_corpus_edit, 1)
        corpus_layout.addWidget(corpus_browse_btn)
        file_layout.addLayout(labeled_field('翻译记忆库', corpus_row))

        glossary_row = QWidget()
        glossary_layout = QHBoxLayout(glossary_row)
        glossary_layout.setContentsMargins(0, 0, 0, 0)
        self.check_glossary_edit = QLineEdit()
        self.check_glossary_edit.setPlaceholderText('选择术语库文件（csv/xlsx）…')
        glossary_browse_btn = QPushButton('浏览…')
        glossary_browse_btn.clicked.connect(self._browse_check_glossary)
        glossary_layout.addWidget(self.check_glossary_edit, 1)
        glossary_layout.addWidget(glossary_browse_btn)
        file_layout.addLayout(labeled_field('术语库', glossary_row))

        layout.addWidget(section('选择文件', file_widget))

        action_row = QHBoxLayout()
        self.check_btn = QPushButton('开始检查')
        self.check_btn.setObjectName('primaryButton')
        self.check_btn.clicked.connect(self._start_check)
        self.check_export_btn = QPushButton('导出 CSV…')
        self.check_export_btn.setEnabled(False)
        self.check_export_btn.setToolTip('导出全部条目（含未标记问题的），不受下面的筛选影响')
        self.check_export_btn.clicked.connect(self._start_export)
        action_row.addWidget(self.check_btn)
        action_row.addWidget(self.check_export_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.check_summary_label = QLabel('')
        self.check_summary_label.setStyleSheet('color: #4B5262;')
        layout.addWidget(self.check_summary_label)

        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self.check_hide_clean_chk = QCheckBox('只显示有问题的条目')
        self.check_hide_clean_chk.setChecked(True)
        self.check_hide_clean_chk.stateChanged.connect(self._refresh_check_table)
        filter_layout.addWidget(self.check_hide_clean_chk)
        filter_layout.addStretch(1)
        layout.addWidget(section('筛选', filter_row))

        self.check_table = QTableWidget(0, 4)
        self.check_table.setHorizontalHeaderLabels(['#', '原文', '译文', '命中的禁用译法'])
        self.check_table.verticalHeader().setVisible(False)
        header = self.check_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.check_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.check_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.check_table.setShowGrid(False)
        self.check_table.setAlternatingRowColors(True)
        layout.addWidget(section('检查结果', self.check_table), 1)
        return tab

    def _browse_check_corpus(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _CORPUS_FILTER)
        if path:
            self.check_corpus_edit.setText(path)

    def _browse_check_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _GLOSSARY_FILTER)
        if path:
            self.check_glossary_edit.setText(path)

    def _validate_check(self):
        corpus_path = self.check_corpus_edit.text().strip()
        glossary_path = self.check_glossary_edit.text().strip()
        if not corpus_path:
            return '请先选择要检查的翻译记忆库文件'
        if not os.path.exists(corpus_path):
            return '找不到翻译记忆库文件，请重新选择'
        if not glossary_path:
            return '请先选择术语库文件'
        if not os.path.exists(glossary_path):
            return '找不到术语库文件，请重新选择'
        return None

    def _start_check(self):
        self._last_units = None
        self.check_table.setRowCount(0)
        self.check_summary_label.setText('')
        self.check_export_btn.setEnabled(False)

        error = self._validate_check()
        if error:
            self._log(error, 'error')
            return

        corpus_path = self.check_corpus_edit.text().strip()
        glossary_path = self.check_glossary_edit.text().strip()
        self.check_btn.setEnabled(False)
        self._log('正在检查…')
        self._check_worker = CallableWorker(
            lambda: _check_job(corpus_path, glossary_path,
                                lang_combo_code(self.glossary_src_lang),
                                lang_combo_code(self.glossary_tgt_lang)),
            parent=self)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.finished_err.connect(self._on_check_err)
        self._check_worker.start()

    def _on_check_ok(self, units):
        self.check_btn.setEnabled(True)
        self._last_units = units
        s = term_check_module.summarize(units)
        rate = (s['flagged'] / s['total'] * 100) if s['total'] else 0.0
        self.check_summary_label.setText(
            '共 %d 条，%d 条命中禁用译法（%.1f%%）' % (s['total'], s['flagged'], rate))
        self.check_export_btn.setEnabled(bool(units))
        self._refresh_check_table()
        self._log('检查完成', 'success')

    def _on_check_err(self, message):
        self.check_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    def _refresh_check_table(self):
        self.check_table.setRowCount(0)
        if not self._last_units:
            return
        hide_clean = self.check_hide_clean_chk.isChecked()
        rows = [(i, u) for i, u in enumerate(self._last_units, 1)
                if not hide_clean or u.meta.get('term_issues')]
        self.check_table.setRowCount(len(rows))
        for row, (i, u) in enumerate(rows):
            hits = u.meta.get('term_issues', [])
            hit_text = '、'.join(_format_term_hit(h) for h in hits) if hits else '-'
            self.check_table.setItem(row, 0, QTableWidgetItem(str(i)))
            self.check_table.setItem(row, 1, QTableWidgetItem(u.src_text))
            self.check_table.setItem(row, 2, QTableWidgetItem(u.tgt_text))
            self.check_table.setItem(row, 3, QTableWidgetItem(hit_text))

    def _start_export(self):
        if not self._last_units:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', '', _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'

        units = self._last_units
        src_lang, tgt_lang = tm_io.infer_langs(units)
        self.check_export_btn.setEnabled(False)
        self._log('正在导出…')
        self._export_worker = CallableWorker(
            lambda: csv_writer.write(path, units, src_lang or 'SRC', tgt_lang or 'TGT',
                                      include_terms=True),
            parent=self)
        self._export_worker.finished_ok.connect(lambda _=None: self._on_export_ok(path))
        self._export_worker.finished_err.connect(self._on_export_err)
        self._export_worker.start()

    def _on_export_ok(self, path):
        self.check_export_btn.setEnabled(True)
        self._log('已导出到 %s' % path, 'success')

    def _on_export_err(self, message):
        self.check_export_btn.setEnabled(True)
        self._log('导出失败：%s' % message, 'error')

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = _LOG_COLORS.get(kind, _LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))
