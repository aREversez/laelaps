"""DESIGN.md 15.4 P3: result tables split a "待核实" (warning, amber) hit
from a genuine "缺陷" (danger, red) one, so a reviewer can tell at a glance
which rows must change vs which just need a look.
"""
from types import SimpleNamespace

from toolbox.widgets import DANGER_COLOR, WARNING_COLOR


def _cell_color(item):
    assert item is not None, 'expected a cell item to inspect'
    return item.foreground().color().name()  # lowercase '#rrggbb'


# ------------------------------------------------------- term_management

def _term_page_with_units(qtbot, hits):
    from toolbox.tools.term_management.page import TermManagementPage
    page = TermManagementPage()
    qtbot.addWidget(page)
    page._last_units = [SimpleNamespace(src_text='cloud', tgt_text='云',
                                        meta={'term_issues': hits})]
    page._refresh_check_table()
    return page


def test_term_forbidden_hit_uses_danger(qtbot):
    page = _term_page_with_units(qtbot, [
        {'src_term': 'cloud', 'tgt_term': '云', 'status': 'forbidden'}])
    assert _cell_color(page.check_table.item(0, 3)) == DANGER_COLOR.lower()


def test_term_approved_hit_uses_warning(qtbot):
    page = _term_page_with_units(qtbot, [
        {'src_term': 'cloud', 'tgt_term': '云', 'status': 'approved'}])
    assert _cell_color(page.check_table.item(0, 3)) == WARNING_COLOR.lower()


def test_term_mixed_hit_defect_wins(qtbot):
    page = _term_page_with_units(qtbot, [
        {'src_term': 'a', 'tgt_term': 'x', 'status': 'approved'},
        {'src_term': 'b', 'tgt_term': 'y', 'status': 'forbidden'}])
    assert _cell_color(page.check_table.item(0, 3)) == DANGER_COLOR.lower()


# ------------------------------------------------------------- qa_check

def _qa_page_with_units(qtbot, issue_codes):
    from toolbox.tools.qa_check.page import QaCheckPage
    page = QaCheckPage()
    qtbot.addWidget(page)
    page._last_units = [SimpleNamespace(
        src_text='Hello 1', tgt_text='你好 2',
        meta={'qa_issues': issue_codes, 'qa_confidence': 0.75})]
    page._refresh_table()
    return page


def test_qa_hard_mismatch_issue_type_uses_danger(qtbot):
    page = _qa_page_with_units(qtbot, ['NUMBER_MISMATCH'])
    assert _cell_color(page.results_table.item(0, 3)) == DANGER_COLOR.lower()


def test_qa_suspicious_issue_type_uses_warning(qtbot):
    page = _qa_page_with_units(qtbot, ['LENGTH_RATIO_OUTLIER'])
    assert _cell_color(page.results_table.item(0, 3)) == WARNING_COLOR.lower()


def test_qa_mixed_issue_type_defect_wins(qtbot):
    page = _qa_page_with_units(qtbot, ['SOURCE_CONFLICT', 'URL_MISMATCH'])
    assert _cell_color(page.results_table.item(0, 3)) == DANGER_COLOR.lower()
