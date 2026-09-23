"""The term-management tool's page (DESIGN.md section 15.1, Phase G2):
maintain a bilingual glossary (csv/xlsx) and check an existing corpus
(tmx/sdltm) against it for forbidden translations.

Two tabs, same ``QTabWidget`` shape as ``tm_maintenance/page.py``:

- 术语库: CRUD over a glossary file. Additions/edits go through
  ``_TermEntryDialog`` (a modal add/edit form, reachable via the entry
  table's right-click menu -- 添加/编辑/删除 all live there, no separate
  toolbar buttons for any of the three -- or by double-clicking a row to
  edit it), NOT inline QTableWidgetItem editing -- same "data changes,
  rebuild the table" pattern as ``tm_maintenance``'s
  ``_set_stats_table_rows`` (see that method's docstring), chosen here
  for an extra reason specific to a form: a modal dialog validates
  (non-empty src/tgt term) before anything is written back, where an
  inline-edited cell has no equivalent checkpoint and would need its own
  ``itemChanged`` validation/rollback plumbing for the same guarantee.
  Glossary language pair is page-level (two compact combos), not per-row
  -- see ``language_tools/terms/glossary.py``'s docstring for why a
  glossary file doesn't store it per row.
- 一致性检查: pick a TM (tmx/sdltm) + a glossary file, run
  ``language_tools.terms.check.run()``, browse/export results. Deliberately
  mirrors ``qa_check/page.py`` almost line for line (file picker ->
  primary button -> summary label -> filter row + table folded into one
  "检查结果" section -> export buttons (CSV + HTML/PDF summary report,
  same ``language_tools.reports`` path as qa_check's 导出报告) -> shared
  log) -- it's the same
  shape of task (run a check against an existing corpus, let the user
  narrow/export what came back), so reusing that page's proven layout
  instead of inventing a new one is the right call. The one structural
  difference: no issue-*type* filter dropdown, because a term hit doesn't
  have a fixed enumerable code the way ``qa.py``'s issues do (a hit names
  its own glossary entry) -- just "只显示有问题的条目".

术语库文件 section layout: 打开/关闭/保存/另存为 sit together on their own
button row, with the current path shown on the line below rather than
inline with the buttons. An earlier version put the path label first
(stretched to fill the row) and the buttons after -- which pushed all
four buttons to the far right edge, reading as lopsided rather than as a
single coherent toolbar. Buttons together, path underneath, matches how
most desktop apps lay out a file-action bar.

Unsaved-changes tracking: ``has_unsaved_changes()``/``save_unsaved_
changes()``/``unsaved_changes_label()`` are a convention ``MainWindow.
closeEvent()`` looks for on every tool page via ``getattr(..., None)``
(not an ABC/Protocol -- see that method's docstring for why a soft
convention, not an enforced interface, is the right amount of coupling
for something only one page currently implements). ``_dirty`` flips true
on any entry add/edit/remove, false again after a successful open/save/
close -- mirrors it against the in-memory ``_entries`` list, not against
the table widget, since the table is a derived view rebuilt from
``_entries`` (see ``_refresh_entry_table()``), not a source of truth
itself. ``_close_glossary()`` (关闭 button) is the same prompt-then-act
flow as a window close with unsaved changes, just scoped to this one
file instead of the whole app -- see ``_prompt_save_before_discard()``.

File-in-use detection (``language_tools.terms.filelock``, see that
module's docstring for what it can and can't actually detect and why an
earlier sidecar-file-based version of this was replaced after real
testing showed it didn't actually protect against WPS/Office at all):
opening a glossary checks for Office/WPS's own lock marker first (warn,
don't block -- best-effort) and then tries to acquire a lock on the real
file (block outright on failure). The held lock moves with
``_glossary_path``: released on open of a different file, transferred to
a new path on save-as, released in ``cleanup()`` (called by
``MainWindow.closeEvent()``) and in ``_close_glossary()``, so neither a
normal app exit nor closing the file mid-session leaves a stale lock
behind. Saving while a lock is held on the very file being written to
goes through ``FileLock.write_around()`` (see that method's docstring for
why a direct write would self-block on Windows).

Same conventions as the other three tools: ``section()``/``CallableWorker``
(``toolbox.widgets``/``toolbox.workers``), ``compact_combo()``/
``labeled_field()`` for the inline language-pair row (``toolbox.widgets``,
promoted there once a third tool -- this one -- needed them; see that
module's docstring), ``objectName('primaryButton')``/``objectName('logConsole')``.

Settings persistence: implements the optional ``restore_settings()``/
``save_settings()`` hooks ``main_window.py`` checks for (see
``corpus_convert/page.py``'s docstring for the full reasoning) -- 术语库
语言对（原文/译文）、一致性检查的"只显示有问题的条目"与"同时检查推荐译法
未使用"、and the shared
file dialogs' last-used directory round-trip across launches via
``toolbox/settings.py``, under the ``term_management/`` key prefix. Note
this is separate from the glossary *file* itself (``_glossary_path``):
the last-opened glossary isn't reopened automatically on launch, same as
``corpus_convert``/``tm_editor`` don't reload a last-used input file either
-- only the form inputs around it are remembered.
"""
import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMenu, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from language_tools.reports import adapters as report_adapters
from language_tools.reports import render as report_render
from language_tools.terms import check as term_check_module
from language_tools.terms import extract as extract_module
from language_tools.terms import glossary as glossary_module
from language_tools.terms.filelock import FileLock, office_lock_marker_exists
from language_tools.terms.model import STATUSES, TermEntry
from language_tools.tm import io as tm_io
from language_tools.writers import csv_writer
from toolbox import settings
from toolbox.widgets import CORPUS_FILTER, LANG_TOOLTIP, LOG_COLORS, compact_combo, labeled_field
from toolbox.widgets import lang_combo_code, make_lang_combo, section, set_lang_combo_code
from toolbox.workers import CallableWorker, wait_for_running

