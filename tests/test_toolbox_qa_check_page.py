from conftest import tmx_path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

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
        assert '标签不匹配' in page.results_table.item(row, 3).text()


def test_type_filter_reset_to_all_restores_full_flagged_view(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.type_filter_combo.setCurrentIndex(1)  # some specific type
    page.type_filter_combo.setCurrentIndex(0)  # back to "全部问题类型"
    assert page.results_table.rowCount() == 6


def test_table_columns_show_src_tgt_and_translated_issue_labels(qtbot, tmp_path):
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
    # Chinese label, not the raw code -- a bare "PLACEHOLDER_MISMATCH"
    # means nothing to a non-technical reviewer.
    assert page.results_table.item(0, 3).text() == '占位符不匹配'


def test_table_shows_multiple_issue_labels_joined_for_one_row(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.hide_clean_chk.setChecked(False)
    # tu 6 (row index 5) has both PLACEHOLDER_MISMATCH and SOURCE_CONFLICT
    cell_text = page.results_table.item(5, 3).text()
    assert '占位符不匹配' in cell_text
    assert '原文冲突' in cell_text


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
    assert 'TAG_MISMATCH' in content  # raw code still present (Excel-filterable)
    assert '标签不匹配' in content  # and the Chinese label leads, per the same fix


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


# ------------------------------------------------------------------- layout

def test_results_table_has_its_own_section_title(qtbot):
    # Regression guard: the table used to sit under a "筛选结果" title that
    # actually belonged to the filter controls above it, not the table --
    # a reviewer scanning section titles for "where are my results" would
    # find nothing labeled as such.
    page = QaCheckPage()
    qtbot.addWidget(page)
    titles = [label.text() for label in page.findChildren(QLabel)
              if label.property('role') == 'sectionTitle']
    assert 'QA 结果' in titles
    assert '筛选结果' not in titles


def test_results_table_header_is_left_aligned(qtbot):
    # Header text used to default to centered while item text defaults to
    # left -- with 原文/译文 stretched wide and often long, that mismatch
    # looked inconsistent. Both should now agree.
    page = QaCheckPage()
    qtbot.addWidget(page)
    alignment = page.results_table.horizontalHeader().defaultAlignment()
    assert alignment & Qt.AlignLeft


# --------------------------------------------------------------- wrap/highlight

def test_wrap_off_by_default_uses_plain_items_for_clean_rows(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    assert not page.wrap_chk.isChecked()
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))  # no NUMBER_MISMATCH rows
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.results_table.item(0, 1) is not None
    assert page.results_table.cellWidget(0, 1) is None


def test_toggling_wrap_on_switches_clean_row_to_wrapped_label(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])  # PLACEHOLDER_MISMATCH, not NUMBER_MISMATCH
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    label = page.results_table.cellWidget(0, 1)
    assert isinstance(label, QLabel)
    assert label.wordWrap()
    # item(row, col) is only meaningful for the plain-item path; wrap mode
    # renders through a cell widget instead, so the item slot is unused.
    assert page.results_table.item(0, 1) is None


def test_toggling_wrap_off_again_restores_plain_items_for_clean_row(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])  # PLACEHOLDER_MISMATCH, not NUMBER_MISMATCH
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    page.wrap_chk.setChecked(False)
    assert page.results_table.cellWidget(0, 1) is None
    assert page.results_table.item(0, 1).text() == 'Found %d results.'


def test_number_mismatch_row_uses_label_even_without_wrap(qtbot, tmp_path):
    # Highlighting must not depend on the wrap toggle -- a NUMBER_MISMATCH
    # row needs a QLabel (for rich-text highlighting) in both view modes.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.wrap_chk.isChecked()
    src_label = page.results_table.cellWidget(0, 1)
    tgt_label = page.results_table.cellWidget(0, 2)
    assert isinstance(src_label, QLabel)
    assert not src_label.wordWrap()
    assert '<b style="color:#B23B3B; font-weight:600;">42</b>' in src_label.text()
    assert '<b style="color:#B23B3B; font-weight:600;">43</b>' in tgt_label.text()


def test_number_mismatch_highlighting_present_in_both_wrap_states(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    for wrapped in (False, True, False):
        page.wrap_chk.setChecked(wrapped)
        src_html = page.results_table.cellWidget(0, 1).text()
        tgt_html = page.results_table.cellWidget(0, 2).text()
        assert '<b style="color:#B23B3B; font-weight:600;">42</b>' in src_html
        assert '<b style="color:#B23B3B; font-weight:600;">43</b>' in tgt_html


def test_wrap_on_does_not_highlight_rows_without_number_mismatch(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])  # PLACEHOLDER_MISMATCH, not NUMBER_MISMATCH
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    src_html = page.results_table.cellWidget(0, 1).text()
    assert '<b' not in src_html


def test_short_row_does_not_grow_row_height_in_wrap_mode(qtbot, tmp_path):
    # Regression guard: every row used to grow to some uniform, overly
    # tall height in wrap mode regardless of actual content -- a
    # three-character row shouldn't need more height than one line. Needs
    # a real, shown window: column width (and therefore whether the long
    # sentence actually needs to wrap at all) is meaningless on an
    # un-shown widget's default/fallback geometry.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [
        _u(
            'We shipped 42 units to the warehouse last quarter, well above '
            'the 43 units originally forecast for the same period.',
            '我们发货了43个单位。'),
        _u('Hi!', '你好！'),
    ])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(700, 500)
    page.show()
    qtbot.waitExposed(page)
    page.hide_clean_chk.setChecked(False)  # keep the clean "Hi!" row visible too
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    short_row = next(r for r in range(page.results_table.rowCount())
                      if page.results_table.item(r, 0).text() == '2')
    long_row = next(r for r in range(page.results_table.rowCount())
                     if page.results_table.item(r, 0).text() == '1')
    assert page.results_table.rowHeight(short_row) < page.results_table.rowHeight(long_row)


def test_number_mismatch_hint_hidden_when_no_mismatch_visible(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])  # PLACEHOLDER_MISMATCH, not NUMBER_MISMATCH
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.number_hint_label.isHidden()


def test_number_mismatch_hint_shown_when_mismatch_visible(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.number_hint_label.isHidden()
    assert '数字不匹配' in page.number_hint_label.text()


def test_number_mismatch_hint_hides_when_filtered_out(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [
        _u('We shipped 42 units.', '我们发货了43个单位。'),
        _u('Found %d results.', '找到了结果。'),
    ])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
    assert not page.number_hint_label.isHidden()

    placeholder_index = next(
        i for i in range(page.type_filter_combo.count())
        if page.type_filter_combo.itemData(i) == 'PLACEHOLDER_MISMATCH')
    page.type_filter_combo.setCurrentIndex(placeholder_index)
    assert page.number_hint_label.isHidden()
