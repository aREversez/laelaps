import pytest

from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import docx, docx_alternating, docx_numbered, docx_table

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


def test_alternating_confidence_capped_low_for_any_even_paragraph_doc():
    # The defining fact about alternating: it has no positive signal. Any
    # document with an even, non-zero paragraph count "matches" -- so its
    # confidence is capped at 0.5 (well below table's 0.85+ and numbered's
    # 0.85+ when those layouts genuinely claim a doc). Even alternating.docx
    # itself, which IS a real alternating-layout bilingual doc, only
    # scores 0.5 because the reader has no way to *know* it's bilingual.
    score = docx_alternating.confidence(fixture_path('alternating.docx'))
    assert 0.0 < score <= 0.5


def test_alternating_confidence_zero_for_odd_paragraph_doc():
    # odd_paragraph_count.docx has an odd number of paragraphs -- the
    # alternating reader rejects it on read(), and confidence() should
    # also return 0.0 so auto-detection doesn't pick it over a layout
    # that actually fits.
    assert docx_alternating.confidence(fixture_path('odd_paragraph_count.docx')) == 0.0


def test_numbered_confidence_high_for_two_block_numbered_doc():
    # basic.docx is the classic "[1]..[N] source, [1]..[N] target" shape
    # -> numbered.confidence should be high (>= 0.85).
    score = docx_numbered.confidence(fixture_path('basic.docx'))
    assert score >= 0.85
    # And it should beat the other readers on the same doc
    assert score > docx_alternating.confidence(fixture_path('basic.docx'))


def test_numbered_confidence_zero_for_non_numbered_doc():
    # table_layout.docx has no [N]-tagged paragraphs -> numbered.confidence
    # should be 0.0
    assert docx_numbered.confidence(fixture_path('table_layout.docx')) == 0.0


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


def test_auto_detect_picks_table_when_table_and_numbered_both_score_high():
    # When two layouts both have a strong positive signal (e.g. a doc
    # that contains both a qualifying table AND [1]..[N] numbered
    # paragraphs), auto-detection should still pick one deterministically
    # rather than fail. Currently the tie-break is _AUTO_ORDER order
    # (table first), which matches the historical "try table, then
    # numbered" behavior. This test documents that contract.
    # Use table_layout.docx -- it scores high on table, low on numbered.
    pairs = docx.read(fixture_path('table_layout.docx'))
    assert len(pairs) == 3
    # Sanity: table confidence > numbered confidence on this doc
    assert docx_table.confidence(fixture_path('table_layout.docx')) >= \
           docx_numbered.confidence(fixture_path('table_layout.docx'))


def test_auto_detect_prefers_stronger_numbered_signal_over_a_stray_cover_table():
    # The actual scenario this commit's confidence-scoring exists to fix
    # (per its own commit message): a small, non-bilingual-content table
    # elsewhere in the document (e.g. a 2-row author/status metadata table
    # on a cover page) that nonetheless *looks* like a qualifying bilingual
    # table to docx_table's own detection, sitting alongside a much
    # stronger 4-pair numbered-layout body.
    #
    # Confirmed empirically before adding this fixture: docx_table.read()
    # called alone on this fixture returns 1 (wrong) pair scraped from the
    # cover table ('Status' -> '状态'); under the OLD first-success
    # auto-detect order (table tried first, first non-error result wins),
    # this would have silently won over the real numbered content. This
    # test guards that the confidence-based auto-detect picks numbered
    # instead, since numbered's signal (4-pair two-block numbering) is
    # objectively stronger than table's (1 qualifying row).
    path = fixture_path('stray_cover_table_plus_numbered.docx')
    assert docx_numbered.confidence(path) > docx_table.confidence(path)

    pairs = docx.read(path)
    assert len(pairs) == 4
    assert pairs[0].src_text == 'First sentence here.'
    assert pairs[0].tgt_text == '第一句话。'
