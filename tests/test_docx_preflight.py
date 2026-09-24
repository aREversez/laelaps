from language_tools.readers import docx_preflight

from conftest import fixture_path


def test_layout_confidence_reports_all_three_readers():
    result = docx_preflight.check(fixture_path('table_layout.docx'))
    assert set(result['layout_confidence']) == {'table', 'numbered', 'alternating'}
    assert result['best_layout'] == 'table'
    assert result['best_score'] >= 0.85
    assert result['layout_ambiguous'] is False
    assert result['issues'] == []


def test_layout_ambiguous_when_best_score_is_low():
    # alternating.docx's confidence() is capped at 0.5 by design (no
    # positive structural signal, just an even paragraph count) -- below
    # the 0.85 "strong signal" tier every reader uses.
    result = docx_preflight.check(fixture_path('alternating.docx'))
    assert result['best_layout'] == 'alternating'
    assert result['layout_ambiguous'] is True
    assert any('置信度偏低' in issue for issue in result['issues'])


def test_merged_cell_flagged():
    result = docx_preflight.check(fixture_path('table_merged_header.docx'))
    assert result['merged_cell_count'] == 1
    assert any('合并单元格' in issue for issue in result['issues'])


def test_no_merged_cells_for_clean_table():
    result = docx_preflight.check(fixture_path('table_layout.docx'))
    assert result['merged_cell_count'] == 0
    assert not any('合并单元格' in issue for issue in result['issues'])


def test_empty_table_flagged():
    result = docx_preflight.check(fixture_path('table_with_empty_table.docx'))
    assert result['empty_table_count'] == 1
    assert any('空表格' in issue for issue in result['issues'])


def test_no_empty_tables_for_clean_doc():
    result = docx_preflight.check(fixture_path('table_layout.docx'))
    assert result['empty_table_count'] == 0


def test_direction_issue_flagged_when_columns_are_swapped():
    # table_layout_reversed.docx's columns are actually zh/en, not en/zh
    # -- see test_docx_table_reader.py's test_table_layout_language_
    # direction_reversal for the same fixture used the same way.
    result = docx_preflight.check(fixture_path('table_layout_reversed.docx'),
                                   src_lang='en-US', tgt_lang='zh-CN')
    assert len(result['direction_issues']) == 2
    assert all(issue in result['issues'] for issue in result['direction_issues'])


def test_no_direction_issue_when_declared_langs_match_content():
    result = docx_preflight.check(fixture_path('table_layout_reversed.docx'),
                                   src_lang='zh-CN', tgt_lang='en-US')
    assert result['direction_issues'] == []


def test_direction_check_skipped_without_declared_langs():
    result = docx_preflight.check(fixture_path('table_layout_reversed.docx'))
    assert result['direction_issues'] == []


def test_direction_check_skipped_with_only_one_lang_and_no_table():
    # basic.docx is numbered-layout, not table-layout -- sample_column_text()
    # has nothing to sample from, so the check is a no-op, not an error.
    result = docx_preflight.check(fixture_path('basic.docx'), src_lang='en-US', tgt_lang='zh-CN')
    assert result['direction_issues'] == []
