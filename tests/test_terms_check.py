from language_tools.model import TranslationUnit
from language_tools.terms import check
from language_tools.terms.model import TermEntry


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def _entry(src_term, tgt_term, status='forbidden', src_lang='en-US', tgt_lang='zh-CN', **kw):
    return TermEntry(src_lang=src_lang, tgt_lang=tgt_lang, src_term=src_term, tgt_term=tgt_term,
                      status=status, **kw)


def test_flags_forbidden_translation_when_both_sides_match():
    glossary = [_entry('big data', '大资料', note='台湾译法，本项目统一用大陆译法')]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary)
    issues = units[0].meta['term_issues']
    assert len(issues) == 1
    assert issues[0]['src_term'] == 'big data'
    assert issues[0]['tgt_term'] == '大资料'
    assert issues[0]['note'] == '台湾译法，本项目统一用大陆译法'


def test_no_flag_when_source_term_absent():
    # Target happens to contain the forbidden string, but the source
    # never mentions the term it's a bad translation of -- not a hit.
    glossary = [_entry('big data', '大资料')]
    units = [_u('Unrelated sentence.', '这是关于大资料的无关句子。')]
    check.run(units, glossary)
    assert units[0].meta['term_issues'] == []


def test_no_flag_when_target_uses_correct_translation():
    glossary = [_entry('big data', '大资料')]
    units = [_u('This is about big data.', '这是关于大数据的。')]
    check.run(units, glossary)
    assert units[0].meta['term_issues'] == []


def test_forbidden_hits_carry_status_key():
    glossary = [_entry('big data', '大资料')]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary)
    assert units[0].meta['term_issues'][0]['status'] == 'forbidden'


def test_approved_entries_are_not_checked_by_default():
    # Default stays forbidden-only: the approved direction is opt-in
    # (see check.py docstring -- missing approved term is a hint, not a
    # defect, so it must not silently widen existing checks).
    glossary = [_entry('big data', '大资料', status='approved')]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary)
    assert units[0].meta['term_issues'] == []


def test_check_approved_flags_missing_preferred_translation():
    glossary = [_entry('big data', '大数据', status='approved', note='官方定名')]
    units = [_u('This is about big data.', '这是关于海量数据的。')]
    check.run(units, glossary, check_approved=True)
    issues = units[0].meta['term_issues']
    assert len(issues) == 1
    assert issues[0]['src_term'] == 'big data'
    assert issues[0]['tgt_term'] == '大数据'
    assert issues[0]['note'] == '官方定名'
    assert issues[0]['status'] == 'approved'


def test_check_approved_silent_when_preferred_translation_used():
    glossary = [_entry('big data', '大数据', status='approved')]
    units = [_u('This is about big data.', '这是关于大数据的。')]
    check.run(units, glossary, check_approved=True)
    assert units[0].meta['term_issues'] == []


def test_check_approved_silent_when_source_term_absent():
    # Target not using the approved term is only a hit if the source
    # actually mentions the term -- same both-sides gate as forbidden.
    glossary = [_entry('big data', '大数据', status='approved')]
    units = [_u('Unrelated sentence.', '无关的句子。')]
    check.run(units, glossary, check_approved=True)
    assert units[0].meta['term_issues'] == []


def test_check_approved_leaves_forbidden_direction_unchanged():
    glossary = [_entry('big data', '大资料')]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary, check_approved=True)
    assert [h['status'] for h in units[0].meta['term_issues']] == ['forbidden']


def test_check_approved_skips_untranslated_empty_target():
    # An empty target trivially "doesn't use" the approved term, but
    # that's qa.py's EMPTY_TARGET finding, not evidence of rewording --
    # must not flood the to-verify list with untranslated segments.
    glossary = [_entry('big data', '大数据', status='approved')]
    units = [_u('This is about big data.', ''),
             _u('This is about big data.', '   ')]
    check.run(units, glossary, check_approved=True)
    assert units[0].meta['term_issues'] == []
    assert units[1].meta['term_issues'] == []


def test_check_approved_skips_entry_with_empty_tgt_term():
    # Glossary rows can have tgt_term blank (src-only rows survive
    # glossary.read()); with nothing to look for, every src match would
    # hit unconditionally -- skip the entry instead.
    glossary = [_entry('big data', '', status='approved')]
    units = [_u('This is about big data.', '这是关于海量数据的。')]
    check.run(units, glossary, check_approved=True)
    assert units[0].meta['term_issues'] == []


