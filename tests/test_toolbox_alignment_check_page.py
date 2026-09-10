from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel

from language_tools.model import TranslationUnit
from toolbox.tools.alignment_check.page import AlignmentCheckPage

_DOCX = 'tests/fixtures/docx/basic.docx'


def _u(src, tgt, source_key='1', align_move='1:1', align_gap=False,
       alignment_cost=0.0, qa_issues=None, qa_confidence=1.0):
    return TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, source_key=source_key,
        meta={
            'align_move': align_move, 'align_gap': align_gap, 'alignment_cost': alignment_cost,
            'qa_issues': qa_issues or [], 'qa_confidence': qa_confidence,
        })


def _fake_run(units):
    """Returns a stand-in for align_report.run() that ignores its
    arguments and always returns the given units -- used to test filter/
    table/export behavior against controlled fixtures, since coaxing the
    real DP aligner into producing every move type (GAP especially) on
    demand isn't practical (see tests/test_align_report.py for that --
    it tests the aligner itself, this file tests the page).
    """
    return lambda *a, **k: units


# ------------------------------------------------------------- validation

def test_empty_input_shows_validation_error(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.check_btn.click()
    assert '请先选择要检查的文件' in page.log.toPlainText()


def test_missing_file_shows_validation_error(qtbot, tmp_path):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(tmp_path / 'nope.docx'))
    page.check_btn.click()
    assert '找不到这个文件' in page.log.toPlainText()


def test_missing_language_shows_validation_error(qtbot, tmp_path):
    src = tmp_path / 'in.docx'
    src.write_text('placeholder')  # existence is enough, validation fails before reading it
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.src_edit.setEditText('')
    page.check_btn.click()
    assert '请先填写原文语言和译文语言' in page.log.toPlainText()


