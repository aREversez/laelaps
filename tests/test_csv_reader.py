from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import csv_bilingual

from conftest import csv_path


def test_basic_csv_utf8_sig_with_header():
    pairs = csv_bilingual.read(csv_path('basic_utf8sig.csv'))
    assert len(pairs) == 2
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert pairs[0].tgt_text == '史密斯博士上午9点到达。'


def test_gb18030_tsv_sniffed_and_decoded():
    # No header row here, no explicit delimiter -- exercises both the
    # header heuristic (should NOT treat row 0 as header, it's real data)
    # and the utf-8-sig/utf-8/gb18030 fallback chain landing on gb18030.
    pairs = csv_bilingual.read(csv_path('gb18030_tsv.tsv'))
    assert len(pairs) == 2
    assert pairs[0].src_text == 'First item.'
    assert pairs[0].tgt_text == '第一项。'


def test_csv_language_direction_reversal():
    pairs = csv_bilingual.read(csv_path('reversed_direction.csv'))
    assert len(pairs) == 1
    units, _ = align_paragraph_pairs(pairs, 'zh-CN', 'en-US')
    assert len(units) == 2
    assert units[0].tgt_text == 'He left at 3pm while it was raining.'
    assert units[1].tgt_text == 'The taxi was late.'
