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


def test_approved_entries_are_never_checked_in_v1():
    glossary = [_entry('big data', '大资料', status='approved')]
    units = [_u('This is about big data.', '这是关于大资料的。')]
    check.run(units, glossary)
    assert units[0].meta['term_issues'] == []


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
    assert s == {'total': 2, 'flagged': 1}