def test_export_before_any_check_is_a_silent_noop(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page._start_export()
    assert page.log.toPlainText() == ''


# ---------------------------------------------------------------- checking

def test_export_button_disabled_until_check_succeeds(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    assert not page.export_btn.isEnabled()


def test_check_end_to_end_with_real_docx_fixture(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert '检查完成' in page.log.toPlainText()
    assert '共 4 条' in page.summary_label.text()
    assert page.export_btn.isEnabled()


def test_default_view_shows_all_rows_including_clean_ones(qtbot, monkeypatch):
    # Unlike qa_check (hide-clean checked by default -- "find the needles
    # in a big corpus"), this tool's default job is "let me see how my
    # one document got aligned", so a clean result should be visibly
    # confirmed, not hidden behind an empty table.
    units = [
        _u('A', 'a'),  # clean
        _u('B', '', align_move='1:0', align_gap=True),  # gap
        _u('C', 'c', qa_issues=['NUMBER_MISMATCH']),  # qa-flagged
    ]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert not page.hide_clean_chk.isChecked()
    assert page.results_table.rowCount() == 3


def test_checking_hide_clean_hides_clean_rows(qtbot, monkeypatch):
    units = [_u('A', 'a'), _u('B', '', align_move='1:0', align_gap=True)]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.hide_clean_chk.setChecked(True)
    assert page.results_table.rowCount() == 1


def test_clean_result_logs_an_explicit_confirmation(qtbot, monkeypatch):
    # Regression guard for the actual bug report: a well-aligned document
    # produced a blank-looking table with no visible explanation. Even
    # with the default now showing all rows, a loud confirmation in the
    # log matters too -- e.g. if the person also checks 只显示有问题的条目.
    units = [_u('A', 'a'), _u('B', 'b')]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert '全部对齐正常，没有发现问题' in page.log.toPlainText()


def test_move_filter_narrows_to_matching_rows(qtbot, monkeypatch):
    units = [
        _u('A', 'a'), _u('B', 'b'),
        _u('C. D.', 'cd', align_move='2:1'),
    ]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    page.hide_clean_chk.setChecked(False)  # show everything first
    merge_index = next(
        i for i in range(page.move_filter_combo.count())
        if page.move_filter_combo.itemData(i) == '2:1')
    page.move_filter_combo.setCurrentIndex(merge_index)
    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 3).text() == '合并（2→1）'


def test_move_filter_only_lists_moves_that_actually_occurred(qtbot, monkeypatch):
    units = [_u('A', 'a'), _u('B', 'b')]  # both 1:1, nothing else
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    codes = [page.move_filter_combo.itemData(i) for i in range(page.move_filter_combo.count())]
    assert codes == [None, '1:1']  # "全部" plus only the move that occurred


def test_gap_and_qa_columns_render_correctly(qtbot, monkeypatch):
    units = [_u('Found %d results.', '找到了结果。', qa_issues=['PLACEHOLDER_MISMATCH'])]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    assert page.results_table.item(0, 1).text() == 'Found %d results.'
    assert page.results_table.item(0, 2).text() == '找到了结果。'
    assert page.results_table.item(0, 5).text() == '占位符不匹配'


def test_check_again_clears_stale_results_first(qtbot, monkeypatch, tmp_path):
    units = [_u('A', '', align_move='1:0', align_gap=True)]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)
    assert page.results_table.rowCount() > 0

    page.input_edit.setText(str(tmp_path / 'missing.docx'))
    page.check_btn.click()
    assert page.results_table.rowCount() == 0
    assert page.summary_label.text() == ''
    assert page.move_filter_combo.count() == 1  # back to just "全部对齐方式"


# ------------------------------------------------------------------- export

def test_export_writes_full_csv_including_clean_rows(qtbot, monkeypatch, tmp_path):
    units = [_u('A', 'a'), _u('B', '', align_move='1:0', align_gap=True)]
    monkeypatch.setattr('toolbox.tools.alignment_check.page.align_report.run', _fake_run(units))
    out = tmp_path / 'report.csv'
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.alignment_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()
    qtbot.waitUntil(lambda: page.export_btn.isEnabled(), timeout=5000)

    assert '已导出到' in page.log.toPlainText()
    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert content.count('\n') >= 3  # header + 2 data rows -- both, not just the gap one
    assert 'align_move' in content


def test_export_cancelled_dialog_does_not_error(qtbot, monkeypatch):
    monkeypatch.setattr(
        'toolbox.tools.alignment_check.page.align_report.run', _fake_run([_u('A', 'a')]))
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.input_edit.setText(_DOCX)
    page.check_btn.click()
    qtbot.waitUntil(lambda: page.check_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.alignment_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: ('', ''))
    page.export_btn.click()
    assert '出错了' not in page.log.toPlainText()
    assert '导出失败' not in page.log.toPlainText()


# ------------------------------------------------------------------- layout

def test_results_section_title_is_对齐结果_exactly_once(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    titles = [label.text() for label in page.findChildren(QLabel)
              if label.property('role') == 'sectionTitle']
    assert titles.count('对齐结果') == 1
    # 筛选 was folded into 对齐结果 (see the module docstring) rather than
    # staying a section of its own -- it should no longer appear at all.
    assert '筛选' not in titles


def test_filter_controls_and_table_live_under_the_same_对齐结果_section(qtbot):
    # 只显示有问题的条目 and the move-type dropdown only ever filter this
    # table, so they should be reachable from the same section() wrapper
    # as results_table -- not split into a separate 筛选 section above it.
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    title_label = next(
        label for label in page.findChildren(QLabel)
        if label.property('role') == 'sectionTitle' and label.text() == '对齐结果')
    section_wrapper = title_label.parentWidget()
    assert page.results_table in section_wrapper.findChildren(type(page.results_table))
    assert page.hide_clean_chk in section_wrapper.findChildren(type(page.hide_clean_chk))
    assert page.move_filter_combo in section_wrapper.findChildren(type(page.move_filter_combo))


def test_results_table_header_is_left_aligned(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    alignment = page.results_table.horizontalHeader().defaultAlignment()
    assert alignment & Qt.AlignLeft


# ------------------------------------------------------- compact input row
# Regression coverage for the actual bug report: on a non-maximized window
# the three stacked input sections (file/language/docx layout) left almost
# no room for 对齐结果, which could show only one or two rows no matter how
# many the check actually found. A first attempt fixed this by moving the
# inputs into a QSplitter + QScrollArea -- rejected on review because it
# hid 开始检查 behind a scroll instead of fixing the actual wasted space.
# The real fix: 原文语言/译文语言/文档排版方式 were each a whole row wide
# despite showing short text (QFormLayout's default field-growth policy
# stretches the field regardless of the widget's own size hint) -- giving
# each combo AdjustToContents sizing and laying all three out in one row
# collapses two sections into one without hiding or scrolling anything.
# Section titles also dropped their "第一步"/"第二步" numbering -- a fixed
# sequence of inputs reads as steps on its own, the numbers were just more
# label text without adding clarity.

def test_no_scroll_area_or_splitter_hides_any_controls(qtbot):
    # The whole point of rejecting the splitter/scroll-area design: every
    # control, including 开始检查, must be reachable without scrolling or
    # dragging a divider.
    from PySide6.QtWidgets import QScrollArea, QSplitter
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    assert page.findChildren(QScrollArea) == []
    assert page.findChildren(QSplitter) == []


def test_language_and_layout_combos_size_to_their_own_content(qtbot):
    # AdjustToContents is what stops these combos from stretching to the
    # full row width for text as short as "英语 (en-US)".
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    for combo in (page.src_edit, page.tgt_edit, page.layout_combo):
        assert combo.sizeAdjustPolicy() == QComboBox.AdjustToContents


def test_language_and_layout_controls_share_a_single_row(qtbot):
    # These three used to be two separate stacked sections (one 2-row
    # QFormLayout for the languages, one more section for the docx
    # layout); they should now be siblings inline in one row, i.e. share
    # the same immediate parent widget.
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    assert page.src_edit.parentWidget() is page.tgt_edit.parentWidget()
    assert page.src_edit.parentWidget() is page.layout_combo.parentWidget()


def test_no_section_title_uses_step_numbering_language(qtbot):
    # "第一步"/"第二步" style prefixes were dropped from every section
    # title on this page -- see the module docstring for why.
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    titles = [label.text() for label in page.findChildren(QLabel)
              if label.property('role') == 'sectionTitle']
    assert titles, 'expected at least one section title to check'
    for title in titles:
        assert not title.startswith('第') or '步' not in title



def test_check_button_is_a_direct_descendant_not_behind_any_container(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    assert page.check_btn in page.findChildren(type(page.check_btn))
    # Reachable via the page's own layout, not nested inside a widget
    # whose visibility/size depends on a splitter position or a scroll
    # viewport -- walking up from check_btn should hit the page itself
    # within a couple of plain QWidget/QVBoxLayout hops.
    from PySide6.QtWidgets import QScrollArea, QSplitter
    ancestor = page.check_btn.parentWidget()
    depth = 0
    while ancestor is not None and ancestor is not page and depth < 6:
        assert not isinstance(ancestor, (QScrollArea, QSplitter))
        ancestor = ancestor.parentWidget()
        depth += 1