def test_check_approved_skips_entries_whose_status_was_not_declared():
    # status_declared=False marks rows glossary.read() defaulted to
    # 'approved' from a blank/unrecognized status cell -- switching on
    # the approved check must not sweep a whole legacy status-less
    # glossary into the to-verify list.
    glossary = [_entry('big data', '大数据', status='approved', status_declared=False)]
    units = [_u('This is about big data.', '这是关于海量数据的。')]
    check.run(units, glossary, check_approved=True)
    assert units[0].meta['term_issues'] == []


def test_forbidden_direction_still_checks_undeclared_status_entries():
    # The status_declared gate is approved-direction-only: a forbidden
    # hit requires the wrong string to actually be present, so it keeps
    # its near-zero false-positive profile regardless of how the status
    # value was obtained.
    glossary = [_entry('big data', '大资料', status='forbidden', status_declared=False)]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary, check_approved=True)
    assert [h['status'] for h in units[0].meta['term_issues']] == ['forbidden']


def test_latin_term_matches_at_word_boundary_case_insensitively():
    glossary = [_entry('AI', 'wrongword', src_lang='en-US', tgt_lang='en-US')]
    hit = _u('The AI system failed.', 'the wrongword happened', src_lang='en-US', tgt_lang='en-US')
    no_hit = _u('She said hi.', 'main street', src_lang='en-US', tgt_lang='en-US')
    check.run([hit, no_hit], glossary)
    assert len(hit.meta['term_issues']) == 1
    assert no_hit.meta['term_issues'] == []


def test_cjk_term_matches_as_plain_substring_no_word_boundary():
    glossary = [_entry('云', 'cloud-wrong', src_lang='zh-CN', tgt_lang='en-US')]
    units = [_u('我们讨论云计算。', 'we discussed cloud-wrong computing',
                src_lang='zh-CN', tgt_lang='en-US')]
    check.run(units, glossary)
    assert len(units[0].meta['term_issues']) == 1


def test_multiple_forbidden_hits_on_one_unit_all_recorded():
    glossary = [_entry('big data', '大资料'), _entry('cloud', '云端')]
    units = [_u('big data and cloud.', '大资料和云端。')]
    check.run(units, glossary)
    assert len(units[0].meta['term_issues']) == 2


def test_summarize_counts_flagged_units():
    glossary = [_entry('big data', '大资料')]
    units = [_u('big data.', '大资料。'), _u('clean sentence.', '干净的句子。')]
    check.run(units, glossary)
    s = check.summarize(units)
    assert s == {'total': 2, 'flagged': 1, 'by_status': {'forbidden': 1}}


def test_summarize_by_status_counts_hits_per_direction_and_omits_zeros():
    glossary = [_entry('big data', '大资料'), _entry('cloud', '云计算', status='approved')]
    units = [_u('big data and cloud.', '大资料。'), _u('clean.', '干净。')]
    check.run(units, glossary, check_approved=True)
    s = check.summarize(units)
    # one forbidden hit + one approved miss on the same unit: flagged counts
    # UNITS, by_status counts HITS per direction.
    assert s == {'total': 2, 'flagged': 1, 'by_status': {'forbidden': 1, 'approved': 1}}
    assert 'repetition' not in s['by_status']


def test_summarize_tolerates_units_never_passed_to_run():
    # summarize() is public and run() is only one way to obtain units --
    # a list whose entries never went through run() has no 'term_issues'
    # key at all and must not blow up (regression guard for the
    # by_status rewrite, which briefly iterated the bare .get() result).
    units = [_u('big data.', '大资料。'), _u('clean.', '干净。')]
    s = check.summarize(units)
    assert s == {'total': 2, 'flagged': 0, 'by_status': {}}


def test_summarize_tolerates_legacy_hits_without_status_key():
    # Hits written before the approved direction existed carry no
    # 'status' key -- they can only be forbidden, same .get default the
    # CSV writer/report/GUI renderers use.
    u = _u('big data.', '大资料。')
    u.meta['term_issues'] = [{'src_term': 'big data', 'tgt_term': '大资料', 'note': ''}]
    s = check.summarize([u])
    assert s == {'total': 1, 'flagged': 1, 'by_status': {'forbidden': 1}}
