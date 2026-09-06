"""App-wide tooltip tuning.

Two complaints, both real usability problems, not just polish:
1. Qt's default tooltip wake-up delay (~700ms) feels laggy.
2. Qt positions the tooltip directly under the cursor, so the cursor
   itself covers the tooltip's own first character or two.

Both are fixed here globally, once, so every ordinary ``widget.setToolTip(
text)`` call elsewhere in the code keeps working unchanged -- nothing
about how tooltips are *set* needs to change, only how/when they render.
Font/color styling for tooltips lives in style.qss's ``QToolTip`` selector
instead (Qt respects that selector natively), not here.
"""
from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QProxyStyle, QStyle, QToolTip

WAKE_UP_DELAY_MS = 200          # Qt's default is ~700ms
CURSOR_OFFSET = QPoint(14, 22)  # keeps the cursor from covering the text


class QuickTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return WAKE_UP_DELAY_MS
        return super().styleHint(hint, option, widget, returnData)


class _TooltipPositioner(QObject):
    """Installed as an app-wide event filter: intercepts Qt's ToolTip
    event and re-shows it offset from the cursor instead of letting Qt's
    default handling place it directly under the pointer.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip:
            text = obj.toolTip() if hasattr(obj, 'toolTip') else ''
            if text:
                QToolTip.showText(QCursor.pos() + CURSOR_OFFSET, text, obj)
                return True
        return super().eventFilter(obj, event)


def install(app):
    """Call once, right after creating QApplication."""
    app.setStyle(QuickTooltipStyle(app.style()))
    positioner = _TooltipPositioner(app)
    app.installEventFilter(positioner)
    app._quick_tooltip_positioner = positioner  # keep it alive
    return positioner
