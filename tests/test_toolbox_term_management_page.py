import pytest
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from language_tools.model import TranslationUnit
from language_tools.terms import glossary as glossary_module
from language_tools.terms.filelock import SidecarLock
from language_tools.terms.model import TermEntry
from language_tools.writers import tmx_writer
from toolbox.tools.term_management.page import TermManagementPage, _TermEntryDialog


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def _write_tmx(path, units):
    tmx_writer.write(str(path), units, 'en-US', 'zh-CN')


def _entry(src_term, tgt_term, **kw):
    return TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term=src_term, tgt_term=tgt_term, **kw)


# ------------------------------------------------------------------ dialog
# _TermEntryDialog.exec() is modal and would block in a real run; tests
# below that go through the page's _add_entry()/_edit_selected_entry()
# monkeypatch exec() itself (fill fields, return Accepted) rather than
# calling .exec() for real -- same "swap out the blocking call" approach
# QFileDialog-driven flows use further down this file.

def test_dialog_rejects_empty_terms_without_accepting(qtbot):
    dialog = _TermEntryDialog()
    dialog._on_accept()
    assert dialog.result() != QDialog.Accepted
    # isVisible() would be False regardless (the dialog itself was never
    # shown), so check the label's own hidden flag instead -- isHidden()
    # reflects the explicit setVisible() call directly, not the ancestor
    # chain's actual on-screen state.
    assert not dialog.error_label.isHidden()


def test_dialog_prefills_from_existing_entry(qtbot):
    entry = _entry('cloud', '云', status='forbidden', domain='tech', note='测试备注')
    dialog = _TermEntryDialog(entry=entry)
    assert dialog.src_term_edit.text() == 'cloud'
    assert dialog.tgt_term_edit.text() == '云'
    assert dialog.status_combo.currentData() == 'forbidden'
    assert dialog.domain_edit.text() == 'tech'
    assert dialog.note_edit.text() == '测试备注'


def test_dialog_result_values_strips_whitespace_and_blanks_optional_fields(qtbot):
    dialog = _TermEntryDialog()
    dialog.src_term_edit.setText('  cloud  ')
    dialog.tgt_term_edit.setText('  云  ')
    values = dialog.result_values()
    assert values['src_term'] == 'cloud'
    assert values['tgt_term'] == '云'
    assert values['domain'] is None
    assert values['note'] is None


# --------------------------------------------------------------- glossary tab

def test_glossary_tab_starts_empty_with_save_disabled(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    assert page.entry_table.rowCount() == 0
    assert not page.glossary_save_btn.isEnabled()


def test_add_entry_via_dialog_appends_to_table(qtbot, monkeypatch):
    def fake_exec(self):
        self.src_term_edit.setText('cloud')
        self.tgt_term_edit.setText('云')
        return QDialog.Accepted
    monkeypatch.setattr(_TermEntryDialog, 'exec', fake_exec)

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._add_entry()
    assert page.entry_table.rowCount() == 1
    assert page.entry_table.item(0, 0).text() == 'cloud'
    assert page.entry_table.item(0, 1).text() == '云'
    assert page.entry_table.item(0, 2).text() == '推荐译法'
    assert '已添加' in page.log.toPlainText()


def test_dialog_cancel_does_not_add_entry(qtbot, monkeypatch):
    monkeypatch.setattr(_TermEntryDialog, 'exec', lambda self: QDialog.Rejected)
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._add_entry()
    assert page.entry_table.rowCount() == 0


def test_edit_selected_entry_updates_table(qtbot, monkeypatch):
    def fake_exec(self):
        self.tgt_term_edit.setText('大数据（已更新）')
        return QDialog.Accepted
    monkeypatch.setattr(_TermEntryDialog, 'exec', fake_exec)

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('big data', '大数据')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)
    page._edit_selected_entry()
    assert page.entry_table.item(0, 1).text() == '大数据（已更新）'


