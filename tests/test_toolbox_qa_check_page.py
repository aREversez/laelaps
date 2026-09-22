import os

from conftest import tmx_path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QStyleOptionViewItem

from language_tools.model import TranslationUnit
from language_tools.writers import tmx_writer
from toolbox.paths import RESOURCES_DIR
from toolbox.tools.qa_check.page import QaCheckPage, _CELL_TOP_PADDING, _WRAP_HTML_ROLE


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def _write_tmx(path, units):
    tmx_writer.write(str(path), units, 'en-US', 'zh-CN')


def _show_checked_units(page, units):
    """Populate the page's results table directly from pre-built units
    (each already carrying whatever ``meta['qa_issues']`` the test wants)
    instead of round-tripping through a real tmx file and qa.run() --
    needed for constructing issue types the tmx writer/reader can't
    round-trip cleanly (e.g. EMPTY_TARGET: an empty <seg> gets dropped by
    the writer, so there's no way to get one back out via a real file).
    """
    page._last_units = units
    page._refresh_table()


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


def test_table_columns_show_src_tgt_and_translated_issue_labels(qtbot):
    # EMPTY_TARGET rather than a highlightable issue type (e.g.
    # PLACEHOLDER_MISMATCH) -- this test is about column content/label
    # translation, which the plain QTableWidgetItem path (below) covers
    # regardless of issue type; a highlightable-issue fixture here would
    # go through the QLabel path instead and item(0, 1) would be None
    # (see the wrap/highlight section's own tests for that path). Built
    # directly rather than via a real tmx file: the tmx writer drops an
    # empty <seg>, so EMPTY_TARGET can't round-trip through a real file.
    unit = _u('Found results.', '')
    unit.meta['qa_issues'] = ['EMPTY_TARGET']
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [unit])

    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 1).text() == 'Found results.'
    assert page.results_table.item(0, 2).text() == ''
    # Chinese label, not the raw code -- a bare "EMPTY_TARGET" means
    # nothing to a non-technical reviewer.
    assert page.results_table.item(0, 3).text() == '译文为空'


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


def test_export_report_before_any_check_is_a_silent_noop(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.export_report_btn.click()
    assert page.log.toPlainText() == ''


def test_export_report_button_disabled_until_check_succeeds(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    assert not page.export_report_btn.isEnabled()
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
    assert page.export_report_btn.isEnabled()


def test_export_report_writes_html_summary(qtbot, tmp_path, monkeypatch):
    out = tmp_path / 'report.html'
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.qa_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), 'HTML (*.html)'))
    page.export_report_btn.click()

    assert '已导出报告到' in page.log.toPlainText()
    content = out.read_text(encoding='utf-8')
    assert '<title>QA Report</title>' in content


def test_export_report_cancelled_dialog_does_not_error(qtbot, monkeypatch):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.qa_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: ('', ''))
    page.export_report_btn.click()
    assert '出错了' not in page.log.toPlainText()


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
    item = page.results_table.item(0, 1)
    assert item is not None
    assert page.results_table.cellWidget(0, 1) is None
    assert item.text() == 'Found %d results.'
    assert '<b' in item.data(_WRAP_HTML_ROLE)


def test_toggling_wrap_off_again_restores_plain_items_for_clean_row(qtbot):
    unit = _u('Found results.', '')
    unit.meta['qa_issues'] = ['EMPTY_TARGET']  # not a highlightable issue type
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [unit])

    page.wrap_chk.setChecked(True)
    page.wrap_chk.setChecked(False)
    assert page.results_table.cellWidget(0, 1) is None
    assert page.results_table.item(0, 1).text() == 'Found results.'


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
        src_item = page.results_table.item(0, 1)
        tgt_item = page.results_table.item(0, 2)
        if wrapped:
            src_html = src_item.data(_WRAP_HTML_ROLE)
            tgt_html = tgt_item.data(_WRAP_HTML_ROLE)
        else:
            src_html = page.results_table.cellWidget(0, 1).text()
            tgt_html = page.results_table.cellWidget(0, 2).text()
        assert '<b style="color:#B23B3B; font-weight:600;">42</b>' in src_html
        assert '<b style="color:#B23B3B; font-weight:600;">43</b>' in tgt_html


