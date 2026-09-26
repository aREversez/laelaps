from PySide6.QtWidgets import QStyle

from toolbox import tooltips


def test_install_sets_reduced_wakeup_delay(qtbot):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    tooltips.install(app)
    style = app.style()
    delay = style.styleHint(QStyle.SH_ToolTip_WakeUpDelay)
    assert delay == tooltips.WAKE_UP_DELAY_MS
    assert delay < 700  # meaningfully faster than Qt's default


def test_cursor_offset_is_nonzero_so_pointer_does_not_cover_text():
    # The whole point of the offset is that the tooltip doesn't render
    # directly under the cursor (which covers its own first character or
    # two) -- a zero offset would silently regress back to that.
    assert tooltips.CURSOR_OFFSET.x() > 0
    assert tooltips.CURSOR_OFFSET.y() > 0


def test_stylesheet_styles_qtooltip_with_a_real_font():
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         'toolbox', 'resources', 'style.qss')
    with open(path, encoding='utf-8') as f:
        content = f.read()
    assert 'QToolTip' in content
    assert 'Microsoft YaHei UI' in content.split('QToolTip')[1].split('}')[0]
