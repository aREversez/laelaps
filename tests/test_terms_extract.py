import pytest

from language_tools.model import TranslationUnit
from language_tools.terms import extract as extract_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_extract_candidates_finds_repeated_multiword_phrase():
    units = [
        _u('Click OK to continue.', ''),
        _u('Click OK to proceed.', ''),
        _u('Click OK to confirm.', ''),
    ]
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=2, max_ngram=2)
    texts = {c['text'] for c in candidates}
    assert 'Click OK' in texts


def test_extract_candidates_respects_min_freq():
    units = [_u('Unique phrase here.', '')]
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=2, max_ngram=3)
    assert candidates == []


def test_extract_candidates_drops_bare_stopword_unigram():
    units = [_u('to the to the to the', '')] * 1
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=1, max_ngram=1)
    texts = {c['text'] for c in candidates}
    assert 'to' not in texts
    assert 'the' not in texts


def test_extract_candidates_drops_candidate_starting_or_ending_on_stopword():
    units = [_u('to the store and the store again', '')]
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=1, min_ngram=2,
                                                     max_ngram=2)
    texts = {c['text'] for c in candidates}
    assert 'the store' not in texts  # starts on a stopword
    assert 'store and' not in texts  # would end mid-word chain awkwardly; sanity check


def test_extract_candidates_scoped_to_requested_language():
    units = [_u('Machine learning model.', '机器学习模型。')]
    en_candidates = extract_module.extract_candidates(units, 'en-US', min_freq=1, max_ngram=2)
    zh_candidates = extract_module.extract_candidates(units, 'zh-CN', side='tgt', min_freq=1,
                                                        max_ngram=2)
    assert any('Machine' in c['text'] for c in en_candidates)
    assert all(all(ord(ch) < 128 for ch in c['text']) is False for c in zh_candidates)


def test_extract_candidates_cjk_uses_character_ngrams_not_words():
    units = [_u('', '机器翻译系统。机器翻译效果。机器翻译质量。', tgt_lang='zh-CN')]
    candidates = extract_module.extract_candidates(units, 'zh-CN', side='tgt', min_freq=3,
                                                     min_ngram=2, max_ngram=4)
    texts = {c['text'] for c in candidates}
    assert '机器翻译' in texts


def test_extract_candidates_nested_shorter_candidate_dropped():
    # "机器翻译" appears 3x; "机器" and "翻译" never appear without each other,
    # so they should be absorbed into the longer candidate, not listed
    # separately at a comparable rank.
    units = [_u('', '机器翻译。机器翻译。机器翻译。', tgt_lang='zh-CN')]
    candidates = extract_module.extract_candidates(units, 'zh-CN', side='tgt', min_freq=1,
                                                     min_ngram=1, max_ngram=4)
    texts = [c['text'] for c in candidates]
    assert '机器翻译' in texts
    assert '机器' not in texts
    assert '翻译' not in texts


def test_extract_candidates_top_n_limits_results():
    units = [_u('Alpha bravo. Charlie delta. Echo foxtrot.', '')]
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=1, max_ngram=1,
                                                     top_n=2)
    assert len(candidates) == 2


def test_extract_candidates_top_n_zero_returns_nothing():
    # top_n=0 means "no candidates", not "unlimited" -- the old `if top_n`
    # truthiness check treated 0 as falsy and returned the whole list.
    units = [_u('Alpha bravo. Charlie delta. Echo foxtrot.', '')]
    candidates = extract_module.extract_candidates(units, 'en-US', min_freq=1, max_ngram=1,
                                                     top_n=0)
    assert candidates == []


def test_extract_candidates_empty_units_returns_empty_list():
    assert extract_module.extract_candidates([], 'en-US') == []


def test_suggest_bilingual_candidates_pairs_a_clear_1to1_term():
    units = [
        _u('Click OK to continue with the installation.', '点击确定以继续安装过程。'),
        _u('Click OK to proceed.', '点击确定以继续。'),
        _u('The installation wizard will now close.', '安装向导现在将会关闭。'),
        _u('Click OK to confirm the installation.', '点击确定以确认安装。'),
        _u('Please wait while the installation completes.', '请稍候，安装正在完成。'),
    ]
    results = extract_module.suggest_bilingual_candidates(
        units, 'en-US', 'zh-CN', min_freq=2, max_ngram=4, min_pair_freq=2,
        concentration_floor=1.5)
    by_src = {r['src_term']: r for r in results}
    assert by_src['Click OK']['tgt_term'] == '点击确定'
    assert by_src['Click OK']['pair_freq'] == 3


def test_suggest_bilingual_candidates_leaves_ambiguous_term_unpaired():
    # "installation" co-occurs with several different Chinese renderings,
    # none of them dominant enough to clear the concentration bar.
    units = [
        _u('Click OK to continue with the installation.', '点击确定以继续安装过程。'),
        _u('The installation wizard will now close.', '安装向导现在将会关闭。'),
        _u('Please wait while the installation completes.', '请稍候，安装正在完成。'),
        _u('Click OK to confirm the installation.', '点击确定以确认安装。'),
    ]
    results = extract_module.suggest_bilingual_candidates(
        units, 'en-US', 'zh-CN', min_freq=2, max_ngram=4, min_pair_freq=2,
        concentration_floor=1.5)
    by_src = {r['src_term']: r for r in results}
    assert by_src['installation']['tgt_term'] == ''
    assert by_src['installation']['pair_freq'] == 0
    assert by_src['installation']['concentration'] == 0.0


