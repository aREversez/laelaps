import pytest

from language_tools.model import TranslationUnit
from language_tools.tm import merge as merge_module


def _u(src, tgt, modified_at=None):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt,
                            modified_at=modified_at)


def test_keep_all_is_default_and_just_concatenates():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '你好'), _u('Bye', '再见')]
    merged, report = merge_module.merge([a, b])
    assert len(merged) == 3
    assert report['input'] == 3
    assert report['output'] == 3
    assert report['conflicts_resolved'] == 0


def test_prefer_first_keeps_earliest_conflicting_translation():
    a = [_u('Ready', '已就绪')]
    b = [_u('Ready', '准备好了')]
    merged, report = merge_module.merge([a, b], strategy='prefer-first')
    assert len(merged) == 1
    assert merged[0].tgt_text == '已就绪'
    assert report['conflicts_resolved'] == 1


def test_prefer_last_keeps_latest_conflicting_translation():
    a = [_u('Ready', '已就绪')]
    b = [_u('Ready', '准备好了')]
    merged, report = merge_module.merge([a, b], strategy='prefer-last')
    assert len(merged) == 1
    assert merged[0].tgt_text == '准备好了'
    assert report['conflicts_resolved'] == 1


def test_prefer_newer_uses_modified_at_regardless_of_input_order():
    # b appears second in the input list but has an *older* timestamp, so
    # prefer-newer must pick a's translation even though prefer-last would
    # have picked b's.
    a = [_u('Ready', '已就绪', modified_at='2025-06-01T00:00:00Z')]
    b = [_u('Ready', '准备好了', modified_at='2024-01-01T00:00:00Z')]
    merged, report = merge_module.merge([a, b], strategy='prefer-newer')
    assert len(merged) == 1
    assert merged[0].tgt_text == '已就绪'


def test_prefer_newer_treats_missing_timestamp_as_oldest():
    a = [_u('Ready', '已就绪', modified_at=None)]
    b = [_u('Ready', '准备好了', modified_at='2024-01-01T00:00:00Z')]
    merged, report = merge_module.merge([a, b], strategy='prefer-newer')
    assert merged[0].tgt_text == '准备好了'


def test_matching_targets_across_inputs_are_not_a_conflict():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '你好')]
    merged, report = merge_module.merge([a, b], strategy='prefer-last')
    assert len(merged) == 1
    assert report['conflicts_resolved'] == 0


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        merge_module.merge([[_u('A', 'a')]], strategy='not-a-real-strategy')
