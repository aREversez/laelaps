"""Unit-level regression tests for the two bugs found and fixed while
porting the seed script (see splitters.py module docstring for the full
empirical writeup of each).
"""
import pytest

from language_tools.align.splitters import is_cjk_lang, looks_cjk, pick_splitter, split_en, split_zh

# Every ABBREV entry with an internal period ends in "single letter + period",
# which is exactly the pattern the removed regex clause misfired on. Locking
# all of them down, not just a.m./p.m., since they share the same root cause.
INTERNAL_PERIOD_ABBREVS = [
    ('He left at 3 a.m. It was still dark.', 'a.m.'),
    ('He left at 3 p.m. It was still light.', 'p.m.'),
    ('Sales grew, e.g. in Q3 they doubled.', 'e.g.'),
    ('The team, i.e. engineering, missed the deadline.', 'i.e.'),
    ('Shipped to the U.S. last quarter.', 'U.S.'),
    ('Shipped to the U.K. last quarter.', 'U.K.'),
    ('Reviewed by Dr. Smith, Ph.D. before publication.', 'Ph.D.'),
]


@pytest.mark.parametrize('text,abbrev', INTERNAL_PERIOD_ABBREVS)
def test_split_en_does_not_split_on_internal_period_abbreviations(text, abbrev):
    pieces = split_en(text)
    assert not any(p.strip() == text.split(abbrev)[0].strip() + abbrev for p in pieces), (
        'abbreviation %r caused a bogus split in %r -> %r' % (abbrev, text, pieces))


def test_split_en_still_splits_real_sentences():
    # No abbreviation directly before the period here, so this should still
    # split normally -- the fix only stops false splits ON abbreviations,
    # it doesn't change how genuine sentence boundaries are detected.
    pieces = split_en('Dr. Smith arrived at 9 a.m. and started the meeting. '
                       "He also discussed next quarter's budget.")
    assert pieces == ['Dr. Smith arrived at 9 a.m. and started the meeting.',
                       "He also discussed next quarter's budget."]


def test_split_en_treats_known_abbreviations_as_always_non_breaking():
    # By design (matches conventional sentence tokenizers like NLTK punkt),
    # a period on a listed abbreviation is never treated as a sentence
    # boundary, even in the rare case where the abbreviation genuinely ends
    # the sentence. This is an accepted, documented heuristic limitation,
    # not something this fix attempts to solve with full disambiguation.
    pieces = split_en('The meeting starts at 9 a.m. He should not be late.')
    assert pieces == ['The meeting starts at 9 a.m. He should not be late.']


def test_split_en_still_treats_bare_initials_as_abbreviation():
    # "J." is not in ABBREV, but the standalone-capital-initial heuristic
    # (separate from the removed clause) should still catch it.
    pieces = split_en('Meet John J. Smith at noon.')
    assert pieces == ['Meet John J. Smith at noon.']


def test_split_zh_basic():
    assert split_zh('第一句。第二句！第三句？') == ['第一句。', '第二句！', '第三句？']


def test_pick_splitter_dispatches_on_declared_language_not_position():
    fn, join, tag = pick_splitter('zh-CN', 'irrelevant sample', 'src')
    assert fn is split_zh and join == '' and tag == 'zh'
    fn, join, tag = pick_splitter('en-US', 'irrelevant sample', 'tgt')
    assert fn is split_en and join == ' ' and tag == 'en'


def test_pick_splitter_falls_back_to_content_sniff(capsys):
    # declared as English, but the sample is mostly CJK -- should warn and
    # use the CJK splitter anyway rather than mis-segmenting it as Latin text.
    fn, join, tag = pick_splitter('en-US', '这是一段主要是中文的示例文本内容。', 'src')
    assert fn is split_zh and tag == 'zh'
    assert 'warning' in capsys.readouterr().out


def test_is_cjk_lang():
    assert is_cjk_lang('zh-CN')
    assert is_cjk_lang('ja-JP')
    assert not is_cjk_lang('en-US')


def test_looks_cjk():
    assert looks_cjk('这是中文')
    assert not looks_cjk('This is English')
