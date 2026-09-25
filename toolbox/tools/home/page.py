"""The home page: a registry-driven overview of every tool, replacing a
bare jump-into-the-first-tool launch (2026-09 UI modernization round).

Deliberately data-driven like the sidebar itself -- this page imports
``registry.discover()`` and renders one tile per ToolSpec (its own tile
excluded), so a new tool shows up here without this file changing, same
guarantee ``main_window.py`` has for the sidebar.

Navigation works through one signal, ``toolRequested(id)``: the page
never reaches for ``MainWindow`` (no parentWidget() walks, no stack
references) -- ``main_window.py`` connects the signal to its own
``select_tool()`` where it wires the page up. The shell stays unaware of
any specific tool, including this one; the only convention is that a
page emitting ``toolRequested`` asks to be taken somewhere by id.

Tiles are flat white cards with a hairline border, like everything else
-- the round's reserved elevation shadow (DESIGN.md §13) is applied here
only while hovered (``_set_lifted()``), so a tile reads as
lift-off-the-page-and-clickable without any tile sitting in shadow
permanently. Icons are the sidebar glyphs re-rendered big and tinted
indigo via ``widgets.tinted_icon_pixmap()`` (gray-at-32px would read as
disabled next to the interactive-card affordance).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget,
)

from toolbox import registry
from toolbox.widgets import tinted_icon_pixmap

# Tiles per row. 3 keeps description text (one short line, elided by
# word-wrap at tile width) readable at the 1280px default window width
# without horizontal scrolling ever being needed.
_TILE_COLUMNS = 3

_TILE_ICON_PX = 32


class _ToolTile(QWidget):
    """One clickable tool card: icon + name + description, emits
    ``clicked`` on a press-and-release inside its own bounds (Qt's own
    button semantics, reimplemented cheaply because QFrame gives no
    clicked signal and promoting every tile to QPushButton would fight
    the multi-line layout QPushButton's icon+text arrangement can't
    do). Enter/Space keyboard activation included -- a tile you can
    see is a tile you should be able to reach without a mouse.
    """
    clicked = Signal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self._spec = spec
        self.setObjectName('homeTile')
        # A QWidget subclass does not paint its QSS background unless it
        # opts into styled backgrounds; without this the tile stayed
        # transparent and showed the page behind it (black before the
        # central widget painted paper). Plain QWidgets like pageCard don't
        # need it -- only subclasses do.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        icon_label = QLabel()
        if spec.icon:
            pixmap = tinted_icon_pixmap(spec.icon, _TILE_ICON_PX)
            icon_label.setPixmap(pixmap)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(icon_label)
        name = QLabel(spec.name)
        name.setObjectName('homeTileName')
        name_row.addWidget(name)
        name_row.addStretch(1)
        layout.addLayout(name_row)

        desc = QLabel(spec.description)
        desc.setObjectName('homeTileDesc')
        desc.setWordWrap(True)
        layout.addWidget(desc)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event):
        self._set_lifted(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_lifted(False)
        super().leaveEvent(event)

    def _set_lifted(self, lifted):
        """Hover = the tile's one moment of elevation (DESIGN.md §13's
        reserved usage). The effect object is created once and toggled,
        not added/removed per hover -- repeatedly calling
        setGraphicsEffect(None)/setGraphicsEffect(effect) churns Qt's
        backing store for the whole tile subtree on every mouse move
        across the grid.
        """
        effect = self.graphicsEffect()
        if effect is None and lifted:
            effect = QGraphicsDropShadowEffect(blurRadius=12, xOffset=0, yOffset=3)
            effect.setColor(QColor(26, 29, 35, 26))  # ink at ~10%
            self.setGraphicsEffect(effect)
        elif effect is not None:
            effect.setEnabled(lifted)


class HomePage(QWidget):
    """Landing page: greeting header + a tile grid over every registered
    tool. ``toolRequested`` is wired to ``MainWindow.select_tool`` by
    MainWindow itself -- see this module's docstring for why the page
    never looks at the shell.
    """
    toolRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        greeting = QLabel('语言工具箱')
        greeting.setObjectName('pageTitle')
        tagline = QLabel('选择一个工具开始工作')
        tagline.setObjectName('pageSubtitle')
        root.addWidget(greeting)
        root.addWidget(tagline)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)

        specs = [spec for spec in registry.discover() if spec.id != 'home']
        specs.sort(key=lambda s: s.order)  # same order the sidebar uses
        for i, spec in enumerate(specs):
            tile = _ToolTile(spec)
            tile.clicked.connect(lambda id_=spec.id: self.toolRequested.emit(id_))
            grid.addWidget(tile, i // _TILE_COLUMNS, i % _TILE_COLUMNS)
        # Equal-width tiles, left-packed: every used column stretches the
        # same, and a zero-width spacer column absorbs whatever width is
        # left over, so a partially-filled last row leaves a gap on the
        # right instead of stretching its couple of tiles across the page.
        if specs:
            last_used_col = (len(specs) - 1) % _TILE_COLUMNS
            for col in range(last_used_col + 1):
                grid.setColumnStretch(col, 1)
            grid.setColumnStretch(_TILE_COLUMNS, 0)

        root.addWidget(grid_host)
        root.addStretch(1)