def test_edit_requires_exactly_one_selected_row(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('a', 'A'), _entry('b', 'B')]
    page._refresh_entry_table()
    page._edit_selected_entry()
    assert '只能选一条' in page.log.toPlainText()


def test_remove_selected_entries_removes_only_selected(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('a', 'A'), _entry('b', 'B')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)
    page.remove_entry_btn.click()
    assert len(page._entries) == 1
    assert page._entries[0].src_term == 'b'
    assert page.entry_table.rowCount() == 1


def test_remove_with_no_selection_shows_validation_error(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page.remove_entry_btn.click()
    assert '请先选中要删除' in page.log.toPlainText()


def test_open_glossary_populates_table_and_enables_save(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云', status='forbidden', note='测试')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    assert page.entry_table.rowCount() == 1
    assert page.entry_table.item(0, 1).text() == '云'
    assert page.glossary_save_btn.isEnabled()
    assert page.glossary_path_label.text() == str(path)


def test_open_glossary_missing_header_shows_error_not_crash(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('foo,bar\ncloud,云\n', encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    assert '打开失败' in page.log.toPlainText()
    assert page.entry_table.rowCount() == 0


def test_save_as_writes_file_and_enables_plain_save(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云', status='forbidden', note='测试')]
    page._save_glossary_as()

    assert out.exists()
    back = glossary_module.read(str(out), 'en-US', 'zh-CN')
    assert len(back) == 1
    assert back[0].status == 'forbidden'
    assert page.glossary_save_btn.isEnabled()
    assert '已保存' in page.log.toPlainText()


def test_save_without_a_path_yet_falls_back_to_save_as(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    # glossary_save_btn is disabled until a path exists (see the "starts
    # disabled" test above), so a real .click() would be a no-op here --
    # this exercises the fallback branch directly, the same defensive-
    # guard testing approach qa_check's own "noop before any check" test
    # uses for its equally-disabled export button.
    page._save_glossary()

    assert out.exists()


# ----------------------------------------------------------------- check tab

def test_check_empty_input_shows_validation_error(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_btn.click()
    assert '请先选择要检查的翻译记忆库文件' in page.log.toPlainText()


def test_check_missing_glossary_shows_validation_error(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('big data.', '大数据。')])
    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_corpus_edit.setText(str(src))
    page.check_btn.click()
    assert '请先选择术语库文件' in page.log.toPlainText()


def test_check_missing_file_shows_validation_error(qtbot, tmp_path):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_corpus_edit.setText(str(tmp_path / 'does-not-exist.tmx'))
    page.check_glossary_edit.setText(str(tmp_path / 'also-missing.csv'))
    page.check_btn.click()
    assert '找不到翻译记忆库文件' in page.log.toPlainText()


def test_export_before_any_check_is_a_silent_noop(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._start_export()
    assert page.log.toPlainText() == ''


def test_check_end_to_end_flags_forbidden_hit_and_enables_export(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('This is about big data.', '这是关于大资料的。'),
                      _u('Clean sentence.', '干净的句子。')])
    glossary_module.write(str(gloss), [_entry('big data', '大资料', status='forbidden', note='旧译名')])

    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_corpus_edit.setText(str(src))
    page.check_glossary_edit.setText(str(gloss))
    assert not page.check_export_btn.isEnabled()
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert '检查完成' in page.log.toPlainText()
    assert '共 2 条，1 条命中禁用译法' in page.check_summary_label.text()
    assert page.check_export_btn.isEnabled()
    assert page.check_table.rowCount() == 1  # hide_clean checked by default
    assert 'big data→大资料（旧译名）' in page.check_table.item(0, 3).text()


def test_check_hide_clean_checkbox_toggles_row_count(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('This is about big data.', '这是关于大资料的。'),
                      _u('Clean sentence.', '干净的句子。')])
    glossary_module.write(str(gloss), [_entry('big data', '大资料', status='forbidden')])

    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_corpus_edit.setText(str(src))
    page.check_glossary_edit.setText(str(gloss))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.check_table.rowCount() == 1
    page.check_hide_clean_chk.setChecked(False)
    assert page.check_table.rowCount() == 2


def test_check_export_writes_csv_with_term_issues_column(qtbot, monkeypatch, tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    out = tmp_path / 'report.csv'
    _write_tmx(src, [_u('This is about big data.', '这是关于大资料的。')])
    glossary_module.write(str(gloss), [_entry('big data', '大资料', status='forbidden')])
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page.check_corpus_edit.setText(str(src))
    page.check_glossary_edit.setText(str(gloss))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page._start_export()
    qtbot.waitUntil(lambda: page.check_export_btn.isEnabled(), timeout=5000)

    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert 'term_issues' in content
    assert 'big data->大资料' in content
    assert '已导出到' in page.log.toPlainText()


# ------------------------------------------------------------ dirty tracking

def test_page_starts_clean(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    assert page.has_unsaved_changes() is False


def test_add_entry_marks_dirty(qtbot, monkeypatch):
    monkeypatch.setattr(_TermEntryDialog, 'exec', lambda self: QDialog.Rejected)
    page = TermManagementPage()
    qtbot.addWidget(page)

    def fake_exec(self):
        self.src_term_edit.setText('cloud')
        self.tgt_term_edit.setText('云')
        return QDialog.Accepted
    monkeypatch.setattr(_TermEntryDialog, 'exec', fake_exec)
    page._add_entry()
    assert page.has_unsaved_changes() is True


def test_edit_entry_marks_dirty(qtbot, monkeypatch):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('big data', '大数据')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)

    monkeypatch.setattr(_TermEntryDialog, 'exec',
                         lambda self: (self.tgt_term_edit.setText('改过了'), QDialog.Accepted)[1])
    page._edit_selected_entry()
    assert page.has_unsaved_changes() is True


def test_remove_entry_marks_dirty(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('a', 'A')]
    page._refresh_entry_table()
    page.entry_table.selectRow(0)
    page.remove_entry_btn.click()
    assert page.has_unsaved_changes() is True


def test_open_glossary_resets_dirty(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._dirty = True  # pretend there was unsaved work before opening a different file
    page._open_glossary()
    assert page.has_unsaved_changes() is False
    page.cleanup()


def test_save_resets_dirty(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    page._dirty = True
    page._save_glossary_as()
    assert page.has_unsaved_changes() is False
    page.cleanup()


def test_unsaved_changes_label(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    assert page.unsaved_changes_label() == '术语管理'


# -------------------------------------------------- save_unsaved_changes()

def test_save_unsaved_changes_is_noop_when_clean(qtbot):
    page = TermManagementPage()
    qtbot.addWidget(page)
    assert page.save_unsaved_changes() is True


def test_save_unsaved_changes_writes_to_existing_path(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    page._entries.append(_entry('cloud', '云'))
    page._dirty = True

    assert page.save_unsaved_changes() is True
    assert page.has_unsaved_changes() is False
    back = glossary_module.read(str(path), 'en-US', 'zh-CN')
    assert len(back) == 1
    page.cleanup()


def test_save_unsaved_changes_prompts_for_path_when_none_yet(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    page._dirty = True

    assert page.save_unsaved_changes() is True
    assert out.exists()
    page.cleanup()


def test_save_unsaved_changes_returns_false_when_save_dialog_cancelled(qtbot, monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: ('', ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    page._dirty = True

    assert page.save_unsaved_changes() is False
    assert page.has_unsaved_changes() is True  # still dirty, nothing was lost


# --------------------------------------------------------------- file locking

def test_open_glossary_shows_warning_when_office_marker_present(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    (tmp_path / ('~$%s' % path.name)).write_bytes(b'')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **kw: QMessageBox.Cancel)

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    # Cancelled at the warning -- must not actually load the file.
    assert page.entry_table.rowCount() == 0
    assert page._glossary_path is None


def test_open_glossary_proceeds_past_office_marker_warning_if_confirmed(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    (tmp_path / ('~$%s' % path.name)).write_bytes(b'')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **kw: QMessageBox.Yes)

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    assert page.entry_table.rowCount() == 1
    page.cleanup()


def test_open_glossary_fails_when_already_locked_by_another_instance(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    other = SidecarLock(str(path))
    other.acquire()
    try:
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))
        page = TermManagementPage()
        qtbot.addWidget(page)
        page._open_glossary()
        assert page.entry_table.rowCount() == 0
        assert '另一个实例' in page.log.toPlainText()
    finally:
        other.release()


def test_open_glossary_acquires_lock_and_cleanup_releases_it(qtbot, monkeypatch, tmp_path):
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    assert page._file_lock is not None

    # While our lock is held, a second attempt from elsewhere must fail --
    # this is the point of holding it in the first place.
    other = SidecarLock(str(path))
    with pytest.raises(OSError):
        other.acquire()

    page.cleanup()
    assert page._file_lock is None
    # Released now, so someone else (or a re-open) can acquire it.
    other.acquire()
    other.release()


def test_open_a_different_glossary_releases_the_previous_lock(qtbot, monkeypatch, tmp_path):
    path_a = tmp_path / 'a.csv'
    path_b = tmp_path / 'b.csv'
    glossary_module.write(str(path_a), [_entry('cloud', '云')])
    glossary_module.write(str(path_b), [_entry('api', '接口')])

    page = TermManagementPage()
    qtbot.addWidget(page)

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path_a), ''))
    page._open_glossary()

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path_b), ''))
    page._open_glossary()

    # path_a's lock should be free again -- it was released when path_b opened.
    a_lock = SidecarLock(str(path_a))
    a_lock.acquire()
    a_lock.release()
    page.cleanup()


def test_save_as_to_new_path_transfers_the_lock(qtbot, monkeypatch, tmp_path):
    path_a = tmp_path / 'a.csv'
    path_b = tmp_path / 'b.csv'
    glossary_module.write(str(path_a), [_entry('cloud', '云')])

    page = TermManagementPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path_a), ''))
    page._open_glossary()

    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(path_b), ''))
    page._save_glossary_as()

    # a's lock released, b's lock now held.
    a_lock = SidecarLock(str(path_a))
    a_lock.acquire()
    a_lock.release()
    with pytest.raises(OSError):
        SidecarLock(str(path_b)).acquire()
    page.cleanup()


# ---------------------------------------------------- split save-format filter

def test_save_as_defaults_to_csv_when_filter_unselected(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary'  # no extension typed
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(out), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    page._save_glossary_as()

    assert (tmp_path / 'glossary.csv').exists()
    page.cleanup()


def test_save_as_uses_xlsx_extension_when_that_filter_is_selected(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'glossary'  # no extension typed
    monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                         lambda *a, **kw: (str(out), 'Excel (*.xlsx)'))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._entries = [_entry('cloud', '云')]
    page._save_glossary_as()

    assert (tmp_path / 'glossary.xlsx').exists()
    page.cleanup()


def test_reopening_the_same_already_open_file_does_not_self_block(qtbot, monkeypatch, tmp_path):
    # Regression test: acquiring a second SidecarLock on a path this page
    # already holds one for would incorrectly fail (POSIX flock() denies
    # a second same-process lock via a different fd), so re-opening the
    # currently-open file to discard local edits and reload from disk
    # must not try to acquire a new lock at all.
    path = tmp_path / 'glossary.csv'
    glossary_module.write(str(path), [_entry('cloud', '云')])
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(path), ''))

    page = TermManagementPage()
    qtbot.addWidget(page)
    page._open_glossary()
    assert page.entry_table.rowCount() == 1

    page._entries.append(_entry('extra', '额外'))
    page._refresh_entry_table()
    assert page.entry_table.rowCount() == 2

    page._open_glossary()  # reload from disk, discarding the in-memory addition
    assert page.entry_table.rowCount() == 1  # back to what's on disk
    assert page.has_unsaved_changes() is False
    page.cleanup()
