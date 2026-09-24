from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import docx, docx_table

from conftest import fixture_path


def test_table_layout_basic():
    pairs = docx_table.read(fixture_path('table_layout.docx'))
    assert len(pairs) == 3
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert pairs[0].tgt_text == '史密斯博士上午9点到达。'


def test_table_layout_language_direction_reversal():
    pairs = docx_table.read(fixture_path('table_layout_reversed.docx'))
    assert len(pairs) == 1
    units, _ = align_paragraph_pairs(pairs, 'zh-CN', 'en-US')
    assert len(units) == 2
    assert units[0].tgt_text == 'He left at 3pm while it was raining.'
    assert units[1].tgt_text == 'The taxi was late.'


def test_table_confidence_high_for_table_layout_doc():
    # table_layout.docx has a 3-row bilingual table -> strong positive
    # signal, should score >= 0.85 (specifically 0.95 with 4+ populated
    # rows, or 0.85 with fewer; either way above numbered/alternating).
    score = docx_table.confidence(fixture_path('table_layout.docx'))
    assert score >= 0.85
    # And it should beat the other readers' confidence on the same doc
    from language_tools.readers import docx_alternating, docx_numbered
    assert score > docx_numbered.confidence(fixture_path('table_layout.docx'))
    assert score > docx_alternating.confidence(fixture_path('table_layout.docx'))


def test_table_confidence_zero_for_non_table_doc():
    # basic.docx is the numbered layout, no qualifying tables -> table
    # confidence should be 0.0 (not "small but non-zero").
    assert docx_table.confidence(fixture_path('basic.docx')) == 0.0


def test_auto_detect_picks_table_layout_when_table_present():
    pairs = docx.read(fixture_path('table_layout.docx'))
    assert len(pairs) == 3


def test_auto_detect_falls_back_to_numbered_layout():
    pairs = docx.read(fixture_path('basic.docx'))
    assert len(pairs) == 3
    # numbered-layout paragraphs, not table cells
    assert pairs[0].src_text.startswith('Dr. Smith arrived')


def test_explicit_layout_override():
    pairs = docx.read(fixture_path('table_layout.docx'), layout='table')
    assert len(pairs) == 3
    import pytest
    with pytest.raises(ValueError):
        docx.read(fixture_path('table_layout.docx'), layout='numbered')


def test_sample_column_text_returns_src_and_tgt_samples():
    src_sample, tgt_sample = docx_table.sample_column_text(fixture_path('table_layout.docx'))
    assert 'Dr. Smith arrived at 9 a.m.' in src_sample
    assert '史密斯博士上午9点到达' in tgt_sample


def test_sample_column_text_empty_when_no_qualifying_table():
    src_sample, tgt_sample = docx_table.sample_column_text(fixture_path('basic.docx'))
    assert (src_sample, tgt_sample) == ('', '')


def test_sample_column_text_caps_at_max_chars():
    src_sample, _ = docx_table.sample_column_text(fixture_path('table_layout.docx'), max_chars=10)
    assert len(src_sample) <= 10


def test_iter_body_tables_with_merge_flags_counts_merged_header_cell():
    from language_tools.readers._ooxml import iter_body_tables_with_merge_flags
    tables = list(iter_body_tables_with_merge_flags(fixture_path('table_merged_header.docx')))
    assert len(tables) == 1
    rows, merged = tables[0]
    assert merged == 1
    assert len(rows) == 5  # merged header row + 4 data rows


def test_iter_body_tables_with_merge_flags_zero_for_clean_table():
    from language_tools.readers._ooxml import iter_body_tables_with_merge_flags
    tables = list(iter_body_tables_with_merge_flags(fixture_path('table_layout.docx')))
    assert all(merged == 0 for _rows, merged in tables)
