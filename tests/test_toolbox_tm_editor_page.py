from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from language_tools.model import InlineNode, TranslationUnit
from language_tools.tm import io as tm_io
from toolbox.tools.tm_editor.page import TmEditorPage, _NearDupDialog, _TUEntryDialog
from toolbox.tools.tm_editor.page import _pick_save_extension
from toolbox.widgets import lang_combo_code

from conftest import tmx_path


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def _write_tmx(path, units, src_lang='en-US', tgt_lang='zh-CN'):
    tm_io.write_corpus(str(path), units, src_lang, tgt_lang)


# ------------------------------------------------------------------ dialog
# _TUEntryDialog.exec() is modal and would block in a real run; tests that
# go through the page's _add_entry()/_edit_selected_entry() monkeypatch
# exec() itself (fill fields, return Accepted) rather than calling .exec()
# for real -- same approach term_management's tests use for the identical
# reason.

def test_dialog_rejects_empty_text_without_accepting(qtbot):
    dialog = _TUEntryDialog()
    dialog._on_accept()
    assert dialog.result() != QDialog.Accepted
    assert not dialog.error_label.isHidden()


def test_dialog_prefills_from_existing_unit(qtbot):
    unit = _u('cloud computing', '云计算')
    dialog = _TUEntryDialog(unit=unit)
    assert dialog.src_edit.toPlainText() == 'cloud computing'
    assert dialog.tgt_edit.toPlainText() == '云计算'


def test_dialog_result_values_strips_whitespace(qtbot):
    dialog = _TUEntryDialog()
    dialog.src_edit.setPlainText('  hello  ')
    dialog.tgt_edit.setPlainText('  你好  ')
    values = dialog.result_values()
    assert values == {'src_text': 'hello', 'tgt_text': '你好'}


def test_dialog_shows_no_markup_warning_for_plain_unit(qtbot):
    dialog = _TUEntryDialog(unit=_u('plain', '纯文本'))
    texts = [dialog.layout().itemAt(i).widget().text()
             for i in range(dialog.layout().rowCount() * 2)
             if dialog.layout().itemAt(i) and dialog.layout().itemAt(i).widget()
             and hasattr(dialog.layout().itemAt(i).widget(), 'text')]
    assert not any('标签' in t for t in texts)


def test_dialog_shows_markup_warning_for_tagged_unit(qtbot):
    tagged = _u('save', '保存', src_markup=[InlineNode('tag', '<b>'), InlineNode('text', 'save')])
    dialog = _TUEntryDialog(unit=tagged)
    texts = [dialog.layout().itemAt(i).widget().text()
             for i in range(dialog.layout().rowCount() * 2)
             if dialog.layout().itemAt(i) and dialog.layout().itemAt(i).widget()
             and hasattr(dialog.layout().itemAt(i).widget(), 'text')]
    assert any('标签' in t and '清除' in t for t in texts)


# --------------------------------------------------------------- CRUD table

def test_page_starts_empty_with_buttons_disabled(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    assert page.entry_table.rowCount() == 0
    assert not page.save_btn.isEnabled()
    assert not page.close_btn.isEnabled()
    assert page.src_lang_combo.isEnabled()
    assert page.tgt_lang_combo.isEnabled()


def test_add_entry_via_dialog_appends_to_table(qtbot, monkeypatch):
    def fake_exec(self):
        self.src_edit.setPlainText('cloud')
        self.tgt_edit.setPlainText('云')
        return QDialog.Accepted
    monkeypatch.setattr(_TUEntryDialog, 'exec', fake_exec)

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._add_entry()
    assert page.entry_table.rowCount() == 1
    assert page.entry_table.item(0, 0).text() == 'cloud'
    assert page.entry_table.item(0, 1).text() == '云'
    assert page.entry_table.item(0, 2).text() == ''  # no markup on a freshly-added entry
    assert '已添加' in page.status_label.text()
    assert page.close_btn.isEnabled()  # nothing to save to yet, but something to discard


def test_dialog_cancel_does_not_add_entry(qtbot, monkeypatch):
    monkeypatch.setattr(_TUEntryDialog, 'exec', lambda self: QDialog.Rejected)
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._add_entry()
    assert page.entry_table.rowCount() == 0


def test_edit_selected_entry_updates_table(qtbot, monkeypatch):
    def fake_exec(self):
        self.tgt_edit.setPlainText('大数据（已更新）')
        return QDialog.Accepted
    monkeypatch.setattr(_TUEntryDialog, 'exec', fake_exec)

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('big data', '大数据')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)
    page._edit_selected_entry()
    assert page.entry_table.item(0, 1).text() == '大数据（已更新）'


