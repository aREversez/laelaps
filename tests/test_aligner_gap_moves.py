"""Regression test for the (1,0)/(0,1) gap-move fix in aligner.MATCHES.

See aligner.py's comment block above MATCHES for the full empirical
writeup (what this does and does not fix, verified by reverting and
reproducing before landing the change).
"""
from language_tools.align.aligner import align_paragraph_pairs
from language_tools.model import ParagraphPair


def test_empty_target_side_no_longer_vanishes_silently():
    # Before adding (1,0)/(0,1) to MATCHES, dp[n][0] was unreachable
    # whenever the target side split to zero sentences, and
    # _align_sentences silently returned [] -- the whole pair vanished
    # with no unit and no warning. Confirmed by temporarily reverting
    # MATCHES and reproducing this exact case returning [].
    pairs = [ParagraphPair(key='1', src_text='Just one sentence here.', tgt_text='')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert len(units) == 1
    assert units[0].src_text == 'Just one sentence here.'
    assert units[0].tgt_text == ''


def test_empty_source_side_no_longer_vanishes_silently():
    pairs = [ParagraphPair(key='1', src_text='', tgt_text='这里只有一句话。')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert len(units) == 1
    assert units[0].src_text == ''
    assert units[0].tgt_text == '这里只有一句话。'


def test_alignment_cost_exposed_in_meta():
    pairs = [ParagraphPair(key='1', src_text='The cat sleeps.', tgt_text='猫在睡觉。')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert 'alignment_cost' in units[0].meta
    assert isinstance(units[0].meta['alignment_cost'], float)


def test_align_move_and_gap_flag_for_normal_one_to_one():
    pairs = [ParagraphPair(key='1', src_text='The cat sleeps.', tgt_text='猫在睡觉。')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert units[0].meta['align_move'] == '1:1'
    assert units[0].meta['align_gap'] is False


def test_align_move_for_a_genuine_merge():
    # Two short source sentences merge into one target sentence -- a real
    # (2,1) DP move, not a gap. align_gap must stay False: a merge is a
    # normal alignment outcome, not "no corresponding sentence existed".
    pairs = [ParagraphPair(key='1', src_text='Hi. Bye.', tgt_text='你好，再见。')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert len(units) == 1
    assert units[0].meta['align_move'] == '2:1'
    assert units[0].meta['align_gap'] is False


def test_align_gap_flag_true_for_gap_moves():
    pairs = [ParagraphPair(key='1', src_text='Just one sentence here.', tgt_text='')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert units[0].meta['align_move'] == '1:0'
    assert units[0].meta['align_gap'] is True

    pairs = [ParagraphPair(key='1', src_text='', tgt_text='这里只有一句话。')]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert units[0].meta['align_move'] == '0:1'
    assert units[0].meta['align_gap'] is True


def test_duplicate_paragraph_pair_keys_do_not_corrupt_content():
    # ParagraphPair.key is diagnostic metadata, not required to be unique.
    # An earlier implementation used {p.key: ...} as an intermediate dict,
    # which would silently collapse two pairs sharing a key down to just
    # the last one's content -- confirmed by temporarily reverting to that
    # implementation and reproducing exactly this corruption.
    pairs = [
        ParagraphPair(key='1', src_text='The cat sleeps.', tgt_text='猫在睡觉。'),
        ParagraphPair(key='1', src_text='The dog runs.', tgt_text='狗在跑步。'),
    ]
    units, _ = align_paragraph_pairs(pairs, 'en-US', 'zh-CN')
    assert len(units) == 2
    assert units[0].src_text == 'The cat sleeps.' and units[0].tgt_text == '猫在睡觉。'
    assert units[1].src_text == 'The dog runs.' and units[1].tgt_text == '狗在跑步。'
