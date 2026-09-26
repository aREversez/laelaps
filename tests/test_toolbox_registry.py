import pytest

from toolbox.registry import TOOLS, ToolSpec, register


def test_register_appends_to_registry():
    before = len(TOOLS)
    register(ToolSpec(id='__test_tool__', name='Test', description='', icon='', page_factory=lambda: None))
    assert len(TOOLS) == before + 1
    assert TOOLS[-1].id == '__test_tool__'
    TOOLS.pop()  # don't leak into other tests


def test_register_rejects_duplicate_id():
    register(ToolSpec(id='__dup__', name='A', description='', icon='', page_factory=lambda: None))
    try:
        with pytest.raises(ValueError):
            register(ToolSpec(id='__dup__', name='B', description='', icon='', page_factory=lambda: None))
    finally:
        TOOLS.pop()


def test_toolspec_order_defaults_high_not_zero():
    # A forgotten `order=` must sort to the very end, not collide with
    # home's explicit order=0 and land wherever discovery order happens
    # to put it.
    spec = ToolSpec(id='__no_order__', name='X', description='', icon='', page_factory=lambda: None)
    assert spec.order == 999


def test_discover_includes_corpus_convert():
    from toolbox.registry import discover
    tools = discover()
    ids = [t.id for t in tools]
    assert 'corpus_convert' in ids
