from language_tools.model import TranslationUnit
from language_tools.tm import leverage as leverage_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_exact_match_bands_as_exact():
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    candidates = [_u('Click OK to continue.', '')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'exact'
    assert candidates[0].meta['leverage_match_pct'] == 100.0
    assert candidates[0].meta['leverage_repetition'] is False


def test_exact_match_is_case_and_whitespace_insensitive():
    tm = [_u('Click  OK to continue.', '')]
    candidates = [_u('click ok to continue.', '')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'exact'


def test_no_overlap_bands_as_no_match():
    tm = [_u('Completely unrelated sentence about weather.', '')]
    candidates = [_u('Click OK to continue.', '')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'no_match'
    assert candidates[0].meta['leverage_match_pct'] == 0.0


def test_empty_tm_bands_everything_as_no_match():
    candidates = [_u('Click OK to continue.', '')]
    leverage_module.analyze([], candidates)
    assert candidates[0].meta['leverage_band'] == 'no_match'


def test_language_pair_scoping_ignores_wrong_pair_tm_entries():
    tm = [_u('Click OK to continue.', '点击确定以继续。', src_lang='en-US', tgt_lang='ja-JP')]
    candidates = [_u('Click OK to continue.', '', src_lang='en-US', tgt_lang='zh-CN')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'no_match'


def test_repeated_candidate_segment_bands_as_repetition_not_exact():
    tm = []  # no TM at all -- repetition still detected purely within candidates
    candidates = [_u('Save changes before exiting.', ''), _u('Save changes before exiting.', '')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'no_match'
    assert candidates[0].meta['leverage_repetition'] is False
    assert candidates[1].meta['leverage_band'] == 'repetition'
    assert candidates[1].meta['leverage_repetition'] is True


def test_fuzzy_match_lands_in_expected_band():
    tm = [_u('The quick brown fox jumps over the lazy dog.', '')]
    candidates = [_u('The quick brown fox jumps over a lazy dog.', '')]  # one word changed
    leverage_module.analyze(tm, candidates)
    band = candidates[0].meta['leverage_band']
    assert band in ('95-99', '85-94')  # near-exact, single small edit
    assert candidates[0].meta['leverage_match_pct'] < 100.0


def test_below_fuzzy_floor_is_no_match():
    tm = [_u('Alpha bravo charlie delta echo foxtrot golf.', '')]
    candidates = [_u('Something else entirely different here today.', '')]
    leverage_module.analyze(tm, candidates, fuzzy_floor=0.90)
    assert candidates[0].meta['leverage_band'] == 'no_match'


def test_empty_candidate_source_is_no_match():
    tm = [_u('Click OK to continue.', '')]
    candidates = [_u('', '')]
    leverage_module.analyze(tm, candidates)
    assert candidates[0].meta['leverage_band'] == 'no_match'


def test_summarize_counts_and_word_counts_per_band():
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    candidates = [
        _u('Click OK to continue.', ''),           # exact, 4 words
        _u('Click OK to continue.', ''),           # repetition, 4 chars->words (en, whitespace split) 4
        _u('Totally unrelated content here.', ''),  # no_match, 4 words
    ]
    leverage_module.analyze(tm, candidates)
    s = leverage_module.summarize(candidates)
    assert s['total'] == 3
    assert s['bands']['exact']['count'] == 1
    assert s['bands']['exact']['words'] == 4
    assert s['bands']['repetition']['count'] == 1
    assert s['bands']['no_match']['count'] == 1
    assert s['total_words'] == 12
    # every BANDS entry present even at zero
    for band in leverage_module.BANDS:
        assert band in s['bands']


def test_summarize_uses_char_count_for_cjk_source():
    candidates = [_u('这是一个测试句子。', '', src_lang='zh-CN', tgt_lang='en-US')]
    leverage_module.analyze([], candidates)
    s = leverage_module.summarize(candidates)
    # 9 CJK characters, punctuation included, whitespace stripped
    assert s['total_words'] == len('这是一个测试句子。')


def test_summarize_empty_candidates_does_not_raise():
    s = leverage_module.summarize([])
    assert s['total'] == 0
    assert s['total_words'] == 0
    for band in leverage_module.BANDS:
        assert s['bands'][band] == {'count': 0, 'words': 0}
