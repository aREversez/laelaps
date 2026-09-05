import pytest

from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import docx, docx_alternating

from conftest import fixture_path


def test_alternating_basic():
    pairs = docx_alternating.read(fixture_path('alternating.docx'))
    assert len(pairs) == 2
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert pairs[0].tgt_text == '史密斯博士上午9点到达。'
    assert pairs[1].src_text == 'The train departs at 6 p.m. daily.'
    assert pairs[1].tgt_text == '火车每天下午6点出发。'


def test_alternating_rejects_odd_paragraph_count():
    with pytest.raises(ValueError):
        docx_alternating.read(fixture_path('odd_paragraph_count.docx'))


def test_alternating_language_direction_reversal():
    pairs = docx_alternating.read(fixture_path('alternating_reversed.docx'))
    assert len(pairs) == 1
    units, _ = align_paragraph_pairs(pairs, 'zh-CN', 'en-US')
    assert len(units) == 2
    assert units[0].tgt_text == 'He left at 3pm while it was raining.'
    assert units[1].tgt_text == 'The taxi was late.'


def test_auto_detect_tries_table_then_numbered_before_alternating():
    # basic.docx matches the numbered layout; must NOT fall through to
    # alternating (which would also technically match its paragraph count).
    pairs = docx.read(fixture_path('basic.docx'))
    assert len(pairs) == 3
    assert pairs[0].src_text.startswith('Dr. Smith arrived')


def test_auto_detect_falls_back_to_alternating_as_last_resort():
    pairs = docx.read(fixture_path('alternating.docx'))
    assert len(pairs) == 2
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'


def test_explicit_alternating_layout_override():
    pairs = docx.read(fixture_path('alternating.docx'), layout='alternating')
    assert len(pairs) == 2
