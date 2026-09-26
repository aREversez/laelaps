from PySide6.QtWidgets import QComboBox

from toolbox.widgets import compact_combo, make_lang_combo


def test_compact_combo_width_covers_widest_item_plus_chrome(qtbot):
    """Regression test for the real-Windows bug where a long item like
    '简体中文 (zh-CN)' had its first character clipped against the box's
    left edge -- see compact_combo()'s docstring for the full story. The
    box's minimum width must be at least wide enough to paint the widest
    item's text without the stylesheet's own padding/border/arrow chrome
    eating into it.
    """
    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(['短', '简体中文 (zh-CN)', '英语 (en-US)'])
    compact_combo(combo)

    fm = combo.fontMetrics()
    widest_text_px = max(fm.horizontalAdvance(t) for t in
                          ['短', '简体中文 (zh-CN)', '英语 (en-US)'])
    assert combo.minimumWidth() >= widest_text_px + 40  # generous chrome floor


def test_compact_combo_on_lang_combo_covers_longest_lang_choice(qtbot):
    # make_lang_combo()'s LANG_CHOICES includes labels like
    # '简体中文 (zh-CN)' and '葡萄牙语 (pt-PT)' -- exercise the actual
    # combo this bug was reported against, not just a synthetic one.
    combo = make_lang_combo('en-US')
    qtbot.addWidget(combo)
    compact_combo(combo)

    fm = combo.fontMetrics()
    widest_text_px = max(fm.horizontalAdvance(combo.itemText(i))
                          for i in range(combo.count()))
    assert combo.minimumWidth() >= widest_text_px + 40


def test_compact_combo_does_not_shrink_below_a_short_items_needs(qtbot):
    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(['是', '否'])
    compact_combo(combo)
    assert combo.minimumWidth() >= 1  # never zero/negative
