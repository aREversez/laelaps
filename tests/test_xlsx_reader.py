from language_tools import api
from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import xlsx_bilingual

from conftest import xlsx_path


def test_basic_xlsx_with_header():
    pairs = xlsx_bilingual.read(xlsx_path('basic.xlsx'))
    assert len(pairs) == 3
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert pairs[0].tgt_text == '史密斯博士上午9点到达。'


def test_xlsx_no_header_3col_and_missing_target_warns(capsys):
    pairs = xlsx_bilingual.read(xlsx_path('no_header_3col.xlsx'))
    assert len(pairs) == 2
    assert 'dropped' in capsys.readouterr().out


def test_xlsx_language_direction_reversal():
    # source column is Chinese, target column is English -- must segment
    # each side with the correct splitter, not by column position.
    pairs = xlsx_bilingual.read(xlsx_path('reversed_direction.xlsx'))
    assert len(pairs) == 1
    units, _ = align_paragraph_pairs(pairs, 'zh-CN', 'en-US')
    assert len(units) == 2
    assert units[0].src_text == '他下午三点离开时正在下雨；'
    assert units[0].tgt_text == 'He left at 3pm while it was raining.'
    assert units[1].src_text == '出租车迟到了。'
    assert units[1].tgt_text == 'The taxi was late.'


def test_convert_end_to_end_xlsx(tmp_path):
    out_base = str(tmp_path / 'out')
    result = api.convert(xlsx_path('basic.xlsx'), out_base, src_lang='en-US', tgt_lang='zh-CN')
    assert result['units'] == 3
    assert result['written']['sdltm'] == 3
