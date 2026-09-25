from language_tools.model import TranslationUnit
from language_tools.tm import compare as compare_module
from language_tools.tm import io as tm_io


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_requires_at_least_two_inputs():
    try:
        compare_module.compare([('a', [_u('Hello', '你好')])])
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'at least 2' in str(e)


def test_segment_unique_to_one_input_is_counted_there_only():
    a = [_u('Hello', '你好')]
    b = [_u('Bye', '再见')]
    report = compare_module.compare([('a', a), ('b', b)])
    assert report['unique_segments'] == {'a': 1, 'b': 1}
    assert report['shared_segments'] == 0
    assert report['conflicts'] == []


def test_agreeing_segment_across_inputs_is_shared_not_conflicting():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '你好')]
    report = compare_module.compare([('a', a), ('b', b)])
    assert report['shared_segments'] == 1
    assert report['unique_segments'] == {'a': 0, 'b': 0}
    assert report['conflicts'] == []


def test_disagreeing_segment_across_inputs_is_a_conflict():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '您好')]
    report = compare_module.compare([('a', a), ('b', b)])
    assert report['shared_segments'] == 0
    assert len(report['conflicts']) == 1
    entry = report['conflicts'][0]
    assert entry['src'] == 'Hello'
    assert entry['labels'] == {'a': ['你好'], 'b': ['您好']}


def test_three_way_comparison_conflict_lists_only_owning_labels():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '您好')]
    c = [_u('Bye', '再见')]  # c doesn't have "Hello" at all
    report = compare_module.compare([('a', a), ('b', b), ('c', c)])
    assert len(report['conflicts']) == 1
    assert set(report['conflicts'][0]['labels'].keys()) == {'a', 'b'}
    assert report['unique_segments']['c'] == 1


def test_totals_reflect_raw_unit_count_including_duplicates():
    a = [_u('Hello', '你好'), _u('Hello', '你好')]  # duplicate within one input
    b = [_u('Bye', '再见')]
    report = compare_module.compare([('a', a), ('b', b)])
    assert report['totals'] == {'a': 2, 'b': 1}
    # duplicate within one input still counts as one shared/unique segment, not two
    assert report['unique_segments']['a'] == 1


def test_conflicts_are_ordered_by_first_appearance_across_inputs():
    a = [_u('First', 'A1'), _u('Second', 'B1')]
    b = [_u('Second', 'B2'), _u('First', 'A2')]
    report = compare_module.compare([('a', a), ('b', b)])
    assert [c['src'] for c in report['conflicts']] == ['First', 'Second']


def test_write_conflicts_csv(tmp_path):
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '您好')]
    report = compare_module.compare([('a', a), ('b', b)])
    out = tmp_path / 'conflicts.csv'
    compare_module.write_conflicts_csv(str(out), report)
    content = out.read_text(encoding='utf-8-sig')
    lines = content.strip().splitlines()
    assert lines[0] == 'source,a,b'
    assert lines[1] == 'Hello,你好,您好'


def test_write_conflicts_csv_blanks_labels_that_do_not_own_the_source(tmp_path):
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '您好')]
    c = [_u('Bye', '再见')]
    report = compare_module.compare([('a', a), ('b', b), ('c', c)])
    out = tmp_path / 'conflicts.csv'
    compare_module.write_conflicts_csv(str(out), report)
    lines = out.read_text(encoding='utf-8-sig').strip().splitlines()
    assert lines[0] == 'source,a,b,c'
    assert lines[1] == 'Hello,你好,您好,'


def test_compare_rejects_duplicate_labels_instead_of_merging():
    # P0-3: every report dict is keyed by label, so a duplicate label would
    # silently merge two inputs under one key rather than error. compare()
    # now raises; callers avoid duplicates by building labels via make_labels.
    try:
        compare_module.compare([('a', [_u('Hello', '你好')]),
                                ('a', [_u('Bye', '再见')])])
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'share a label' in str(e)


def test_make_labels_disambiguates_same_basename_across_dirs():
    labels = tm_io.make_labels(['q1/same.tmx', 'q2/same.tmx', 'q3/same.tmx'])
    assert labels == ['same.tmx', 'same-2.tmx', 'same-3.tmx']


def test_make_labels_handles_backslash_paths_and_real_dash_number_collisions():
    # Windows-style separators must not come back as one giant basename on
    # POSIX; and a genuine 'a-2.tmx' input must not be clobbered by the
    # generated suffix of a colliding 'a.tmx' (the while-loop keeps bumping).
    labels = tm_io.make_labels(['\\dir\\a-2.tmx', 'y/a.tmx', 'z/a.tmx'])
    assert labels == ['a-2.tmx', 'a.tmx', 'a-3.tmx']