def test_wrap_on_does_not_highlight_rows_without_a_highlightable_issue(qtbot):
    unit = _u('Found results.', '')
    unit.meta['qa_issues'] = ['EMPTY_TARGET']  # not a highlightable issue type
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [unit])

    page.wrap_chk.setChecked(True)
    src_html = page.results_table.item(0, 1).data(_WRAP_HTML_ROLE)
    assert '<b' not in src_html


def test_placeholder_mismatch_row_highlights_placeholder_tokens(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])  # target dropped the %d
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.wrap_chk.isChecked()
    src_html = page.results_table.cellWidget(0, 1).text()
    assert '<b style="color:#B23B3B; font-weight:600;">%d</b>' in src_html


def test_url_mismatch_row_highlights_the_url(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('See https://example.com/docs for details.', '详情见文档。')])  # URL dropped
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.wrap_chk.isChecked()
    src_html = page.results_table.cellWidget(0, 1).text()
    assert '<b style="color:#B23B3B; font-weight:600;">https://example.com/docs</b>' in src_html


def test_row_with_both_number_and_placeholder_mismatch_highlights_both(qtbot):
    # A row can carry more than one issue at once (see e.g.
    # test_table_shows_multiple_issue_labels_joined_for_one_row) --
    # spans from every applicable check must all show up, not just the
    # first one found.
    unit = _u('Found %d results, 42 in total.', '找到了结果，总共43个。')
    unit.meta['qa_issues'] = ['NUMBER_MISMATCH', 'PLACEHOLDER_MISMATCH']
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [unit])

    src_html = page.results_table.cellWidget(0, 1).text()
    assert '<b style="color:#B23B3B; font-weight:600;">%d</b>' in src_html
    assert '<b style="color:#B23B3B; font-weight:600;">42</b>' in src_html


