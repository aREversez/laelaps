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
