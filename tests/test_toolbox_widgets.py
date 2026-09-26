from PySide6.QtWidgets import QWidget

from toolbox.widgets import page_shell


def test_page_shell_attaches_layout_to_the_given_page(qtbot):
    page = QWidget()
    qtbot.addWidget(page)
    outer, title_label, subtitle_label = page_shell(page, 'Title', 'Subtitle')
    assert page.layout() is not None
    assert title_label.text() == 'Title'
    assert subtitle_label.text() == 'Subtitle'
    # `outer` is where a caller adds its own sections -- confirm it's live.
    marker = QWidget()
    outer.addWidget(marker)
    assert marker.parent() is not None


def test_page_shell_attaches_to_the_right_widget_even_from_a_nested_helper(qtbot):
    """Regression test: page_shell() used to infer its target by walking
    the call stack for a QWidget-typed local named `self`, which could
    silently attach to the wrong widget if page_shell() were called from
    a nested helper while an *unrelated* widget's own `__init__` (with its
    own `self`) was still on the stack. Two different widgets, each with a
    `self` on the stack at the same time, pins that the explicit `page`
    argument -- not stack position -- decides where the layout lands.
    """
    class _Outer(QWidget):
        def __init__(self, inner_target):
            super().__init__()
            self._build(inner_target)

        def _build(self, inner_target):
            # inner_target's layout must be installed on inner_target, not
            # accidentally on this _Outer instance, even though this
            # instance's `self` is on the stack the whole time.
            page_shell(inner_target, 'Inner', 'Inner subtitle')

    inner = QWidget()
    qtbot.addWidget(inner)
    outer = _Outer(inner)
    qtbot.addWidget(outer)

    assert inner.layout() is not None
    assert outer.layout() is None