def test_short_row_matches_non_wrap_row_height_exactly(qtbot, tmp_path):
    # Regression guard: every row used to grow to some uniform, overly
    # tall height in wrap mode regardless of actual content -- a
    # three-character row shouldn't need more height than one line, and
    # specifically should match a plain non-wrap row's height exactly
    # (not just "less than a long row's height", which a smaller-but-
    # still-inflated height would also satisfy). Needs a real, shown
    # window: column width (and therefore whether the long sentence
    # actually needs to wrap at all) is meaningless on an un-shown
    # widget's default/fallback geometry.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [
        _u(
            'We shipped 42 units to the warehouse last quarter, well above '
            'the 43 units originally forecast for the same period, and '
            'expect volumes to keep rising through year end.',
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
    non_wrap_height = page.results_table.rowHeight(0)

    page.wrap_chk.setChecked(True)
    qtbot.wait(200)  # let the delegate reflow debounce run
    short_row = next(r for r in range(page.results_table.rowCount())
                      if page.results_table.item(r, 0).text() == '2')
    long_row = next(r for r in range(page.results_table.rowCount())
                     if page.results_table.item(r, 0).text() == '1')
    assert page.results_table.rowHeight(short_row) == non_wrap_height
    assert page.results_table.rowHeight(long_row) > non_wrap_height


def test_short_row_matches_non_wrap_row_height_with_real_stylesheet(qtbot, tmp_path):
    # Regression guard for a bug that this test file's other row-height
    # tests did NOT catch: this app's real font (Microsoft YaHei UI, from
    # style.qss) has a taller natural single-line height than whatever
    # fallback font this test environment substitutes when no stylesheet
    # is loaded, so a one-line row could come out taller in wrap mode
    # than in the default view on the real font while every other test
    # here -- never loading the real stylesheet -- still passed. Loading
    # the actual app stylesheet to reproduce it is the only way for this
    # suite to have caught it. Real reset in a try/finally: QApplication
    # is a session-wide singleton (pytest-qt's own qapp fixture), so a
    # stylesheet set here would otherwise leak into every later test.
    app = QApplication.instance()
    style_path = os.path.join(RESOURCES_DIR, 'style.qss')
    with open(style_path, encoding='utf-8') as f:
        stylesheet = f.read()
    original_stylesheet = app.styleSheet()
    app.setStyleSheet(stylesheet)
    try:
        src = tmp_path / 'in.tmx'
        # Long enough that it's a real sentence, not a trivial "Hi!" --
        # the bug this guards against needed real single-line content,
        # not just a near-empty one, to actually manifest.
        _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
        page = QaCheckPage()
        qtbot.addWidget(page)
        page.resize(1400, 500)  # wide enough the content stays on one line
        page.show()
        qtbot.waitExposed(page)
        page.input_edit.setText(str(src))
        page.check_btn.click()
        qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
        non_wrap_height = page.results_table.rowHeight(0)

        page.wrap_chk.setChecked(True)
        qtbot.wait(200)  # let the delegate reflow debounce run
        assert page.results_table.rowHeight(0) == non_wrap_height
    finally:
        app.setStyleSheet(original_stylesheet)


def test_wrap_row_height_is_never_less_than_the_content_actually_needs(qtbot, tmp_path):
    # Regression guard for a specific, previously-real bug: setting an
    # early row's wrapped height can itself make the vertical scrollbar
    # newly appear (total content now taller than the viewport), which
    # narrows the Stretch-resized columns -- so a height computed
    # against that row's width *before* the scrollbar appeared could
    # already be stale/too-short by the time later rows (and therefore
    # the scrollbar) exist, clipping that row's last line. This exact
    # geometry (one long multi-line row, one short row, this window
    # size) was confirmed empirically to flip the scrollbar on right as
    # the first row's height grows -- columnWidth(1) measured 262 while
    # sizing row 0, then settled at 255 once row 1 existed too.
    long_src = (
        'We shipped 42 units to the warehouse last quarter, well above '
        'the 43 units originally forecast for the same period, and '
        'expect volumes to keep rising through year end.')
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u(long_src, '我们发货了43个单位。'), _u('Hi!', '你好！')])
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
    qtbot.wait(200)  # let the delegate reflow debounce run
    for row in range(page.results_table.rowCount()):
        item = page.results_table.item(row, 1)
        option = QStyleOptionViewItem()
        option.rect.setWidth(page.results_table.columnWidth(1))
        index = page.results_table.model().index(row, 1)
        needed = page.results_table.itemDelegate().sizeHint(option, index).height()
        assert page.results_table.rowHeight(row) >= needed, (
            f'row {row}: height={page.results_table.rowHeight(row)} '
            f'but content needs {needed}')


