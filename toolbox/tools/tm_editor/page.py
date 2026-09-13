"""The TM entry editor: 术语管理's 术语库 tab pattern (open/close/save/
save-as a file into memory, a QTableWidget browsing it, add/edit/delete
via a modal dialog, dirty-tracking wired into MainWindow's unsaved-
changes prompt -- see term_management/page.py's module docstring for the
original reasoning) applied to individual translation units in a tmx/
sdltm instead of glossary rows.

Two deliberate differences from term_management, both decided with Eliot
(2026-09-13):

- No file lock. term_management's FileLock/office_lock_marker_exists is
  specifically built around detecting an Office/WPS lock marker on a csv/
  xlsx -- not applicable here (.sdltm is a SQLite database, .tmx is plain
  XML; the realistic concurrent-editor to worry about is a CAT tool like
  Trados Studio, not Office). Scoped out for this first pass -- a failed
  write just surfaces the OS/database error, same as any other tool page
  that doesn't hold a lock.

- Read/write catch a broad ``Exception``, not term_management's narrower
  ``(ValueError, OSError)``: a corrupt .sdltm can raise a sqlite3 error
  and a malformed .tmx can raise an XML parse error, neither of which is
  a ValueError/OSError, so the narrower catch term_management gets away
  with (glossary csv/xlsx parsing only ever raises those two) would let
  a corrupt-file open crash the whole page instead of showing "打开失败".

Also, unlike glossary (no embedded language pair -- csv/xlsx rows are
just src_term/tgt_term columns), a tmx/sdltm carries its own src/tgt
language. So the language combos here aren't an independent setting the
person picks every time like term_management's glossary_src_lang/
tgt_lang -- they're editable only while building a brand new, not-yet-
saved TM from scratch (新建), and get set from the opened file's own
pair (via ``tm_io.infer_langs()``) and locked as soon as a file is
open or has been saved once. Changing an *existing* TM's language pair
is tm_maintenance's job (清理/合并 already rewrite the whole file), not
this page's -- letting the combos stay live post-open would raise "what
happens to the units that already have the old pair on them" questions
this page has no good answer for.

Entries are edited through a modal dialog, not inline table cells --
same reasoning as term_management's _TermEntryDialog: validation (原文/
译文 not empty) needs somewhere to fail before committing, which inline
cell editing doesn't have without its own itemChanged rollback plumbing.
One more thing the dialog handles that term_management's doesn't need to:
a unit can carry inline-markup (TMX <bpt>/<ph>/... tags -- see
language_tools/model.py's docstring). The dialog only edits plain
src_text/tgt_text, so accepting it always clears both markup fields --
tmx_writer prefers markup over src_text/tgt_text when both are present
(see tmx_writer.py's _seg_body()), so leaving old markup in place after
a text edit would make the edit silently not show up in the saved file.
The dialog warns about this up front when editing a unit that has any.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from language_tools.model import TranslationUnit
from language_tools.tm import io as tm_io
from toolbox import settings
from toolbox.widgets import CORPUS_FILTER, LANG_TOOLTIP, LOG_COLORS, compact_combo, labeled_field
from toolbox.widgets import lang_combo_code, make_lang_combo, set_lang_combo_code
from toolbox.widgets import section

_SAVE_FILTER = 'TMX (*.tmx);;SDLTM (*.sdltm)'
_SETTINGS_PREFIX = 'tm_editor/'


def _pick_save_extension(path, selected_filter):
    # Same shape as term_management's _pick_save_extension() (second call
    # site -- not promoted, see toolbox/widgets.py's promote-at-third-site
    # convention) for the same reason: a combined "TMX (*.tmx);;SDLTM
    # (*.sdltm)" filter doesn't reliably get its extension auto-appended
    # by the save dialog on every platform.
    if path.lower().endswith('.tmx') or path.lower().endswith('.sdltm'):
        return path
    return path + ('.sdltm' if 'sdltm' in selected_filter.lower() else '.tmx')


class _TUEntryDialog(QDialog):
    """Modal add/edit form for one translation unit."""

    def __init__(self, parent=None, unit=None):
        super().__init__(parent)
        self.setWindowTitle('编辑记录' if unit else '添加记录')
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.src_edit = QPlainTextEdit(unit.src_text if unit else '')
        self.tgt_edit = QPlainTextEdit(unit.tgt_text if unit else '')
        for edit in (self.src_edit, self.tgt_edit):
            edit.setMaximumHeight(90)

        self.error_label = QLabel('')
        self.error_label.setStyleSheet('color: %s;' % LOG_COLORS['error'])
        self.error_label.setVisible(False)

        form.addRow('原文', self.src_edit)
        form.addRow('译文', self.tgt_edit)

        if unit is not None and (unit.src_markup or unit.tgt_markup):
            markup_note = QLabel('该条目包含内联标签格式，保存修改后标签会被清除，只保留纯文本')
            markup_note.setWordWrap(True)
            markup_note.setStyleSheet('color: %s;' % LOG_COLORS['info'])
            form.addRow(markup_note)

        form.addRow(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self):
        if not self.src_edit.toPlainText().strip() or not self.tgt_edit.toPlainText().strip():
            self.error_label.setText('原文和译文都不能为空')
            self.error_label.setVisible(True)
            return
        self.accept()

    def result_values(self):
        return {
            'src_text': self.src_edit.toPlainText().strip(),
            'tgt_text': self.tgt_edit.toPlainText().strip(),
        }


class TmEditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._units = []      # currently-loaded/edited TM, in memory
        self._path = None     # None until opened/saved once
        self._dirty = False   # True if _units has changes not yet saved to _path
        self._last_dir = ''   # overwritten by restore_settings() when wired through MainWindow
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('条目编辑')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel('打开或新建翻译记忆库，浏览、增删改单条记录')
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(10)

        lang_row = QHBoxLayout()
        self.src_lang_combo = make_lang_combo('en-US')
        self.tgt_lang_combo = make_lang_combo('zh-CN')
        self.src_lang_combo.setToolTip(LANG_TOOLTIP + '\n打开文件后由文件本身决定，锁定为只读')
        self.tgt_lang_combo.setToolTip(LANG_TOOLTIP + '\n打开文件后由文件本身决定，锁定为只读')
        compact_combo(self.src_lang_combo)
        compact_combo(self.tgt_lang_combo)
        lang_row.addLayout(labeled_field('原文语言', self.src_lang_combo))
        lang_row.addLayout(labeled_field('译文语言', self.tgt_lang_combo))
        lang_row.addStretch(1)
        file_layout.addLayout(lang_row)

        btn_row = QHBoxLayout()
        new_btn = QPushButton('新建')
        new_btn.clicked.connect(self._new_tm)
        open_btn = QPushButton('打开…')
        open_btn.clicked.connect(self._open_tm)
        self.close_btn = QPushButton('关闭')
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self._close_tm)
        self.save_btn = QPushButton('保存')
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        save_as_btn = QPushButton('另存为…')
        save_as_btn.clicked.connect(self._save_as)
        for b in (new_btn, open_btn, self.close_btn, self.save_btn, save_as_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        file_layout.addLayout(btn_row)

        self.path_label = QLabel('未打开文件（当前为新建）')
        self.path_label.setStyleSheet('color: #6B7280;')
        file_layout.addWidget(self.path_label)

        outer.addWidget(section('记忆库文件', file_widget))

        self.entry_table = QTableWidget(0, 3)
        self.entry_table.setHorizontalHeaderLabels(['原文', '译文', '标签'])
        self.entry_table.verticalHeader().setVisible(False)
        header = self.entry_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.entry_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.entry_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.entry_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.entry_table.setShowGrid(False)
        self.entry_table.setAlternatingRowColors(True)
        self.entry_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entry_table.customContextMenuRequested.connect(self._show_entry_context_menu)
        self.entry_table.cellDoubleClicked.connect(self._on_entry_double_clicked)
        outer.addWidget(section('记录（右键新增/编辑/删除）', self.entry_table), 1)

        self.status_label = QLabel('')
        self.status_label.setStyleSheet('color: #4B5262;')
        outer.addWidget(self.status_label)

    # ---------------------------------------------------------------- log
    def _log(self, message, kind='info'):
        self.status_label.setText(message)
        self.status_label.setStyleSheet('color: %s;' % LOG_COLORS.get(kind, LOG_COLORS['info']))

    # --------------------------------------------------------------- table
    def _refresh_entry_table(self):
        self.entry_table.setRowCount(len(self._units))
        for row, u in enumerate(self._units):
            self.entry_table.setItem(row, 0, QTableWidgetItem(u.src_text))
            self.entry_table.setItem(row, 1, QTableWidgetItem(u.tgt_text))
            tag_note = '含标签' if (u.src_markup or u.tgt_markup) else ''
            self.entry_table.setItem(row, 2, QTableWidgetItem(tag_note))

    def _sync_buttons(self):
        has_path = self._path is not None
        self.save_btn.setEnabled(has_path)
        self.close_btn.setEnabled(has_path or bool(self._units))
        enabled = not has_path
        self.src_lang_combo.setEnabled(enabled)
        self.tgt_lang_combo.setEnabled(enabled)

    def _selected_rows(self):
        return sorted({idx.row() for idx in self.entry_table.selectedIndexes()})

    def _on_entry_double_clicked(self, row, column):
        self.entry_table.selectRow(row)
        self._edit_selected_entry()

    def _show_entry_context_menu(self, pos):
        row = self.entry_table.rowAt(pos.y())
        if row >= 0 and row not in self._selected_rows():
            self.entry_table.selectRow(row)

        menu = QMenu(self)
        add_action = menu.addAction('添加…')
        edit_action = None
        delete_action = None
        if row >= 0:
            menu.addSeparator()
            edit_action = menu.addAction('编辑…')
            edit_action.setEnabled(len(self._selected_rows()) == 1)
            delete_action = menu.addAction('删除')
        chosen = menu.exec(self.entry_table.viewport().mapToGlobal(pos))
        if chosen == add_action:
            self._add_entry()
        elif chosen == edit_action:
            self._edit_selected_entry()
        elif chosen == delete_action:
            self._remove_selected_entries()

    # -------------------------------------------------------------- CRUD
    def _add_entry(self):
        dialog = _TUEntryDialog(self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.result_values()
            self._units.append(TranslationUnit(
                src_lang=lang_combo_code(self.src_lang_combo),
                tgt_lang=lang_combo_code(self.tgt_lang_combo), **values))
            self._dirty = True
            self._refresh_entry_table()
            self._sync_buttons()
            self._log('已添加 1 条记录', 'success')

    def _edit_selected_entry(self):
        rows = self._selected_rows()
        if len(rows) != 1:
            self._log('请先选中一条要编辑的记录（只能选一条）', 'error')
            return
        row = rows[0]
        unit = self._units[row]
        dialog = _TUEntryDialog(self, unit=unit)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.result_values()
            # src_markup/tgt_markup dropped unconditionally -- see this
            # module's docstring for why (the dialog only edits plain
            # text, and tmx_writer prefers markup over text when both are
            # present, so stale markup would silently swallow the edit).
            self._units[row] = TranslationUnit(
                src_lang=unit.src_lang, tgt_lang=unit.tgt_lang, **values)
            self._dirty = True
            self._refresh_entry_table()
            self._sync_buttons()
            self._log('已更新 1 条记录', 'success')

    def _remove_selected_entries(self):
        rows = self._selected_rows()
        if not rows:
            self._log('请先选中要删除的记录', 'error')
            return
        for row in reversed(rows):
            del self._units[row]
        self._dirty = True
        self._refresh_entry_table()
        self._sync_buttons()
        self._log('已删除 %d 条记录' % len(rows), 'success')

    # ---------------------------------------------------------- open/close
    def _new_tm(self):
        if self._dirty:
            choice = self._prompt_save_before_discard('当前记忆库有未保存的更改，新建前要保存吗？')
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save and not self.save_unsaved_changes():
                return
        self._units = []
        self._path = None
        self._dirty = False
        self.path_label.setText('未打开文件（当前为新建）')
        self._refresh_entry_table()
        self._sync_buttons()
        self._log('已新建空白记忆库，请先设置原文/译文语言')

    def _open_tm(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开记忆库', self._last_dir, CORPUS_FILTER)
        if not path:
            return

        if self._dirty:
            choice = self._prompt_save_before_discard('当前记忆库有未保存的更改，打开文件前要保存吗？')
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save and not self.save_unsaved_changes():
                return

        try:
            units = tm_io.read_corpus(path)
        except Exception as e:  # noqa: BLE001 -- see module docstring for why this is broad
            self._log('打开失败：%s' % e, 'error')
            return

        self._units = units
        self._path = path
        self._dirty = False
        self._last_dir = os.path.dirname(path)
        src_lang, tgt_lang = tm_io.infer_langs(units)
        set_lang_combo_code(self.src_lang_combo, src_lang)
        set_lang_combo_code(self.tgt_lang_combo, tgt_lang)
        self.path_label.setText(path)
        self._sync_buttons()
        self._refresh_entry_table()
        self._log('已打开 %s，共 %d 条记录' % (path, len(units)), 'success')

    def _close_tm(self):
        if self._dirty:
            choice = self._prompt_save_before_discard('当前记忆库有未保存的更改，关闭前要保存吗？')
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save and not self.save_unsaved_changes():
                return
        self._units = []
        self._path = None
        self._dirty = False
        self.path_label.setText('未打开文件（当前为新建）')
        self._refresh_entry_table()
        self._sync_buttons()
        self._log('已关闭记忆库')

    def _prompt_save_before_discard(self, text):
        box = QMessageBox(self)
        box.setWindowTitle('未保存的更改')
        box.setText(text)
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        return box.exec()

    # -------------------------------------------------------------- save
    def _save(self):
        if not self._path:
            self._save_as()
            return
        self._write(self._path)

    def _save_as(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self, '另存为', self._last_dir, _SAVE_FILTER)
        if not path:
            return
        self._write(_pick_save_extension(path, selected_filter))

    def _write(self, path):
        """Writes ``self._units`` to ``path``. Returns True on success,
        False on failure -- used both by the plain save/save-as flows
        (which just log either way) and by ``save_unsaved_changes()``
        (which needs to know whether it's safe to proceed with closing).
        """
        src_lang = lang_combo_code(self.src_lang_combo)
        tgt_lang = lang_combo_code(self.tgt_lang_combo)
        try:
            tm_io.write_corpus(path, self._units, src_lang, tgt_lang)
        except Exception as e:  # noqa: BLE001 -- see module docstring for why this is broad
            self._log('保存失败：%s' % e, 'error')
            return False

        self._path = path
        self._dirty = False
        self._last_dir = os.path.dirname(path)
        self.path_label.setText(path)
        self._sync_buttons()
        self._log('已保存到 %s' % path, 'success')
        return True

    # -------------------------------------- MainWindow unsaved-changes hook
    # See toolbox/main_window.py's module docstring for why this is a soft
    # "implement these if relevant" convention rather than an enforced
    # interface.
    def has_unsaved_changes(self):
        return self._dirty

    def unsaved_changes_label(self):
        return '条目编辑'

    def save_unsaved_changes(self):
        if not self._dirty:
            return True
        if not self._path:
            path, selected_filter = QFileDialog.getSaveFileName(
                self, '另存为', self._last_dir, _SAVE_FILTER)
            if not path:
                return False
            return self._write(_pick_save_extension(path, selected_filter))
        return self._write(self._path)

    # ------------------------------------------------------------ settings
    def restore_settings(self):
        set_lang_combo_code(self.src_lang_combo, settings.get_str(_SETTINGS_PREFIX + 'srcLang', 'en-US'))
        set_lang_combo_code(self.tgt_lang_combo, settings.get_str(_SETTINGS_PREFIX + 'tgtLang', 'zh-CN'))
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        # Only meaningful for the 新建 starting point -- once a file's
        # open/saved these combos are locked to that file's own pair
        # (see this module's docstring), so persisting them here is
        # purely "what should 新建 default to next time", not an attempt
        # to remember which specific file's language pair was last open.
        settings.set_value(_SETTINGS_PREFIX + 'srcLang', lang_combo_code(self.src_lang_combo))
        settings.set_value(_SETTINGS_PREFIX + 'tgtLang', lang_combo_code(self.tgt_lang_combo))
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)
