from language_tools.model import TranslationUnit
from language_tools.tm import stats as stats_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN', **kw):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt, **kw)


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


def test_aging_buckets_by_modified_at_year():
    units = [
        _u('A', 'a', modified_at='2023-06-15 10:00:00'),
        _u('B', 'b', modified_at='2023-11-01 09:00:00'),
        _u('C', 'c', modified_at='2025-01-02 12:00:00'),
    ]
    s = stats_module.compute(units)
    assert s['aging'] == {'2023': 2, '2025': 1}


def test_aging_uses_modified_at_not_created_at():
    units = [_u('A', 'a', created_at='2019-01-01 00:00:00', modified_at='2025-05-05 00:00:00')]
    s = stats_module.compute(units)
    assert s['aging'] == {'2025': 1}


def test_aging_unparseable_or_missing_date_goes_to_unknown_bucket():
    units = [_u('A', 'a', modified_at=None), _u('B', 'b', modified_at=''),
             _u('C', 'c', modified_at='not-a-date')]
    s = stats_module.compute(units)
    assert s['aging'] == {'unknown': 3}


def test_aging_tolerates_non_standard_date_formats():
    # Not this project's own sdltm_writer.py format -- a real Trados-
    # native timestamp with a different separator/precision should still
    # yield a year via the leading-4-digits regex, not 'unknown'.
    units = [_u('A', 'a', modified_at='2024/03/10 08:15:30.123')]
    s = stats_module.compute(units)
    assert s['aging'] == {'2024': 1}


def test_lang_pair_by_domain_falls_back_to_source_file_basename():
    units = [
        _u('A', 'a', source_file='/tmp/projects/legal_contract.tmx'),
        _u('B', 'b', source_file='/tmp/projects/legal_contract.tmx'),
        _u('C', 'c', source_file='/tmp/projects/marketing_site.tmx'),
    ]
    s = stats_module.compute(units)
    assert s['lang_pair_by_domain'] == {
        'en-US-zh-CN': {'legal_contract.tmx': 2, 'marketing_site.tmx': 1},
    }


def test_lang_pair_by_domain_prefers_meta_domain_over_source_file():
    u = _u('A', 'a', source_file='/tmp/whatever.tmx')
    u.meta['domain'] = 'legal'
    s = stats_module.compute([u])
    assert s['lang_pair_by_domain'] == {'en-US-zh-CN': {'legal': 1}}


def test_lang_pair_by_domain_unknown_when_neither_available():
    units = [_u('A', 'a')]  # no source_file, no meta['domain']
    s = stats_module.compute(units)
    assert s['lang_pair_by_domain'] == {'en-US-zh-CN': {'unknown': 1}}


def test_lang_pair_by_domain_splits_by_lang_pair_too():
    units = [
        _u('A', 'a', 'en-US', 'zh-CN', source_file='x/acme.tmx'),
        _u('B', 'b', 'en-US', 'ja-JP', source_file='x/acme.tmx'),
    ]
    s = stats_module.compute(units)
    assert s['lang_pair_by_domain'] == {
        'en-US-zh-CN': {'acme.tmx': 1},
        'en-US-ja-JP': {'acme.tmx': 1},
    }