_GLOSSARY_OPEN_FILTER = 'Glossary files (*.csv *.xlsx *.xlsm *.tbx)'
_SETTINGS_PREFIX = 'term_management/'
# Save needs each format split into its own named filter (not one
# combined "Glossary files (*.csv *.xlsx *.tbx)" entry) so picking a
# format from the dialog's format dropdown actually determines which
# extension gets appended -- same convention tm_maintenance/page.py's
# _SAVE_FILTER already uses for its TMX/SDLTM choice ('TMX (*.tmx);;SDLTM
# (*.sdltm)'). A single combined filter meant Save always produced .csv
# regardless of which format the person actually wanted, unless they
# typed the extension into the filename themselves.
_GLOSSARY_SAVE_FILTER = 'CSV (*.csv);;Excel (*.xlsx);;TBX (*.tbx)'
_CSV_FILTER = 'CSV (*.csv)'
_REPORT_FILTER = 'HTML (*.html);;PDF (*.pdf)'
_EXTRACT_CORPUS_FILTER = 'Corpus files (*.tmx *.sdltm)'


_STATUS_LABELS = {'approved': '推荐译法', 'forbidden': '禁用译法'}
_STATUS_TOOLTIPS = {
    'approved': '标准/推荐译法。一致性检查默认不看这一档，勾选"同时检查推荐译法未使用"后才会据此标记译文；'
                '只有在这里（或术语表 status 列）明确选了"推荐译法"的行才会被那样检查，'
                'status 留空/无法识别而默认显示为推荐译法的旧行不参与（详见 DESIGN.md 15.1）',
    'forbidden': '明确禁止的错误译法——原文出现这个词，且译文出现这个禁用译法，就标记出来',
}


def _check_job(corpus_path, glossary_path, src_lang, tgt_lang, check_approved=False):
    units = tm_io.read_corpus(corpus_path)
    entries = glossary_module.read(glossary_path, src_lang, tgt_lang)
    return term_check_module.run(units, entries, check_approved=check_approved)


def _extract_job(paths, src_lang, tgt_lang, min_freq, max_ngram, top_n, min_pair_freq):
    units = []
    for path in paths:
        units.extend(tm_io.read_corpus(path))
    return extract_module.suggest_bilingual_candidates(
        units, src_lang, tgt_lang, min_freq=min_freq, max_ngram=max_ngram, top_n=top_n,
        min_pair_freq=min_pair_freq)


def _format_term_hit(hit):
    text = '%s→%s' % (hit['src_term'], hit['tgt_term'])
    if hit.get('status', 'forbidden') == 'approved':
        text = '未用推荐译法 ' + text
    return '%s（%s）' % (text, hit['note']) if hit.get('note') else text


