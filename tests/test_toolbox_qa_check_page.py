from conftest import tmx_path

from language_tools.model import TranslationUnit
from language_tools.writers import tmx_writer
from toolbox.tools.qa_check.page import QaCheckPage


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def _write_tmx(path, units):
    tmx_writer.write(str(path), units, 'en-US', 'zh-CN')


# ------------------------------------------------------------- validation

def test_empty_input_shows_validation_error(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.check_btn.click()
    assert '请先选择要检查的文件' in page.log.toPlainText()


def test_missing_file_shows_validation_error(qtbot, tmp_path):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(tmp_path / 'does-not-exist.tmx'))
    page.check_btn.click()
    assert '找不到这个文件' in page.log.toPlainText()


def test_export_before_any_check_is_a_silent_noop(qtbot):
    # export_btn is disabled whenever there are no results, so .click()
    # is a no-op through the UI; call the handler directly to confirm the
    # defensive guard doesn't crash if ever invoked with no results.
    page = QaCheckPage()
    qtbot.addWidget(page)
    page._start_export()
    assert page.log.toPlainText() == ''


# ---------------------------------------------------------------- checking

def test_export_button_disabled_until_check_succeeds(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    assert not page.export_btn.isEnabled()


def test_check_end_to_end_updates_summary_and_enables_export(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert '检查完成' in page.log.toPlainText()
    assert '共 8 条' in page.summary_label.text()
    assert '6 条有问题' in page.summary_label.text()
    assert page.export_btn.isEnabled()


def test_default_view_hides_clean_rows(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.hide_clean_chk.isChecked()
    assert page.results_table.rowCount() == 6  # 8 total, 2 clean (tu 1 and tu 4)


def test_unchecking_hide_clean_shows_all_rows(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.hide_clean_chk.setChecked(False)
    assert page.results_table.rowCount() == 8


def test_type_filter_narrows_to_matching_rows_only(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    tag_mismatch_index = next(
        i for i in range(page.type_filter_combo.count())
        if page.type_filter_combo.itemData(i) == 'TAG_MISMATCH')
    page.type_filter_combo.setCurrentIndex(tag_mismatch_index)
    assert page.results_table.rowCount() == 2

    for row in range(page.results_table.rowCount()):
        assert 'TAG_MISMATCH' in page.results_table.item(row, 3).text()


def test_type_filter_reset_to_all_restores_full_flagged_view(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.type_filter_combo.setCurrentIndex(1)  # some specific type
    page.type_filter_combo.setCurrentIndex(0)  # back to "全部问题类型"
    assert page.results_table.rowCount() == 6


def test_table_columns_show_src_tgt_and_issue_codes(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 1).text() == 'Found %d results.'
    assert page.results_table.item(0, 2).text() == '找到了结果。'
    assert page.results_table.item(0, 3).text() == 'PLACEHOLDER_MISMATCH'


def test_check_again_clears_stale_results_first(qtbot, tmp_path):
    good = tmp_path / 'good.tmx'
    _write_tmx(good, [_u('Hello', '你好')])

    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
    assert page.results_table.rowCount() > 0 or page.summary_label.text()

    # Second run against a missing file: validation fails before the
    # worker starts, but the *previous* run's stale table/summary must
    # not keep showing as if it were current.
    page.input_edit.setText(str(tmp_path / 'missing.tmx'))
    page.check_btn.click()
    assert page.results_table.rowCount() == 0
    assert page.summary_label.text() == ''


# -------------------------------------------------------------------- export

def test_export_writes_full_csv_including_clean_rows(qtbot, tmp_path, monkeypatch):
    out = tmp_path / 'report.csv'
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    # hide_clean is on by default (display-only) -- export must still
    # include all 8 rows, not just the 6 currently visible in the table.
    monkeypatch.setattr(
        'toolbox.tools.qa_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()
    qtbot.waitUntil(lambda: page.export_btn.isEnabled(), timeout=5000)

    assert '已导出到' in page.log.toPlainText()
    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert content.count('\n') >= 9  # header + 8 data rows (+ trailing newline)
    assert 'TAG_MISMATCH' in content


def test_export_cancelled_dialog_does_not_error(qtbot, monkeypatch):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.qa_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: ('', ''))
    page.export_btn.click()  # user cancelled the save dialog
    assert '出错了' not in page.log.toPlainText()
    assert '导出失败' not in page.log.toPlainText()