def test_editing_a_unit_clears_its_markup(qtbot, monkeypatch):
    # The core correctness guard this tool exists to get right -- see the
    # module docstring's explanation of tmx_writer preferring markup over
    # src_text/tgt_text when both are present.
    def fake_exec(self):
        self.src_edit.setPlainText('save (fixed)')
        return QDialog.Accepted
    monkeypatch.setattr(_TUEntryDialog, 'exec', fake_exec)

    tagged = _u('save', '保存', src_markup=[InlineNode('text', 'save')])
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [tagged]
    page._refresh_entry_table()
    assert page.entry_table.item(0, 2).text() == '含标签'

    page.entry_table.selectRow(0)
    page._edit_selected_entry()
    assert page._units[0].src_text == 'save (fixed)'
    assert page._units[0].src_markup is None
    assert page.entry_table.item(0, 2).text() == ''


def test_edit_requires_exactly_one_selected_row(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A'), _u('b', 'B')]
    page._refresh_entry_table()
    page._edit_selected_entry()
    assert '只能选一条' in page.status_label.text()


def test_double_clicking_a_row_opens_the_edit_dialog(qtbot, monkeypatch):
    def fake_exec(self):
        self.tgt_edit.setPlainText('改过了')
        return QDialog.Accepted
    monkeypatch.setattr(_TUEntryDialog, 'exec', fake_exec)

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('big data', '大数据')]
    page._refresh_entry_table()
    page._on_entry_double_clicked(0, 1)
    assert page.entry_table.item(0, 1).text() == '改过了'


def test_remove_selected_entries_removes_only_selected(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A'), _u('b', 'B')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)
    page._remove_selected_entries()
    assert len(page._units) == 1
    assert page._units[0].src_text == 'b'
    assert page.entry_table.rowCount() == 1


def test_remove_with_no_selection_shows_validation_error(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._remove_selected_entries()
    assert '请先选中要删除' in page.status_label.text()


# ----------------------------------------------------------- context menu

def _fake_menu_module(monkeypatch, choose_text):
    class _FakeAction:
        def __init__(self, text):
            self.text = text
            self._enabled = True

        def setEnabled(self, enabled):
            self._enabled = enabled

        def isEnabled(self):
            return self._enabled

    class _FakeMenu:
        def __init__(self, parent=None):
            self.actions = []

        def addAction(self, text):
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def addSeparator(self):
            pass

        def exec(self, pos):
            for action in self.actions:
                if action.text == choose_text:
                    return action
            return None

    import toolbox.tools.tm_editor.page as page_module
    monkeypatch.setattr(page_module, 'QMenu', _FakeMenu)


def _row_center(page, row):
    page.show()
    page.entry_table.window().activateWindow()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    return page.entry_table.visualRect(page.entry_table.model().index(row, 0)).center()


def test_context_menu_add_action_dispatches_to_add(qtbot, monkeypatch):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('big data', '大数据')]
    page._refresh_entry_table()
    _fake_menu_module(monkeypatch, choose_text='添加…')

    calls = []
    monkeypatch.setattr(page, '_add_entry', lambda: calls.append('add'))
    page._show_entry_context_menu(_row_center(page, 0))
    assert calls == ['add']


def test_context_menu_delete_action_dispatches_to_delete(qtbot, monkeypatch):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('big data', '大数据')]
    page._refresh_entry_table()
    _fake_menu_module(monkeypatch, choose_text='删除')

    calls = []
    monkeypatch.setattr(page, '_remove_selected_entries', lambda: calls.append('delete'))
    page._show_entry_context_menu(_row_center(page, 0))
    assert calls == ['delete']


# --------------------------------------------------------------- new/open/close

