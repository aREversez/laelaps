import os
import shutil

from toolbox.tools.batch_convert.page import BatchConvertPage
from toolbox.widgets import lang_combo_code

from conftest import fixture_path, tmx_path


def _status_text(page, row):
    return page.file_table.item(row, 1).text()


def test_empty_list_shows_validation_error(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page.start_btn.click()
    assert '请先添加要转换的文件' in page.summary_label.text()


def test_missing_lang_for_bilingual_source_shows_error(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._refresh_count()
    page.src_edit.setEditText('')
    page.start_btn.click()
    assert '原文语言和译文语言' in page.summary_label.text()


def test_no_output_format_selected_shows_error(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._refresh_count()
    page.chk_sdltm.setChecked(False)
    page.chk_tmx.setChecked(False)
    page.chk_csv.setChecked(False)
    page.start_btn.click()
    assert '至少勾选一种要生成的格式' in page.summary_label.text()


def test_adding_same_file_twice_does_not_duplicate(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._append_path(fixture_path('basic.docx'))
    assert len(page._paths) == 1
    assert page.file_table.rowCount() == 1


def test_remove_selected_keeps_paths_and_rows_in_sync(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._append_path(fixture_path('table_layout.docx'))
    page.file_table.selectRow(0)
    page._remove_selected()
    assert page._paths == [fixture_path('table_layout.docx')]
    assert page.file_table.rowCount() == 1
    assert page.file_table.item(0, 0).toolTip() == fixture_path('table_layout.docx')


def test_clear_all_empties_table_and_paths(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._append_path(fixture_path('table_layout.docx'))
    page._clear_all()
    assert page._paths == []
    assert page.file_table.rowCount() == 0
    assert page.count_label.text() == '共 0 个文件'


def test_add_folder_scans_recursively_and_skips_unsupported_files(qtbot, tmp_path):
    sub = tmp_path / 'nested'
    sub.mkdir()
    shutil.copy(fixture_path('basic.docx'), tmp_path / 'a.docx')
    shutil.copy(fixture_path('table_layout.docx'), sub / 'b.docx')
    (tmp_path / 'notes.txt').write_text('not a supported format')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    from PySide6.QtWidgets import QFileDialog
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(tmp_path))
    page._add_folder()

    assert len(page._paths) == 2
    assert str(tmp_path / 'a.docx') in page._paths
    assert str(sub / 'b.docx') in page._paths


def test_new_rows_start_pending(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    assert _status_text(page, 0) == '等待中'


def test_real_batch_conversion_end_to_end(qtbot, tmp_path):
    docx_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')
    table_src = shutil.copy(fixture_path('table_layout.docx'), tmp_path / 'table_layout.docx')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(docx_src))
    page._append_path(str(table_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')
    # layout_combo stays at its default 自动识别 -- basic.docx is numbered
    # layout and table_layout.docx is table layout, so forcing either
    # technical value for the whole batch would break the other file;
    # readers.docx's own per-file auto-detection (see language_tools/
    # readers/docx.py) is what makes a mixed-layout batch work at all.

    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert '全部完成' in page.summary_label.text()
    assert '2 个文件都转换成功' in page.summary_label.text()
    assert '成功' in _status_text(page, 0)
    assert '成功' in _status_text(page, 1)
    for base in (tmp_path / 'basic', tmp_path / 'table_layout'):
        assert (base.with_suffix('.sdltm')).exists()
        assert (base.with_suffix('.tmx')).exists()
        assert (base.with_suffix('.csv')).exists()


def test_batch_with_one_bad_file_reports_partial_failure(qtbot, tmp_path):
    good_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'good.docx')
    bad_src = tmp_path / 'bad.docx'
    bad_src.write_bytes(b'not actually a docx file')
    # bad file placed in the middle (not last) so a regression that stops
    # the whole batch on the first error -- instead of skipping just that
    # file and continuing -- would leave this third file's row stuck at
    # "等待中" and get caught below, rather than being masked by bad
    # happening to be the last file processed anyway.
    good_src2 = shutil.copy(fixture_path('table_layout.docx'), tmp_path / 'good2.docx')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(good_src))
    page._append_path(str(bad_src))
    page._append_path(str(good_src2))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')

    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert '2 个成功，1 个失败' in page.summary_label.text()
    assert '成功' in _status_text(page, 0)
    assert '成功' not in _status_text(page, 1)
    assert '成功' in _status_text(page, 2)


def test_same_format_output_is_skipped_per_file(qtbot, tmp_path):
    # Batch contains one .tmx (whose own format matches a checked output)
    # alongside a .docx (no such conflict) -- the .tmx file should still
    # convert (sdltm/csv), just skip re-generating tmx for itself, while
    # the .docx gets all three formats untouched.
    tmx_src = shutil.copy(tmx_path('inline_markup_qa.tmx'), tmp_path / 'memory.tmx')
    docx_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(tmx_src))
    page._append_path(str(docx_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')

    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert '已跳过同格式选项' in _status_text(page, 0)
    assert '已跳过同格式选项' not in _status_text(page, 1)
    assert (tmp_path / 'memory.tmx').exists()  # source file itself untouched
    assert (tmp_path / 'basic.tmx').exists()
    assert (tmp_path / 'basic.sdltm').exists()
    assert (tmp_path / 'basic.csv').exists()


def test_controls_disabled_while_running_and_reenabled_after(qtbot, tmp_path):
    src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')

    page.start_btn.click()
    # Worker runs on a real QThread; by the time isEnabled() is false the
    # disabling has definitely happened (it's the very first thing
    # _start_batch does after validation), so no race to poll around here.
    assert not page.start_btn.isEnabled()
    assert not page.add_files_btn.isEnabled()
    assert not page.add_folder_btn.isEnabled()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)
    assert page.remove_btn.isEnabled()
    assert page.clear_btn.isEnabled()
    assert page.add_files_btn.isEnabled()
    assert page.add_folder_btn.isEnabled()


def test_adding_files_after_run_clears_finished_rows(qtbot, tmp_path, monkeypatch):
    good_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(good_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)
    assert page.file_table.rowCount() == 1  # sanity: one finished row before adding more

    another_src = shutil.copy(fixture_path('table_layout.docx'), tmp_path / 'table_layout.docx')
    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getOpenFileNames',
        staticmethod(lambda *a, **k: ([str(another_src)], '')),
    )
    page._add_files()

    # The finished basic.docx row is gone; only the newly-added, still-等待中 file remains.
    assert page._paths == [str(another_src)]
    assert page.file_table.rowCount() == 1
    assert _status_text(page, 0) == '等待中'


def test_adding_folder_after_run_clears_finished_rows(qtbot, tmp_path, monkeypatch):
    good_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(good_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    other_dir = tmp_path / 'next_batch'
    other_dir.mkdir()
    other_src = shutil.copy(fixture_path('table_layout.docx'), other_dir / 'table_layout.docx')
    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getExistingDirectory',
        staticmethod(lambda *a, **k: str(other_dir)),
    )
    page._add_folder()

    assert page._paths == [str(other_src)]
    assert page.file_table.rowCount() == 1
    assert _status_text(page, 0) == '等待中'


def test_adding_more_files_keeps_still_pending_rows(qtbot, tmp_path, monkeypatch):
    # Two files queued, neither run yet -- adding a third shouldn't clear
    # the first two, since 等待中 rows aren't "finished".
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._refresh_count()

    third = shutil.copy(fixture_path('table_layout.docx'), tmp_path / 'table_layout.docx')
    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getOpenFileNames',
        staticmethod(lambda *a, **k: ([str(third)], '')),
    )
    page._add_files()

    assert page._paths == [fixture_path('basic.docx'), str(third)]
    assert page.file_table.rowCount() == 2


def test_cancelling_add_files_dialog_does_not_clear_finished_rows(qtbot, tmp_path, monkeypatch):
    good_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(good_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getOpenFileNames',
        staticmethod(lambda *a, **k: ([], '')),  # user cancelled the dialog
    )
    page._add_files()

    assert page._paths == [str(good_src)]
    assert page.file_table.rowCount() == 1
    assert '成功' in _status_text(page, 0)


# ------------------------------------------------------------- settings

def test_restore_settings_defaults_when_nothing_saved_yet(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page.restore_settings()
    assert lang_combo_code(page.src_edit) == 'en-US'
    assert lang_combo_code(page.tgt_edit) == 'zh-CN'
    assert page.layout_combo.currentData() == 'auto'
    assert page.chk_sdltm.isChecked() and page.chk_tmx.isChecked() and page.chk_csv.isChecked()
    assert page.chk_qa.isChecked() is False
    assert page._last_dir == ''


def test_save_then_restore_settings_round_trips(qtbot):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page.src_edit.setEditText('fr-FR')
    page.tgt_edit.setEditText('de-DE')
    idx = page.layout_combo.findData('alternating')
    page.layout_combo.setCurrentIndex(idx)
    page.chk_sdltm.setChecked(False)
    page.chk_qa.setChecked(True)
    page._last_dir = '/some/batch/folder'
    page.save_settings()

    fresh = BatchConvertPage()
    qtbot.addWidget(fresh)
    fresh.restore_settings()
    assert lang_combo_code(fresh.src_edit) == 'fr-FR'
    assert lang_combo_code(fresh.tgt_edit) == 'de-DE'
    assert fresh.layout_combo.currentData() == 'alternating'
    assert fresh.chk_sdltm.isChecked() is False
    assert fresh.chk_tmx.isChecked() is True
    assert fresh.chk_csv.isChecked() is True
    assert fresh.chk_qa.isChecked() is True
    assert fresh._last_dir == '/some/batch/folder'


def test_add_files_and_add_folder_share_and_update_last_dir(qtbot, tmp_path, monkeypatch):
    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._last_dir = '/wherever/i/was'

    seen = {}
    src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    def _fake_get_files(parent, caption, dir_, filt):
        seen['files_start_dir'] = dir_
        return [str(src)], ''

    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getOpenFileNames', _fake_get_files)
    page._add_files()
    assert seen['files_start_dir'] == '/wherever/i/was'
    assert page._last_dir == str(tmp_path)  # moved to wherever the picked file lives

    other_dir = tmp_path / 'next'
    other_dir.mkdir()

    def _fake_get_folder(parent, caption, dir_):
        seen['folder_start_dir'] = dir_
        return str(other_dir)

    monkeypatch.setattr(
        'toolbox.tools.batch_convert.page.QFileDialog.getExistingDirectory', _fake_get_folder)
    page._add_folder()
    assert seen['folder_start_dir'] == str(tmp_path)  # picked up where 添加文件 left it
    assert page._last_dir == str(other_dir)  # ...and moved on to the folder just picked


def test_cleanup_waits_for_running_batch_instead_of_crashing(qtbot, tmp_path):
    """Regression test for the intermittent close-while-converting crash:
    ``main_window.py``'s ``closeEvent()`` calls ``cleanup()`` on every
    page with no ``qtbot.waitUntil`` in between, so a close landing
    mid-batch used to tear down a still-running ``QThread`` (see
    ``BatchConvertPage.cleanup()``'s docstring). Calling ``cleanup()``
    right after ``start_btn.click()``, with no wait in between,
    reproduces that same race deliberately instead of relying on timing
    luck to hit it.
    """
    docx_src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    page = BatchConvertPage()
    qtbot.addWidget(page)
    page._append_path(str(docx_src))
    page._refresh_count()
    page.src_edit.setEditText('en-US')
    page.tgt_edit.setEditText('zh-CN')

    page.start_btn.click()
    page.cleanup()  # simulates closeEvent() landing mid-batch

    assert page._worker.isFinished()
    assert (tmp_path / 'basic.sdltm').exists()
