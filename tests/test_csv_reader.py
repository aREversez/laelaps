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


def test_csv_multiline_quoted_field_preserved(tmp_path):
    # A quoted field spanning multiple physical lines must keep its embedded
    # newlines. Regression: csv.reader used to be fed text.splitlines(),
    # which strips the line terminators, so multi-line records were silently
    # re-joined WITHOUT the newline ("line1\nline2" -> "line1line2").
    #
    # Generated via tmp_path instead of a committed fixture under
    # fixtures/csv/: the bytes under test ARE the line terminators, and git
    # autocrlf would rewrite them on Windows checkouts, making a committed
    # fixture's expected values platform-dependent.
    p = tmp_path / 'multiline.csv'
    p.write_text('en,zh\n"line1\nline2","第一行\n第二行"\n', encoding='utf-8')
    pairs = csv_bilingual.read(str(p))
    assert len(pairs) == 1
    assert pairs[0].key == '1'
    assert pairs[0].src_text == 'line1\nline2'
    assert pairs[0].tgt_text == '第一行\n第二行'