def test_new_tm_resets_state_and_enables_lang_combos(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'existing.tmx'
    _write_tmx(path, [_u('a', 'A')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_tm()
    assert not page.src_lang_combo.isEnabled()

    page._new_tm()
    assert page._units == []
    assert page._path is None
    assert page.path_label.text() == '未打开文件（当前为新建）'
    assert page.src_lang_combo.isEnabled()
    assert page.tgt_lang_combo.isEnabled()


def test_open_tm_loads_entries_infers_lang_and_locks_combos(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'sample.tmx'
    _write_tmx(path, [_u('hello', '你好'), _u('world', '世界')], src_lang='ja-JP', tgt_lang='ko-KR')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_tm()

    assert page.entry_table.rowCount() == 2
    assert lang_combo_code(page.src_lang_combo) == 'ja-JP'
    assert lang_combo_code(page.tgt_lang_combo) == 'ko-KR'
    assert not page.src_lang_combo.isEnabled()
    assert not page.tgt_lang_combo.isEnabled()
    assert page.save_btn.isEnabled()
    assert page._last_dir == str(tmp_path)
    assert '已打开' in page.status_label.text()


def test_open_malformed_file_shows_error_not_crash(qtbot, monkeypatch, tmp_path):
    bad = tmp_path / 'corrupt.sdltm'
    bad.write_bytes(b'this is not a sqlite database')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(bad), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_tm()  # must not raise
    assert '打开失败' in page.status_label.text()
    assert page.entry_table.rowCount() == 0


def test_close_tm_with_unsaved_changes_cancel_keeps_state(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Cancel)
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A')]
    page._dirty = True
    page._close_tm()
    assert page._units  # untouched


def test_close_tm_with_unsaved_changes_discard_clears_state(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Discard)
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A')]
    page._dirty = True
    page._close_tm()
    assert page._units == []
    assert page._path is None


# --------------------------------------------------------------------- save

def test_save_as_writes_file_and_enables_buttons(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'new.tmx'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A')]
    page._dirty = True
    page._save_as()

    assert out.exists()
    assert page._path == str(out)
    assert not page._dirty
    assert page.save_btn.isEnabled()
    assert not page.src_lang_combo.isEnabled()  # locked now that it's a real saved file
    assert page._last_dir == str(tmp_path)


def test_save_without_a_path_yet_falls_back_to_save_as(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'new.tmx'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A')]
    page._save()
    assert out.exists()


def test_save_unsaved_changes_is_noop_when_clean(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    assert page.save_unsaved_changes() is True


def test_save_unsaved_changes_writes_to_existing_path(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'sample.tmx'
    _write_tmx(path, [_u('a', 'A')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_tm()
    page._units.append(_u('b', 'B'))
    page._dirty = True
    assert page.save_unsaved_changes() is True
    assert not page._dirty
    reloaded = tm_io.read_corpus(str(path))
    assert len(reloaded) == 2


def test_save_unsaved_changes_returns_false_when_save_dialog_cancelled(qtbot, monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: ('', ''))
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('a', 'A')]
    page._dirty = True
    assert page.save_unsaved_changes() is False


# ---------------------------------------------------------- save-extension

def test_pick_save_extension_keeps_explicit_tmx_or_sdltm():
    assert _pick_save_extension('/x/y.tmx', 'TMX (*.tmx)') == '/x/y.tmx'
    assert _pick_save_extension('/x/y.sdltm', 'SDLTM (*.sdltm)') == '/x/y.sdltm'


def test_pick_save_extension_appends_based_on_selected_filter():
    assert _pick_save_extension('/x/y', 'SDLTM (*.sdltm)') == '/x/y.sdltm'
    assert _pick_save_extension('/x/y', 'TMX (*.tmx)') == '/x/y.tmx'


# ------------------------------------------------------------- settings

def test_restore_settings_defaults_when_nothing_saved_yet(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page.restore_settings()
    assert lang_combo_code(page.src_lang_combo) == 'en-US'
    assert lang_combo_code(page.tgt_lang_combo) == 'zh-CN'
    assert page._last_dir == ''


def test_save_then_restore_settings_round_trips(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page.src_lang_combo.setEditText('fr-FR')
    page.tgt_lang_combo.setEditText('de-DE')
    page._last_dir = '/some/tm/folder'
    page.save_settings()

    fresh = TmEditorPage()
    qtbot.addWidget(fresh)
    fresh.restore_settings()
    assert lang_combo_code(fresh.src_lang_combo) == 'fr-FR'
    assert lang_combo_code(fresh.tgt_lang_combo) == 'de-DE'
    assert fresh._last_dir == '/some/tm/folder'


# ------------------------------------------------------- real fixture file

def test_opening_the_inline_markup_fixture_flags_tagged_rows(qtbot, monkeypatch):
    monkeypatch.setattr(
        QFileDialog, 'getOpenFileName', lambda *a, **kw: (tmx_path('inline_markup_qa.tmx'), ''))
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_tm()

    tag_notes = [page.entry_table.item(r, 2).text() for r in range(page.entry_table.rowCount())]
    assert '含标签' in tag_notes  # at least one row from the fixture has markup
    assert '' in tag_notes        # and at least one doesn't


# ---------------------------------------------------------- near-dup dialog

def test_near_dup_dialog_finds_clusters_and_defaults_to_keeping_first(qtbot):
    units = [
        _u('Click OK to continue.', '点击确定以继续。'),
        _u('Click OK to continue!', '点击确定以继续了！'),
        _u('Totally unrelated content about the weather outside today.', '完全无关的内容。'),
    ]
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(0.8)
    dialog._run_find()

    assert dialog.results_table.rowCount() == 2
    assert '共 1 簇，涉及 2 条记录' in dialog.summary_label.text()
    # first row of the (only) cluster defaults to checked ("keep")
    assert dialog.results_table.item(0, 0).checkState() == Qt.Checked
    assert dialog.results_table.item(1, 0).checkState() == Qt.Unchecked


def test_near_dup_dialog_no_clusters_below_threshold(qtbot):
    units = [
        _u('Click OK to continue.', '点击确定以继续。'),
        _u('Totally unrelated content about the weather outside today.', '完全无关的内容。'),
    ]
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog._run_find()
    assert dialog.results_table.rowCount() == 0
    assert '共 0 簇' in dialog.summary_label.text()
    assert dialog.indices_to_remove() == []


def test_near_dup_dialog_checking_a_row_unchecks_its_cluster_mates(qtbot):
    units = [
        _u('Click OK to continue.', '点击确定以继续。'),
        _u('Click OK to continue!', '点击确定以继续了！'),
        _u('Click OK to continue please.', '点击确定以继续吧！'),
    ]
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(0.6)
    dialog._run_find()
    assert dialog.results_table.rowCount() == 3

    dialog.results_table.item(2, 0).setCheckState(Qt.Checked)
    assert dialog.results_table.item(0, 0).checkState() == Qt.Unchecked
    assert dialog.results_table.item(1, 0).checkState() == Qt.Unchecked
    assert dialog.results_table.item(2, 0).checkState() == Qt.Checked


def test_near_dup_dialog_cannot_uncheck_the_only_kept_row(qtbot):
    units = [
        _u('Click OK to continue.', '点击确定以继续。'),
        _u('Click OK to continue!', '点击确定以继续了！'),
    ]
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(0.6)
    dialog._run_find()
    assert dialog.results_table.item(0, 0).checkState() == Qt.Checked
    dialog.results_table.item(0, 0).setCheckState(Qt.Unchecked)
    # blocked -- re-checked immediately, "keep nothing" isn't a valid state
    assert dialog.results_table.item(0, 0).checkState() == Qt.Checked


def test_near_dup_dialog_indices_to_remove_matches_original_list(qtbot):
    keep = _u('Click OK to continue.', '点击确定以继续。')
    remove_me = _u('Click OK to continue!', '点击确定以继续了！')
    other = _u('Totally unrelated content about the weather outside today.', '完全无关。')
    units = [other, keep, remove_me]  # order matters -- indices must track original positions
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(0.8)
    dialog._run_find()
    assert dialog.indices_to_remove() == [2]  # remove_me's original index


def test_near_dup_dialog_side_tgt_clusters_on_target_text(qtbot):
    units = [
        _u('An orange cat sleeps on the windowsill.', '点击确定以继续。'),
        _u('The stock market fell sharply this afternoon.', '点击确定以继续了！'),
    ]
    dialog = _NearDupDialog(None, units)
    qtbot.addWidget(dialog)
    dialog.threshold_spin.setValue(0.8)
    dialog.side_combo.setCurrentIndex(dialog.side_combo.findData('tgt'))
    dialog._run_find()
    assert dialog.results_table.rowCount() == 2


# ------------------------------------------------- near-dup page integration

def test_near_dup_button_disabled_flow_with_empty_tm(qtbot):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._open_near_dup_dialog()
    assert '没有记录' in page.status_label.text()


def test_near_dup_dialog_cancelled_leaves_units_untouched(qtbot, monkeypatch):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [_u('Click OK to continue.', '点击确定以继续。'),
                   _u('Click OK to continue!', '点击确定以继续了！')]
    monkeypatch.setattr(_NearDupDialog, 'exec', lambda self: QDialog.Rejected)
    page._open_near_dup_dialog()
    assert len(page._units) == 2
    assert page._dirty is False


def test_near_dup_applied_removes_units_and_marks_dirty(qtbot, monkeypatch):
    page = TmEditorPage()
    qtbot.addWidget(page)
    page._units = [
        _u('Click OK to continue.', '点击确定以继续。'),
        _u('Click OK to continue!', '点击确定以继续了！'),
        _u('Totally unrelated content about the weather outside today.', '完全无关的内容。'),
    ]

    def fake_exec(self):
        self.threshold_spin.setValue(0.8)
        self._run_find()
        return QDialog.Accepted
    monkeypatch.setattr(_NearDupDialog, 'exec', fake_exec)

    page._open_near_dup_dialog()
    assert page._dirty is True
    assert len(page._units) == 2
    assert page.entry_table.rowCount() == 2
    assert '已删除 1 条近重复记录' in page.status_label.text()
    remaining_src = [u.src_text for u in page._units]
    assert 'Totally unrelated content about the weather outside today.' in remaining_src
    # exactly one of the two near-duplicate variants survived
    assert sum(1 for s in remaining_src if s.startswith('Click OK to continue')) == 1
