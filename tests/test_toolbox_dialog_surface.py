"""Regression tests for the "all-black confirmation dialog" bug.

The bare ``QWidget { background: transparent; ... }`` rule in style.qss
matches QDialog/QMessageBox as well (a QSS type selector matches
subclasses), and when two rules tie on specificity the one declared LAST
wins -- so the ``QMainWindow, QDialog, QMessageBox { background: ... }``
rule was silently overridden by the QWidget rule declared after it. A
top-level dialog left with a transparent stylesheet background paints
nothing at all, which composites to solid black on Windows, with
ink-colored (#1A1D23) message text invisible on top of it.

Two guards, matching the two ways this bug can come back:
- someone reorders style.qss so the dialog rule sits above the QWidget
  rule again (guarded textually: assert the rule order, failing with a
  message that spells out the ordering contract), or
- someone removes/simplifies the dialog rule entirely (guarded
  behaviorally: render a real QMessageBox under the real stylesheet
  offscreen and require its surface to actually be the paper token,
  not the unpainted rgba(0,0,0,0) it regressed to -- verified at bug
  time by grabbing the dialog and sampling its pixels).
"""
import os

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMessageBox

RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'toolbox', 'resources')

_PAPER = QColor(246, 247, 249)  # the paper design token, #F6F7F9


def _load_stylesheet():
    """The same {ICONS_DIR} substitution toolbox.main._load_stylesheet()
    performs, so the sheet under test is byte-identical to production's
    (a literal leftover placeholder would change url() resolution and
    with it what the sheet actually does to icon-bearing widgets)."""
    icons_dir = os.path.join(RESOURCES_DIR, 'icons').replace(os.sep, '/')
    with open(os.path.join(RESOURCES_DIR, 'style.qss'), encoding='utf-8') as f:
        return f.read().replace('{ICONS_DIR}', icons_dir)


def test_dialog_surface_rule_is_declared_after_the_bare_qwidget_rule():
    with open(os.path.join(RESOURCES_DIR, 'style.qss'), encoding='utf-8') as f:
        content = f.read()
    qwidget_rule = content.index('QWidget {')
    dialog_rule = content.index('QMainWindow, QDialog, QMessageBox {')
    assert dialog_rule > qwidget_rule, (
        "style.qss: the top-level surface rule "
        "(QMainWindow, QDialog, QMessageBox) must be declared AFTER the "
        "bare QWidget rule. Type selectors match subclasses, both rules "
        "are equal-specificity single type selectors, and Qt resolves "
        "ties in favor of whichever rule came last -- declared above the "
        "QWidget rule, the dialog rule is silently overridden by it and "
        "every modal dialog renders unpainted (solid black on Windows, "
        "message text invisible) again.")


def test_message_box_renders_a_painted_paper_surface(qtbot):
    app = QApplication.instance()
    original = app.styleSheet()
    app.setStyleSheet(_load_stylesheet())
    box = QMessageBox()
    qtbot.addWidget(box)
    try:
        box.setWindowTitle('确认清理')
        box.setText('将删除 重复 3 / 空段 0 / 原文=译文 0 条（共 10 → 7）。是否继续？')
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.show()
        qtbot.wait(0)  # let the offscreen platform lay the dialog out
        img = box.grab().toImage()
        # Sample inside the dialog but away from its frame, the icon, the
        # message label, and the button row: these spots are pure dialog
        # surface (all verified paper after the fix; under the bug every
        # one of them was rgba(0,0,0,0), i.e. never painted at all).
        spots = ((12, 12), (img.width() - 20, 15),
                 (img.width() // 2, 12), (8, img.height() // 2))
        for spot in spots:
            c = img.pixelColor(*spot)
            assert c == _PAPER, (
                'message box surface at %r is %s (alpha %d), expected '
                'paper #F6F7F9 -- the dialog background is not being '
                'painted; the all-black-confirm-dialog regression is '
                'back (see style.qss\'s top-level surfaces rule and its '
                'ORDER IS LOAD-BEARING comment)' %
                (spot, c.name(), c.alpha()))
    finally:
        app.setStyleSheet(original)