def test_sizeHint_accounts_for_the_same_vertical_offset_paint_uses(qtbot, tmp_path):
    # Regression guard for a specific, previously-real bug that the test
    # above can NOT catch: rowHeight() is set FROM sizeHint()'s own
    # return value, so comparing one against the other is tautological --
    # it stays true even if sizeHint() itself is wrong. paint() draws
    # this cell's content starting _CELL_TOP_PADDING px down from the
    # cell's top; sizeHint() has to add that same offset to the raw
    # document height it measures, or a row sized to exactly the
    # document's own height has no room for the offset paint() pushes
    # it down by, clipping the bottom _CELL_TOP_PADDING px of the last
    # line. This checks sizeHint()'s output against the raw document
    # measurement directly, independent of sizeHint() itself, which is
    # what actually would have caught it.
    long_src = (
        'We shipped 42 units to the warehouse last quarter, well above '
        'the 43 units originally forecast for the same period, and '
        'expect volumes to keep rising through year end.')
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u(long_src, '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(500, 500)
    page.show()
    qtbot.waitExposed(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    qtbot.wait(200)

    delegate = page.results_table.itemDelegate()
    index = page.results_table.model().index(0, 1)
    column_width = page.results_table.columnWidth(1)
    raw_document_height = delegate._document(index, column_width).size().height()
    # This content, at this width, must genuinely need more than one
    # line -- otherwise the floor alone would mask the bug this test is
    # for, and the assertion below would pass for the wrong reason.
    assert raw_document_height > 20, 'fixture no longer wraps to multiple lines at this width'

    option = QStyleOptionViewItem()
    option.rect.setWidth(column_width)
    reported = delegate.sizeHint(option, index).height()
    assert reported >= raw_document_height + _CELL_TOP_PADDING


def test_wrap_row_height_updates_when_window_is_resized(qtbot, tmp_path):
    # A window narrower than before means the Stretch-resized 原文/译文
    # columns get narrower too, so a row that fit on one line at the old
    # width may need to wrap onto more lines at the new one -- the row's
    # height must grow to match, or the extra lines get visually clipped.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [
        _u(
            'We shipped 42 units to the warehouse last quarter, well above '
            'the 43 units originally forecast for the same period, and '
            'expect volumes to keep rising through year end.',
            '我们发货了43个单位。'),
    ])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(700, 500)
    page.show()
    qtbot.waitExposed(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    wide_height = page.results_table.rowHeight(0)

    page.resize(420, 500)
    qtbot.wait(300)  # let the page debounce AND the delegate reflow debounce both run

    narrow_height = page.results_table.rowHeight(0)
    assert narrow_height > wide_height


def test_wrap_row_height_shrinks_back_down_when_window_is_widened_again(qtbot, tmp_path):
    # The row height must track the column width in both directions --
    # not just grow when the window narrows, but shrink back down once
    # it's widened again and fewer lines are needed. A widget-based
    # approach tried earlier could only ever grow a row (each cell
    # widget only knew how to ask for more room, never to give it back),
    # leaving rows stuck too tall after a widen; the delegate approach
    # recomputes fresh from the real current width every time, so it has
    # no "too tall" state to get stuck in.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [
        _u(
            'We shipped 42 units to the warehouse last quarter, well above '
            'the 43 units originally forecast for the same period, and '
            'expect volumes to keep rising through year end as demand from '
            'overseas distributors continues to climb.',
            '我们发货了43个单位。'),
    ])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(1100, 500)
    page.show()
    qtbot.waitExposed(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.wrap_chk.setChecked(True)
    qtbot.wait(300)
    wide_height = page.results_table.rowHeight(0)

    page.resize(420, 500)
    qtbot.wait(300)
    narrow_height = page.results_table.rowHeight(0)
    assert narrow_height > wide_height

    page.resize(1100, 500)
    qtbot.wait(300)
    wide_again_height = page.results_table.rowHeight(0)
    assert wide_again_height == wide_height
    assert wide_again_height < narrow_height


def test_non_wrap_highlighted_row_re_elides_when_window_is_widened(qtbot, tmp_path):
    # A NUMBER_MISMATCH row in the non-wrap view elides at whatever
    # column width it was built with; if the window (and therefore the
    # column) later gets wider, the visible "…"-truncated text should
    # grow to use the extra room, not stay stuck at the old, narrower
    # truncation point.
    long_src = (
        'We shipped 42 units to the warehouse last quarter, well above '
        'the 43 units originally forecast for the same period, and '
        'expect volumes to keep rising through year end.')
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u(long_src, '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(420, 500)
    page.show()
    qtbot.waitExposed(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.wrap_chk.isChecked()
    narrow_html = page.results_table.cellWidget(0, 1).text()
    assert '…' in narrow_html

    page.resize(1100, 500)
    qtbot.wait(300)  # let the page debounce AND the delegate reflow debounce both run

    wide_html = page.results_table.cellWidget(0, 1).text()
    # Re-elided against the new, wider column -- strictly more of the
    # sentence is now visible than at the narrow width (whether or not
    # this particular window width is wide enough to fit the whole
    # thing with zero truncation is a font-metrics detail, not what this
    # regression test is about).
    assert wide_html != narrow_html
    assert len(wide_html) > len(narrow_html)


def test_highlight_hint_hidden_when_nothing_highlightable_visible(qtbot):
    unit = _u('Found results.', '')
    unit.meta['qa_issues'] = ['EMPTY_TARGET']  # not a highlightable issue type
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [unit])

    assert page.highlight_hint_label.isHidden()


def test_highlight_hint_shown_when_number_mismatch_visible(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.highlight_hint_label.isHidden()
    assert '数字不匹配' in page.highlight_hint_label.text()


def test_highlight_hint_shown_when_placeholder_or_url_mismatch_visible(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Found %d results.', '找到了结果。')])
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.highlight_hint_label.isHidden()


def test_highlight_hint_hides_when_filtered_to_a_non_highlightable_type(qtbot):
    number_mismatch_unit = _u('We shipped 42 units.', '我们发货了43个单位。')
    number_mismatch_unit.meta['qa_issues'] = ['NUMBER_MISMATCH']
    empty_target_unit = _u('Found results.', '')
    empty_target_unit.meta['qa_issues'] = ['EMPTY_TARGET']
    page = QaCheckPage()
    qtbot.addWidget(page)
    _show_checked_units(page, [number_mismatch_unit, empty_target_unit])
    assert not page.highlight_hint_label.isHidden()

    empty_target_index = next(
        i for i in range(page.type_filter_combo.count())
        if page.type_filter_combo.itemData(i) == 'EMPTY_TARGET')
    page.type_filter_combo.setCurrentIndex(empty_target_index)
    assert page.highlight_hint_label.isHidden()


# ------------------------------------------------------------- debug logging

def test_debug_logging_is_silent_by_default(qtbot, tmp_path, capsys, monkeypatch):
    # QA_CHECK_DEBUG defaults to unset -- normal operation (including the
    # rest of this test suite) must produce no diagnostic output.
    monkeypatch.delenv('QA_CHECK_DEBUG', raising=False)
    import importlib
    from toolbox.tools.qa_check import page as page_module
    importlib.reload(page_module)

    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
    page = page_module.QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
    page.wrap_chk.setChecked(True)
    qtbot.wait(200)

    assert '[qa_check debug]' not in capsys.readouterr().err


def test_debug_logging_traces_the_resize_reflow_chain_when_enabled(qtbot, tmp_path, capsys, monkeypatch):
    # QA_CHECK_DEBUG=1 is the diagnostic the user can turn on (from a
    # terminal, so stderr is visible) to capture what's actually
    # happening on their own machine when the wrap/resize row-height
    # mechanism is suspected of misbehaving -- this is read once at
    # import time, so the module needs reloading after the env var
    # changes for a test to see it take effect.
    monkeypatch.setenv('QA_CHECK_DEBUG', '1')
    import importlib
    from toolbox.tools.qa_check import page as page_module
    importlib.reload(page_module)
    try:
        src = tmp_path / 'in.tmx'
        _write_tmx(src, [_u('We shipped 42 units.', '我们发货了43个单位。')])
        page = page_module.QaCheckPage()
        qtbot.addWidget(page)
        page.input_edit.setText(str(src))
        page.check_btn.click()
        qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
        page.wrap_chk.setChecked(True)
        qtbot.wait(200)

        err = capsys.readouterr().err
        assert '_refresh_table: called' in err
        assert '_reflow_wrapped_rows: starting' in err
        assert '_reflow_wrapped_rows: pass 0' in err
    finally:
        monkeypatch.delenv('QA_CHECK_DEBUG', raising=False)
        importlib.reload(page_module)



def test_wrapped_plain_text_honors_the_option_palette_text_color(qtbot, tmp_path):
    # Regression guard for a specific, previously-real bug: a wrap-mode
    # cell with no highlight spans (e.g. a TAG_MISMATCH row -- TAG_MISMATCH
    # has no span finder, see _SPAN_FINDERS) has nothing but plain,
    # unstyled text in its HTML, and document.drawContents(painter) alone
    # ignored option.palette entirely, always painting in black regardless
    # of what color the table actually uses -- confirmed empirically (see
    # the kill-test this regression guard is built to catch): black,
    # every time, independent of the option passed in. On at least one
    # real machine that made text pale/unreadable against the
    # alternating-row background on some rows. Comparing the rendered
    # output against the app's own subtle dark gray was tried first and
    # discarded: anti-aliasing at normal font sizes means barely any
    # pixel is an exact match for either the right color or the wrong
    # one, so an exact-equality check on "the darkest pixel" passed
    # whether or not the fix was present. Injecting a deliberately
    # extreme, unmistakable palette color (pure green) and checking it
    # actually got used sidesteps that: anti-aliased or not, a genuinely
    # green-tinted pixel cannot be confused with the app's grayscale text,
    # so this discriminates reliably regardless of font rendering
    # specifics.
    unit = _u('Please save your work.', '请保存你的工作。')
    unit.meta['qa_issues'] = ['TAG_MISMATCH']  # not in _SPAN_FINDERS -- no highlight spans
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.resize(700, 500)
    page.show()
    qtbot.waitExposed(page)
    _show_checked_units(page, [unit])
    page.wrap_chk.setChecked(True)
    qtbot.wait(200)

    delegate = page.results_table.itemDelegate()
    index = page.results_table.model().index(0, 1)
    option = QStyleOptionViewItem()
    option.rect.setWidth(page.results_table.columnWidth(1))
    option.rect.setHeight(page.results_table.rowHeight(0))
    option.widget = page.results_table.viewport()
    palette = QPalette(option.palette)
    palette.setColor(QPalette.Text, QColor('#00ff00'))
    option.palette = palette

    pixmap = QPixmap(option.rect.width(), option.rect.height())
    pixmap.fill(QColor('white'))
    painter = QPainter(pixmap)
    delegate.paint(painter, option, index)
    painter.end()

    image = pixmap.toImage()
    # A genuinely green-tinted dark pixel: green channel clearly dominant
    # over red/blue, however anti-aliased -- not just "not white".
    found_green_text = any(
        image.pixelColor(x, y).green() > image.pixelColor(x, y).red() + 40
        and image.pixelColor(x, y).green() > image.pixelColor(x, y).blue() + 40
        for y in range(image.height()) for x in range(image.width()))
    assert found_green_text, 'expected option.palette\'s Text color to be used for unstyled text'


# ------------------------------------------------------------- settings

def test_restore_settings_defaults_when_nothing_saved_yet(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.restore_settings()
    assert page.hide_clean_chk.isChecked() is True
    assert page.wrap_chk.isChecked() is False
    assert page._last_dir == ''


def test_save_then_restore_settings_round_trips(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.hide_clean_chk.setChecked(False)
    page.wrap_chk.setChecked(True)
    page._last_dir = '/some/folder'
    page.save_settings()

    fresh = QaCheckPage()
    qtbot.addWidget(fresh)
    fresh.restore_settings()
    assert fresh.hide_clean_chk.isChecked() is False
    assert fresh.wrap_chk.isChecked() is True
    assert fresh._last_dir == '/some/folder'


def test_cleanup_waits_for_running_check_instead_of_crashing(qtbot):
    """Regression test: closing the window while a check is still running
    used to destroy a live QThread (see ``QaCheckPage.cleanup()``).
    Calling ``cleanup()`` right after ``check_btn.click()``, with no wait
    in between, reproduces that race deliberately instead of relying on
    timing luck.
    """
    page = QaCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(tmx_path('inline_markup_qa.tmx'))
    page.check_btn.click()
    page.cleanup()  # simulates closeEvent() landing mid-check
    qtbot.wait(50)  # cleanup() only waits for the thread; let its queued
                     # finished_ok signal actually reach its slot too

    assert page._check_worker.isFinished()
    assert '检查完成' in page.log.toPlainText()