def _pick_save_extension(path, selected_filter):
    if path.lower().endswith(('.csv', '.xlsx', '.tbx')):
        return path
    if 'tbx' in selected_filter.lower():
        return path + '.tbx'
    return path + ('.xlsx' if 'xlsx' in selected_filter.lower() else '.csv')


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
        self._dirty = False          # True if _entries has changes not yet saved to _glossary_path
        self._file_lock = None       # FileLock held on _glossary_path while editing, or None
        self._last_units = None      # last consistency-check result
        self._last_summary = None
        self._check_worker = None
        self._export_worker = None
        self._extract_inputs = []    # corpus file paths queued for candidate extraction
        self._extract_candidates = []  # last extraction result (list of dicts, see extract.py)
        self._extract_worker = None
        self._last_dir = ''  # overwritten by restore_settings() when wired through MainWindow
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
        self.tabs.addTab(self._build_extract_tab(), '候选词提取')
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
        open_btn = QPushButton('打开…')
        open_btn.clicked.connect(self._open_glossary)
        self.glossary_close_btn = QPushButton('关闭')
        self.glossary_close_btn.setEnabled(False)
        self.glossary_close_btn.clicked.connect(self._close_glossary)
        self.glossary_save_btn = QPushButton('保存')
        self.glossary_save_btn.setEnabled(False)
        self.glossary_save_btn.clicked.connect(self._save_glossary)
        save_as_btn = QPushButton('另存为…')
        save_as_btn.clicked.connect(self._save_glossary_as)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(self.glossary_close_btn)
        btn_row.addWidget(self.glossary_save_btn)
        btn_row.addWidget(save_as_btn)
        btn_row.addStretch(1)
        file_layout.addLayout(btn_row)

        self.glossary_path_label = QLabel('未打开文件（当前为新建）')
        self.glossary_path_label.setStyleSheet('color: #6B7280;')
        file_layout.addWidget(self.glossary_path_label)

        layout.addWidget(section('术语库文件', file_widget))

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
        self.entry_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entry_table.customContextMenuRequested.connect(self._show_entry_context_menu)
        self.entry_table.cellDoubleClicked.connect(self._on_entry_double_clicked)
        layout.addWidget(section('术语条目（右键新增/编辑/删除）', self.entry_table), 1)
        return tab

    def _refresh_entry_table(self):
        self.entry_table.setRowCount(len(self._entries))
        for row, e in enumerate(self._entries):
            self.entry_table.setItem(row, 0, QTableWidgetItem(e.src_term))
            self.entry_table.setItem(row, 1, QTableWidgetItem(e.tgt_term))
            self.entry_table.setItem(row, 2, QTableWidgetItem(_STATUS_LABELS.get(e.status, e.status)))
            self.entry_table.setItem(row, 3, QTableWidgetItem(e.domain or ''))
            self.entry_table.setItem(row, 4, QTableWidgetItem(e.note or ''))

    def _sync_glossary_buttons(self):
        has_path = self._glossary_path is not None
        self.glossary_save_btn.setEnabled(has_path)
        self.glossary_close_btn.setEnabled(has_path or bool(self._entries))

    def _add_entry(self):
        dialog = _TermEntryDialog(self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.result_values()
            self._entries.append(TermEntry(
                src_lang=lang_combo_code(self.glossary_src_lang),
                tgt_lang=lang_combo_code(self.glossary_tgt_lang), **values))
            self._dirty = True
            self._refresh_entry_table()
            self._sync_glossary_buttons()
            self._log('已添加：%s → %s' % (values['src_term'], values['tgt_term']))

    def _selected_entry_rows(self):
        return sorted({idx.row() for idx in self.entry_table.selectedIndexes()})

    def _on_entry_double_clicked(self, row, column):
        self.entry_table.selectRow(row)
        self._edit_selected_entry()

    def _show_entry_context_menu(self, pos):
        # No separate "添加…" toolbar button -- 添加/编辑/删除 all live in
        # this one right-click menu instead. Right-clicking empty space
        # below the last row (row == -1) still shows 添加…, just without
        # 编辑/删除, which need an actual row to act on.
        row = self.entry_table.rowAt(pos.y())
        if row >= 0 and row not in self._selected_entry_rows():
            self.entry_table.selectRow(row)

        menu = QMenu(self)
        add_action = menu.addAction('添加…')
        edit_action = None
        delete_action = None
        if row >= 0:
            menu.addSeparator()
            edit_action = menu.addAction('编辑…')
            edit_action.setEnabled(len(self._selected_entry_rows()) == 1)
            delete_action = menu.addAction('删除')
        chosen = menu.exec(self.entry_table.viewport().mapToGlobal(pos))
        if chosen == add_action:
            self._add_entry()
        elif chosen == edit_action:
            self._edit_selected_entry()
        elif chosen == delete_action:
            self._remove_selected_entries()


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
            self._dirty = True
            self._refresh_entry_table()
            self._sync_glossary_buttons()
            self._log('已更新：%s → %s' % (values['src_term'], values['tgt_term']))

    def _remove_selected_entries(self):
        rows = self._selected_entry_rows()
        if not rows:
            self._log('请先选中要删除的术语', 'error')
            return
        for row in reversed(rows):
            del self._entries[row]
        self._dirty = True
        self._refresh_entry_table()
        self._sync_glossary_buttons()
        self._log('已删除 %d 条术语' % len(rows))

    def _release_file_lock(self):
        if self._file_lock is not None:
            self._file_lock.release()
            self._file_lock = None

    def _open_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开术语库', self._last_dir, _GLOSSARY_OPEN_FILTER)
        if not path:
            return
        self._last_dir = os.path.dirname(path)

        # Opening another file (or re-opening the current file to reload
        # it) replaces the in-memory glossary. Give the person the same
        # save/discard/cancel choice _close_glossary() uses before doing
        # anything that could discard unsaved edits -- this used to be
        # missing here specifically, so opening a second glossary while
        # the first had unsaved changes silently discarded them with no
        # warning at all (the same protection existed for closing the
        # app and for the 关闭 button, just not for 打开).
        if self._dirty:
            choice = self._prompt_save_before_discard(
                '当前术语库有未保存的更改，打开文件前要保存吗？')
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save and not self.save_unsaved_changes():
                return

        if office_lock_marker_exists(path):
            proceed = QMessageBox.warning(
                self, '文件可能正被占用',
                '这个文件可能正在 Microsoft Office 或 WPS 中打开。\n'
                '同时编辑可能导致保存冲突，建议先在那边关闭。\n\n仍要继续打开吗？',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if proceed != QMessageBox.Yes:
                return

        # Read before locking, not after: glossary.read() opens its own
        # short-lived handle, separate from the lock's -- if the lock
        # were acquired first, this second handle would (on Windows)
        # collide with this tool's own just-acquired lock, the same
        # same-process self-block FileLock.write_around() exists to avoid
        # on the write side.
        try:
            entries = glossary_module.read(
                path, lang_combo_code(self.glossary_src_lang),
                lang_combo_code(self.glossary_tgt_lang))
        except ValueError as e:
            self._log('打开失败：%s' % e, 'error')
            return
        except OSError as e:
            self._log('打开失败：文件可能正被其他程序占用（%s）' % e, 'error')
            return

        # Re-opening the file already loaded (e.g. to discard local edits
        # and reload from disk) needs no new lock -- we already hold one,
        # and acquiring a second FileLock on it here would incorrectly
        # self-block (same reasoning as above, this time for the lock
        # itself rather than the read).
        reopening_same_file = (path == self._glossary_path)
        if not reopening_same_file:
            new_lock = FileLock(path)
            try:
                new_lock.acquire()
            except OSError:
                self._log(
                    '无法打开：%s 可能正被其他程序占用（例如 WPS/Office，或本工具的另一个实例）' % path,
                    'error')
                return
            self._release_file_lock()
            self._file_lock = new_lock

        self._entries = entries
        self._glossary_path = path
        self._dirty = False
        self.glossary_path_label.setText(path)
        self._sync_glossary_buttons()
        self._refresh_entry_table()
        self._log('已打开 %s，共 %d 条术语' % (path, len(entries)), 'success')

    def _close_glossary(self):
        if self._dirty:
            choice = self._prompt_save_before_discard('当前术语库有未保存的更改，关闭前要保存吗？')
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save and not self.save_unsaved_changes():
                return
        self._release_file_lock()
        self._entries = []
        self._glossary_path = None
        self._dirty = False
        self.glossary_path_label.setText('未打开文件（当前为新建）')
        self._refresh_entry_table()
        self._sync_glossary_buttons()
        self._log('已关闭术语库')

    def _prompt_save_before_discard(self, text):
        box = QMessageBox(self)
        box.setWindowTitle('未保存的更改')
        box.setText(text)
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        return box.exec()

    def _save_glossary(self):
        if not self._glossary_path:
            self._save_glossary_as()
            return
        self._write_glossary(self._glossary_path)

    def _save_glossary_as(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self, '另存为', self._last_dir, _GLOSSARY_SAVE_FILTER)
        if not path:
            return
        self._last_dir = os.path.dirname(path)
        self._write_glossary(_pick_save_extension(path, selected_filter))

    def _write_glossary(self, path):
        """Writes ``self._entries`` to ``path``. Returns True on success,
        False on failure -- used both by the plain save/save-as flows
        (which just log either way) and by ``save_unsaved_changes()``/
        ``_close_glossary()`` (which need to know whether it's safe to
        proceed, or have to stop so the person doesn't lose work).
        """
        is_new_path = path != self._glossary_path
        try:
            if is_new_path or self._file_lock is None:
                glossary_module.write(path, self._entries)
            else:
                # Already holding a lock on this exact path -- route
                # through write_around() so this tool's own save doesn't
                # collide with its own held lock. See FileLock.write_
                # around()'s docstring for why that's needed at all.
                self._file_lock.write_around(lambda: glossary_module.write(path, self._entries))
        except (ValueError, OSError) as e:
            self._log('保存失败：%s' % e, 'error')
            return False

        lock_warning = None
        if is_new_path:
            self._release_file_lock()
            new_lock = FileLock(path)
            try:
                new_lock.acquire()
                self._file_lock = new_lock
            except OSError:
                lock_warning = '已保存，但无法锁定该文件（可能正被其他程序占用），后续编辑将不受保护'

        self._glossary_path = path
        self._dirty = False
        self.glossary_path_label.setText(path)
        self._sync_glossary_buttons()
        if lock_warning:
            self._log(lock_warning, 'error')
        else:
            self._log('已保存到 %s' % path, 'success')
        return True

    # -------------------------------------- MainWindow unsaved-changes hook
    # See this module's docstring for why this is a soft "implement these
    # if relevant" convention rather than an enforced interface.
    def has_unsaved_changes(self):
        return self._dirty

    def unsaved_changes_label(self):
        return '术语管理'

    def save_unsaved_changes(self):
        """Called by MainWindow.closeEvent() when the person chooses "保存
        并退出". Prompts for a save location the same way the save button
        would if there's no path yet. Returns True if it's now safe to
        close (saved, or the person had nothing unsaved to begin with),
        False if closing should be aborted (save failed, or the person
        cancelled the save-location prompt mid-close).
        """
        if not self._dirty:
            return True
        if not self._glossary_path:
            path, selected_filter = QFileDialog.getSaveFileName(
                self, '另存为', '', _GLOSSARY_SAVE_FILTER)
            if not path:
                return False
            return self._write_glossary(_pick_save_extension(path, selected_filter))
        return self._write_glossary(self._glossary_path)

    def cleanup(self):
        """Called by MainWindow.closeEvent() once it's decided the app is
        actually closing, so a normal exit releases the file lock instead
        of leaving it held (and the file unusable elsewhere) after this
        tool itself has stopped running.

        Also waits for ``_check_worker``/``_export_worker`` if either is
        still running -- see ``toolbox.workers.wait_for_running()``. This
        page already implemented ``cleanup()`` for the file lock, which is
        exactly why its own two workers had been missed: the hook existed,
        but nothing in it looked at either worker.
        """
        wait_for_running(self._check_worker, self._export_worker, self._extract_worker)
        self._release_file_lock()

    # ---------------------------------------------------------- settings
    def restore_settings(self):
        set_lang_combo_code(self.glossary_src_lang,
                             settings.get_str(_SETTINGS_PREFIX + 'srcLang', 'en-US'))
        set_lang_combo_code(self.glossary_tgt_lang,
                             settings.get_str(_SETTINGS_PREFIX + 'tgtLang', 'zh-CN'))
        self.check_hide_clean_chk.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'checkHideClean', True))
        self.check_approved_chk.setChecked(
            settings.get_bool(_SETTINGS_PREFIX + 'checkApproved', False))
        self.extract_min_freq_spin.setValue(
            settings.get_int(_SETTINGS_PREFIX + 'extractMinFreq', 2))
        self.extract_max_ngram_spin.setValue(
            settings.get_int(_SETTINGS_PREFIX + 'extractMaxNgram', 4))
        self.extract_top_n_spin.setValue(
            settings.get_int(_SETTINGS_PREFIX + 'extractTopN', 100))
        self.extract_min_pair_freq_spin.setValue(
            settings.get_int(_SETTINGS_PREFIX + 'extractMinPairFreq', 2))
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        settings.set_value(_SETTINGS_PREFIX + 'srcLang', lang_combo_code(self.glossary_src_lang))
        settings.set_value(_SETTINGS_PREFIX + 'tgtLang', lang_combo_code(self.glossary_tgt_lang))
        settings.set_value(_SETTINGS_PREFIX + 'checkHideClean', self.check_hide_clean_chk.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'checkApproved', self.check_approved_chk.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'extractMinFreq', self.extract_min_freq_spin.value())
        settings.set_value(_SETTINGS_PREFIX + 'extractMaxNgram', self.extract_max_ngram_spin.value())
        settings.set_value(_SETTINGS_PREFIX + 'extractTopN', self.extract_top_n_spin.value())
        settings.set_value(_SETTINGS_PREFIX + 'extractMinPairFreq',
                            self.extract_min_pair_freq_spin.value())
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)

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
        self.check_glossary_edit.setPlaceholderText('选择术语库文件（csv/xlsx/tbx）…')
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
        self.check_export_report_btn = QPushButton('导出报告…')
        self.check_export_report_btn.setEnabled(False)
        self.check_export_report_btn.setToolTip(
            '导出为 HTML 或 PDF 的汇总报告（总数/命中占比/按术语统计），适合给非技术干系人看')
        self.check_export_report_btn.clicked.connect(self._start_export_report)
        action_row.addWidget(self.check_btn)
        action_row.addWidget(self.check_export_btn)
        action_row.addWidget(self.check_export_report_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        # Approved-direction check lives next to the check button (not in
        # the results-filter row below) because it changes what the check
        # COMPUTES, unlike 只显示有问题的条目 which only changes what the
        # table displays.
        options_row = QHBoxLayout()
        self.check_approved_chk = QCheckBox('同时检查推荐译法未使用')
        self.check_approved_chk.setToolTip(
            '勾选后额外标记：原文出现推荐术语、但译文没有用到对应推荐译法的情况。'
            '同义改写、代词指代都可能触发，结果是待核实提示，不一定是错。'
            '只检查明确标了"推荐译法"的条目——status 留空或填了不认识的值的行（只是默认显示为推荐译法）不检查；'
            '没有译文的未翻译条目也不标记（那属于 QA 的空译文检查）')
        options_row.addWidget(self.check_approved_chk)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        self.check_summary_label = QLabel('')
        self.check_summary_label.setStyleSheet('color: #4B5262;')
        layout.addWidget(self.check_summary_label)

        # --- 检查结果: filter row + table together under one section, same
        # fold as qa_check/alignment_check made for their own results
        # sections -- see qa_check/page.py's comment at the equivalent spot.
        results_content = QWidget()
        results_layout = QVBoxLayout(results_content)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(10)

        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self.check_hide_clean_chk = QCheckBox('只显示有问题的条目')
        self.check_hide_clean_chk.setChecked(True)
        self.check_hide_clean_chk.stateChanged.connect(self._refresh_check_table)
        filter_layout.addWidget(self.check_hide_clean_chk)
        filter_layout.addStretch(1)
        results_layout.addWidget(filter_row)

        self.check_table = QTableWidget(0, 4)
        self.check_table.setHorizontalHeaderLabels(['#', '原文', '译文', '术语问题'])
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
        results_layout.addWidget(self.check_table, 1)

        layout.addWidget(section('检查结果', results_content), 1)
        return tab

    def _browse_check_corpus(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, CORPUS_FILTER)
        if path:
            self.check_corpus_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    def _browse_check_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, _GLOSSARY_OPEN_FILTER)
        if path:
            self.check_glossary_edit.setText(path)
            self._last_dir = os.path.dirname(path)

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
        self._last_summary = None
        self.check_table.setRowCount(0)
        self.check_summary_label.setText('')
        self.check_export_btn.setEnabled(False)
        self.check_export_report_btn.setEnabled(False)

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
                                lang_combo_code(self.glossary_tgt_lang),
                                check_approved=self.check_approved_chk.isChecked()),
            parent=self)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.finished_err.connect(self._on_check_err)
        self._check_worker.start()

    def _on_check_ok(self, units):
        self.check_btn.setEnabled(True)
        self._last_units = units
        s = term_check_module.summarize(units)
        self._last_summary = s
        rate = (s['flagged'] / s['total'] * 100) if s['total'] else 0.0
        parts = ['%s %d' % (label, s['by_status'][status])
                 for status, label in (('forbidden', '禁用译法'), ('approved', '未用推荐译法'))
                 if s['by_status'].get(status)]
        detail = '（%s）' % '、'.join(parts) if parts else ''
        self.check_summary_label.setText(
            '共 %d 条，%d 条有术语问题（%.1f%%%s）' % (s['total'], s['flagged'], rate, detail))
        self.check_export_btn.setEnabled(bool(units))
        self.check_export_report_btn.setEnabled(bool(units))
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
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', self._last_dir, _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        self._last_dir = os.path.dirname(path)

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

    def _start_export_report(self):
        # Same synchronous report_render.write() pattern as qa_check's
        # 导出报告 button -- one small summary, nothing worth a worker
        # thread; see qa_check/page.py's docstring for the full reasoning.
        if not self._last_units:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, '导出报告', os.path.join(self._last_dir, '术语检查报告'), _REPORT_FILTER)
        if not path:
            return
        if '.' not in os.path.basename(path):
            path += '.pdf' if 'PDF' in selected_filter else '.html'
        self._last_dir = os.path.dirname(path)
        try:
            report_render.write(path, report_adapters.from_term_summary(
                self._last_summary, self._last_units))
        except (ValueError, ImportError) as e:
            self._log('出错了：%s' % e, 'error')
            return
        self._log('已导出报告到 %s' % path, 'success')

    # ------------------------------------------------------- extract tab
    def _build_extract_tab(self):
        """DESIGN.md 15.2's term-extract GUI follow-up. Deliberately
        simpler than the CLI's ``term-extract``/``term-extract-promote``
        pair in two ways, both explained here rather than re-derived by a
        future reader from the code alone:

        - Input is restricted to corpus files (.tmx/.sdltm), not the full
          bilingual-source (docx/xlsx/csv/tsv) dispatch ``tmtool
          term-extract`` supports. Exposing that reader's full option set
          (layout/sheet/column/delimiter/header) here would mean
          duplicating most of ``corpus_convert``'s own form just for this
          one tab; mining an existing TM someone already has open in this
          same tool is the common case this GUI serves, and the CLI
          remains the tool for a power-user batch of raw source files.
        - No separate review-CSV file and no ``decision`` column: the
          results table below *is* the review UI (a checkable "选中"
          column plus editable 译文建议/领域/备注 cells), and "提升到
          术语库" appends straight into this page's own in-memory
          ``self._entries`` -- the same glossary the 术语库 tab is
          already editing -- rather than writing a file this page would
          then have to read back in. This page already has an open-edit-
          save glossary workflow; routing through a CSV round trip here
          would just be an extra file for no benefit a GUI reviewer gets
          from it. The CLI's file-based two-step design earns its keep
          there specifically because there's no in-memory glossary
          session to append into between two separate command
          invocations.

        Promoted entries always get ``status='approved'`` (declared) --
        no status picker in this tab. A term-extraction run proposes
        *candidate recommended terms*, not candidate *forbidden*
        translations; marking something forbidden is a deliberate,
        specific decision this tab's statistical suggestions have no
        basis for making on their own, so that stays a 术语库 tab / manual
        add-entry action.

        The "选中" checkbox column uses ``QTableWidgetItem``'s built-in
        checkable-item support (``Qt.ItemIsUserCheckable`` + checkState),
        not ``setCellWidget()`` -- see ``qa_check/page.py``'s docstring
        for the real, hard-won reasons this codebase avoids cell widgets
        in a QTableWidget where a plain item will do; a checkbox has no
        content-driven sizing problem to begin with, so there's no reason
        to take on that risk here.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        note = QLabel('候选词由统计方法（词频 + 共现集中度）生成，不是语言学分析，'
                       '一定会有噪音——每一行都需要人工判断，勾选"选中"只代表你已经看过并认可这一行，'
                       '不代表提取结果本身可信')
        note.setWordWrap(True)
        note.setStyleSheet('color: #6B7280;')
        layout.addWidget(note)

        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)

        self.extract_input_list = QListWidget()
        self.extract_input_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.extract_input_list.setMaximumHeight(90)
        input_layout.addWidget(self.extract_input_list)

        input_btn_row = QHBoxLayout()
        add_input_btn = QPushButton('添加文件…')
        add_input_btn.clicked.connect(self._add_extract_inputs)
        remove_input_btn = QPushButton('移除选中')
        remove_input_btn.clicked.connect(self._remove_selected_extract_inputs)
        input_btn_row.addWidget(add_input_btn)
        input_btn_row.addWidget(remove_input_btn)
        input_btn_row.addStretch(1)
        input_layout.addLayout(input_btn_row)

        params_row = QHBoxLayout()
        self.extract_min_freq_spin = QSpinBox()
        self.extract_min_freq_spin.setRange(1, 1000)
        self.extract_min_freq_spin.setValue(2)
        self.extract_min_freq_spin.setToolTip('候选词至少要出现这么多次才会被考虑')
        self.extract_max_ngram_spin = QSpinBox()
        self.extract_max_ngram_spin.setRange(1, 20)
        self.extract_max_ngram_spin.setValue(4)
        self.extract_max_ngram_spin.setToolTip('候选词最长多少个词（非中日韩）或字符（中日韩）')
        self.extract_top_n_spin = QSpinBox()
        self.extract_top_n_spin.setRange(1, 10000)
        self.extract_top_n_spin.setValue(100)
        self.extract_top_n_spin.setToolTip('最多取多少个原文候选词并尝试配对译文')
        self.extract_min_pair_freq_spin = QSpinBox()
        self.extract_min_pair_freq_spin.setRange(1, 1000)
        self.extract_min_pair_freq_spin.setValue(2)
        self.extract_min_pair_freq_spin.setToolTip('译文候选至少要和原文候选共现这么多次才会被建议')
        for spin in (self.extract_min_freq_spin, self.extract_max_ngram_spin,
                     self.extract_top_n_spin, self.extract_min_pair_freq_spin):
            spin.setMaximumWidth(90)
        params_row.addLayout(labeled_field('最小频次', self.extract_min_freq_spin))
        params_row.addLayout(labeled_field('最长候选', self.extract_max_ngram_spin))
        params_row.addLayout(labeled_field('候选词上限', self.extract_top_n_spin))
        params_row.addLayout(labeled_field('最小配对频次', self.extract_min_pair_freq_spin))
        params_row.addStretch(1)
        input_layout.addLayout(params_row)

        layout.addWidget(section('输入文件（tmx/sdltm，语言对沿用术语库 tab 的设置）', input_widget))

        action_row = QHBoxLayout()
        self.extract_btn = QPushButton('开始提取')
        self.extract_btn.setObjectName('primaryButton')
        self.extract_btn.clicked.connect(self._start_extract)
        self.extract_promote_btn = QPushButton('提升到术语库')
        self.extract_promote_btn.setEnabled(False)
        self.extract_promote_btn.setToolTip('把已勾选的行加入当前术语库（内存中，仍需在术语库 tab 保存）')
        self.extract_promote_btn.clicked.connect(self._promote_extract_selection)
        action_row.addWidget(self.extract_btn)
        action_row.addWidget(self.extract_promote_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.extract_summary_label = QLabel('')
        self.extract_summary_label.setStyleSheet('color: #4B5262;')
        layout.addWidget(self.extract_summary_label)

        self.extract_table = QTableWidget(0, 7)
        self.extract_table.setHorizontalHeaderLabels(
            ['选中', '原文候选', '译文建议', '领域', '备注', '原文频次', '配对频次/集中度'])
        self.extract_table.verticalHeader().setVisible(False)
        header = self.extract_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Only 选中/译文建议/领域/备注 are meant to be edited; 原文候选 and
        # the two reference-number columns stay read-only via each item's
        # own flags (set in _refresh_extract_table()) rather than a
        # table-wide NoEditTriggers, since this table (unlike every other
        # one in this codebase) needs some cells editable.
        self.extract_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.extract_table.setShowGrid(False)
        self.extract_table.setAlternatingRowColors(True)
        layout.addWidget(section('候选结果', self.extract_table), 1)
        return tab

    def _add_extract_inputs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择文件', self._last_dir, _EXTRACT_CORPUS_FILTER)
        if not paths:
            return
        self._last_dir = os.path.dirname(paths[0])
        for path in paths:
            if path not in self._extract_inputs:
                self._extract_inputs.append(path)
                self.extract_input_list.addItem(path)

    def _remove_selected_extract_inputs(self):
        rows = sorted({idx.row() for idx in self.extract_input_list.selectedIndexes()},
                      reverse=True)
        for row in rows:
            self.extract_input_list.takeItem(row)
            del self._extract_inputs[row]

    def _start_extract(self):
        if not self._extract_inputs:
            self._log('请先添加至少一个 tmx/sdltm 文件', 'error')
            return
        self._extract_candidates = []
        self.extract_table.setRowCount(0)
        self.extract_summary_label.setText('')
        self.extract_promote_btn.setEnabled(False)
        self.extract_btn.setEnabled(False)
        self._log('正在提取候选词…')
        self._extract_worker = CallableWorker(
            lambda: _extract_job(
                list(self._extract_inputs), lang_combo_code(self.glossary_src_lang),
                lang_combo_code(self.glossary_tgt_lang),
                self.extract_min_freq_spin.value(), self.extract_max_ngram_spin.value(),
                self.extract_top_n_spin.value(), self.extract_min_pair_freq_spin.value()),
            parent=self)
        self._extract_worker.finished_ok.connect(self._on_extract_ok)
        self._extract_worker.finished_err.connect(self._on_extract_err)
        self._extract_worker.start()

    def _on_extract_ok(self, candidates):
        self.extract_btn.setEnabled(True)
        self._extract_candidates = candidates
        paired = sum(1 for c in candidates if c['tgt_term'])
        self.extract_summary_label.setText(
            '共 %d 条候选，%d 条有译文建议（%.1f%%）——统计方法产生的建议，逐行核实后再勾选' % (
                len(candidates), paired,
                (paired / len(candidates) * 100) if candidates else 0.0))
        self.extract_promote_btn.setEnabled(bool(candidates))
        self._refresh_extract_table()
        self._log('提取完成，共 %d 条候选' % len(candidates), 'success')

    def _on_extract_err(self, message):
        self.extract_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    def _refresh_extract_table(self):
        self.extract_table.setRowCount(len(self._extract_candidates))
        for row, c in enumerate(self._extract_candidates):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Unchecked)  # never pre-checked -- see tab docstring
            self.extract_table.setItem(row, 0, check_item)

            src_item = QTableWidgetItem(c['src_term'])
            src_item.setFlags(src_item.flags() & ~Qt.ItemIsEditable)
            self.extract_table.setItem(row, 1, src_item)

            self.extract_table.setItem(row, 2, QTableWidgetItem(c.get('tgt_term', '')))
            self.extract_table.setItem(row, 3, QTableWidgetItem(''))
            self.extract_table.setItem(row, 4, QTableWidgetItem(''))

            freq_item = QTableWidgetItem(str(c.get('src_freq', '')))
            freq_item.setFlags(freq_item.flags() & ~Qt.ItemIsEditable)
            self.extract_table.setItem(row, 5, freq_item)

            pair_text = ('%s / %.2f' % (c.get('pair_freq', 0), c.get('concentration', 0.0))
                         if c.get('tgt_term') else '-')
            pair_item = QTableWidgetItem(pair_text)
            pair_item.setFlags(pair_item.flags() & ~Qt.ItemIsEditable)
            self.extract_table.setItem(row, 6, pair_item)

    def _promote_extract_selection(self):
        checked_rows = [row for row in range(self.extract_table.rowCount())
                         if self.extract_table.item(row, 0).checkState() == Qt.Checked]
        if not checked_rows:
            self._log('请先勾选要提升的候选词', 'error')
            return

        # All-or-nothing on a blank tgt_term among the checked rows -- same
        # guard language_tools.terms.extract.promote_reviewed_candidates()
        # enforces for the CLI path, and the same reason: approving a
        # src-only hit with no translation filled in is almost always an
        # oversight, not something that should silently produce an empty
        # glossary entry.
        blank_rows = [row for row in checked_rows if not self.extract_table.item(row, 2).text().strip()]
        if blank_rows:
            self._log('第 %s 行已勾选但译文建议为空，请先填写译文或取消勾选' %
                       '、'.join(str(r + 1) for r in blank_rows), 'error')
            return

        src_lang = lang_combo_code(self.glossary_src_lang)
        tgt_lang = lang_combo_code(self.glossary_tgt_lang)
        for row in checked_rows:
            src_term = self.extract_table.item(row, 1).text()
            tgt_term = self.extract_table.item(row, 2).text().strip()
            domain = self.extract_table.item(row, 3).text().strip() or None
            note = self.extract_table.item(row, 4).text().strip() or None
            self._entries.append(TermEntry(
                src_lang=src_lang, tgt_lang=tgt_lang, src_term=src_term, tgt_term=tgt_term,
                status='approved', status_declared=True, domain=domain, note=note))
            self.extract_table.item(row, 0).setCheckState(Qt.Unchecked)

        self._dirty = True
        self._refresh_entry_table()
        self._sync_glossary_buttons()
        self._log('已提升 %d 条候选词到术语库（还未保存到文件）' % len(checked_rows), 'success')

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = LOG_COLORS.get(kind, LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))