def test_suggest_bilingual_candidates_breaks_concentration_tie_by_pair_freq():
    # "gamma delta epsilon zeta" (local 3/4, global 3/12) and "theta iota"
    # (local 4/4, global 4/12) have exactly equal concentration (3.0), but
    # "theta iota" co-occurs more often (pair_freq 4 vs 3) -- the docstring
    # promises ties are broken by co-occurrence count, so it must win even
    # though the ranking score puts the 4-token candidate first.
    units = [
        _u('alpha beta one two', 'gamma delta epsilon zeta theta iota',
           src_lang='en-US', tgt_lang='en-US'),
        _u('alpha beta three four', 'xray gamma delta epsilon zeta theta iota yankee',
           src_lang='en-US', tgt_lang='en-US'),
        _u('alpha beta five six', 'gamma delta epsilon zeta theta iota',
           src_lang='en-US', tgt_lang='en-US'),
        _u('alpha beta seven eight', 'theta iota',
           src_lang='en-US', tgt_lang='en-US'),
        _u('kilo lima mike', 'november oscar papa',
           src_lang='en-US', tgt_lang='en-US'),
        _u('quebec romeo sierra', 'tango uniform victor',
           src_lang='en-US', tgt_lang='en-US'),
        _u('golf hotel india', 'juliet whiskey xray',
           src_lang='en-US', tgt_lang='en-US'),
        _u('papa quebec romeo', 'sierra tango uniform',
           src_lang='en-US', tgt_lang='en-US'),
        _u('hotel india juliet', 'kilo lima mike',
           src_lang='en-US', tgt_lang='en-US'),
        _u('oscar papa quebec', 'romeo sierra tango',
           src_lang='en-US', tgt_lang='en-US'),
        _u('uniform victor whiskey', 'xray yankee zulu',
           src_lang='en-US', tgt_lang='en-US'),
        _u('bravo charlie echo', 'foxtrot golf hotel',
           src_lang='en-US', tgt_lang='en-US'),
    ]
    results = extract_module.suggest_bilingual_candidates(
        units, 'en-US', 'en-US', min_freq=2, max_ngram=4, min_pair_freq=2,
        concentration_floor=2.5)
    by_src = {r['src_term']: r for r in results}
    assert by_src['alpha beta']['tgt_term'] == 'theta iota'
    assert by_src['alpha beta']['pair_freq'] == 4
    assert by_src['alpha beta']['concentration'] == 3.0


def test_suggest_bilingual_candidates_small_corpus_returns_no_pairings():
    units = [_u('Click OK to continue.', '点击确定以继续。')]
    results = extract_module.suggest_bilingual_candidates(
        units, 'en-US', 'zh-CN', min_freq=1, max_ngram=3, min_pair_freq=2)
    assert all(r['tgt_term'] == '' for r in results)


def test_suggest_bilingual_candidates_empty_units_does_not_raise():
    assert extract_module.suggest_bilingual_candidates([], 'en-US', 'zh-CN') == []


def test_write_and_promote_round_trip_for_approved_row(tmp_path):
    candidates = [
        {'src_term': 'Click OK', 'tgt_term': '点击确定', 'src_freq': 3,
         'pair_freq': 3, 'concentration': 1.67},
        {'src_term': 'installation', 'tgt_term': '', 'src_freq': 4,
         'pair_freq': 0, 'concentration': 0.0},
    ]
    path = tmp_path / 'candidates.csv'
    extract_module.write_candidates_csv(str(path), candidates)
    content = path.read_text(encoding='utf-8-sig')
    assert 'Click OK' in content
    assert 'decision' in content

    # No decisions filled in yet -- nothing should promote.
    assert extract_module.promote_reviewed_candidates(str(path), 'en-US', 'zh-CN') == []

    # Simulate a reviewer approving the first row and leaving the second alone.
    lines = content.splitlines()
    header = lines[0].split(',')
    decision_idx = header.index('decision')
    row = lines[1].split(',')
    row[decision_idx] = 'approve'
    lines[1] = ','.join(row)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')

    entries = extract_module.promote_reviewed_candidates(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'Click OK'
    assert entries[0].tgt_term == '点击确定'
    assert entries[0].status == 'approved'
    assert entries[0].src_lang == 'en-US'
    assert entries[0].tgt_lang == 'zh-CN'


def test_promote_reviewed_candidates_rejects_approved_row_with_blank_tgt(tmp_path):
    path = tmp_path / 'candidates.csv'
    extract_module.write_candidates_csv(
        str(path), [{'src_term': 'foo', 'tgt_term': '', 'src_freq': 2}])
    content = path.read_text(encoding='utf-8-sig')
    lines = content.splitlines()
    header = lines[0].split(',')
    decision_idx = header.index('decision')
    row = lines[1].split(',')
    row[decision_idx] = 'approve'
    lines[1] = ','.join(row)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')

    with pytest.raises(ValueError, match='no tgt_term'):
        extract_module.promote_reviewed_candidates(str(path), 'en-US', 'zh-CN')


def test_promote_reviewed_candidates_requires_expected_columns(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('foo,bar\n1,2\n', encoding='utf-8-sig')
    with pytest.raises(ValueError, match='missing required column'):
        extract_module.promote_reviewed_candidates(str(path), 'en-US', 'zh-CN')


def test_promote_reviewed_candidates_empty_file_returns_empty_list(tmp_path):
    path = tmp_path / 'empty.csv'
    path.write_text('', encoding='utf-8-sig')
    assert extract_module.promote_reviewed_candidates(str(path), 'en-US', 'zh-CN') == []
