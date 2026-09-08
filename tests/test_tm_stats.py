from language_tools.model import TranslationUnit
from language_tools.tm import stats as stats_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_basic_counts():
    units = [_u('A', 'a'), _u('A', 'a'), _u('B', 'b')]
    s = stats_module.compute(units)
    assert s['total'] == 3
    assert s['unique_pairs'] == 2
    assert s['duplicate_pairs'] == 1
    assert s['duplicate_rate'] == 1 / 3


def test_empty_counts():
    units = [_u('', 'x'), _u('y', ''), _u('A', 'a')]
    s = stats_module.compute(units)
    assert s['empty_source'] == 1
    assert s['empty_target'] == 1


def test_lang_pair_distribution_handles_mixed_pairs():
    units = [_u('A', 'a', 'en-US', 'zh-CN'), _u('B', 'b', 'en-US', 'zh-CN'),
             _u('C', 'c', 'en-US', 'ja-JP')]
    s = stats_module.compute(units)
    assert s['lang_pairs'] == {'en-US-zh-CN': 2, 'en-US-ja-JP': 1}


def test_empty_corpus_does_not_divide_by_zero():
    s = stats_module.compute([])
    assert s['total'] == 0
    assert s['duplicate_rate'] == 0.0
    assert s['length_ratio'] == 0.0


def test_length_ratio_uses_char_counts():
    units = [_u('AAAA', 'aa')]  # src 4 chars, tgt 2 chars -> ratio 2.0
    s = stats_module.compute(units)
    assert s['length_ratio'] == 2.0
