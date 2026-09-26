from language_tools.model import TranslationUnit
from language_tools.tm import clean as clean_module


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def test_removes_exact_duplicates():
    units = [_u('Hello', '你好'), _u('Hello', '你好'), _u('Bye', '再见')]
    kept, report = clean_module.clean(units)
    assert len(kept) == 2
    assert report['removed_duplicate'] == 1
    assert report['input'] == 3
    assert report['output'] == 2


def test_keeps_same_source_different_target_not_a_duplicate():
    # This is a SOURCE_CONFLICT for qa.py, not a duplicate for clean() --
    # clean() must not silently collapse legitimate translation variants.
    units = [_u('Ready', '已就绪'), _u('Ready', '准备好了')]
    kept, report = clean_module.clean(units)
    assert len(kept) == 2
    assert report['removed_duplicate'] == 0


def test_removes_empty_source_or_target():
    units = [_u('Hello', '你好'), _u('', '空源'), _u('Empty target', ''), _u('  ', '只有空白')]
    kept, report = clean_module.clean(units)
    assert len(kept) == 1
    assert report['removed_empty'] == 3


def test_remove_identical_is_opt_in():
    units = [_u('OK', 'OK'), _u('Hello', '你好')]
    kept_default, report_default = clean_module.clean(units)
    assert len(kept_default) == 2
    assert report_default['removed_identical'] == 0

    units2 = [_u('OK', 'OK'), _u('Hello', '你好')]
    kept, report = clean_module.clean(units2, remove_identical=True)
    assert len(kept) == 1
    assert kept[0].src_text == 'Hello'
    assert report['removed_identical'] == 1


def test_normalize_collapses_whitespace_and_nfc():
    # NBSP (U+00A0) and a run of regular spaces both collapse to a single
    # normal space, so two segments that only differ by whitespace style
    # are recognized as duplicates after normalization.
    units = [_u('Hello\u00a0\u00a0world', '你好'), _u('Hello  world', '你好')]
    kept, report = clean_module.clean(units)
    assert len(kept) == 1
    assert kept[0].src_text == 'Hello world'
    assert report['normalized'] == 2
    assert report['removed_duplicate'] == 1


def test_no_normalize_flag_leaves_whitespace_variants_as_distinct():
    units = [_u('Hello\u00a0world', '你好'), _u('Hello world', '你好')]
    kept, report = clean_module.clean(units, normalize=False)
    assert len(kept) == 2
    assert report['normalized'] == 0


def test_no_dedupe_flag_keeps_exact_duplicates():
    units = [_u('Hello', '你好'), _u('Hello', '你好')]
    kept, report = clean_module.clean(units, dedupe=False)
    assert len(kept) == 2
    assert report['removed_duplicate'] == 0


def test_no_remove_empty_flag_keeps_empty_segments():
    units = [_u('', '空源')]
    kept, report = clean_module.clean(units, remove_empty=False)
    assert len(kept) == 1
    assert report['removed_empty'] == 0


def test_report_counts_are_internally_consistent():
    units = [_u('A', 'a'), _u('A', 'a'), _u('', 'x'), _u('B', 'B')]
    kept, report = clean_module.clean(units, remove_identical=True)
    assert report['input'] == 4
    assert report['output'] == len(kept)
    assert report['output'] == (report['input'] - report['removed_duplicate']
                                 - report['removed_empty'] - report['removed_identical'])
