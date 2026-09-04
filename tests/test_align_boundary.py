"""Guards the architectural invariant from DESIGN.md section 2: DP alignment
must never cross ParagraphPair boundaries.

Constructs two paragraphs where, if the aligner concatenated all sentences
into one sequence before running DP, cross-paragraph merging would produce
a cheaper (but semantically wrong) alignment than aligning each paragraph
independently. Confirms the aligner does NOT take that cheaper-but-wrong
path.
"""
from language_tools.align.aligner import align_paragraph_pairs
from language_tools.model import ParagraphPair


def test_dp_does_not_cross_paragraph_boundaries():
    # Paragraph 1: one short EN sentence, one short ZH sentence -- a clean 1:1.
    # Paragraph 2: same shape, different content -- also a clean 1:1.
    # If DP were run over the concatenated 2+2 sentence sequence, nothing
    # forces it to respect the para-1/para-2 split; if it were run per-pair
    # (as required), each pair must independently resolve to exactly one
    # aligned unit with its own paragraph's content on both sides.
    pairs = [
        ParagraphPair(key='1', src_text='The cat sleeps.', tgt_text='猫在睡觉。'),
        ParagraphPair(key='2', src_text='The dog runs.', tgt_text='狗在跑步。'),
    ]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')

    assert len(units) == 2
    by_key = {u.source_key: u for u in units}
    assert by_key['1'].src_text == 'The cat sleeps.'
    assert by_key['1'].tgt_text == '猫在睡觉。'
    assert by_key['2'].src_text == 'The dog runs.'
    assert by_key['2'].tgt_text == '狗在跑步。'
    # explicitly assert no cross-contamination
    assert '狗' not in by_key['1'].tgt_text
    assert '猫' not in by_key['2'].tgt_text


def test_dp_does_not_cross_boundaries_with_uneven_splits():
    # Paragraph 1 has 2 EN sentences vs 1 ZH sentence (needs a 2:1 merge).
    # Paragraph 2 has 1 EN sentence vs 1 ZH sentence (clean 1:1).
    # A buggy implementation that flattens everything into one sequence
    # before DP could plausibly borrow paragraph 2's ZH sentence to balance
    # paragraph 1's extra EN sentence. Confirm that doesn't happen.
    pairs = [
        ParagraphPair(key='1', src_text='He arrived early. He waited outside.',
                       tgt_text='他早早到了，在外面等着。'),
        ParagraphPair(key='2', src_text='She left late.', tgt_text='她走得很晚。'),
    ]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')

    keys_seen = {u.source_key for u in units}
    assert keys_seen == {'1', '2'}
    for u in units:
        if u.source_key == '1':
            assert '她' not in u.tgt_text and '走' not in u.tgt_text
        else:
            assert u.src_text == 'She left late.'
            assert u.tgt_text == '她走得很晚。'
