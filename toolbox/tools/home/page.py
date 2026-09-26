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
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from toolbox import registry
from toolbox.widgets import tinted_icon_pixmap

# Responsive tile grid: up to 3 columns on a wide window, dropping to 2/1 as
# the window narrows so tiles keep a readable width and are never clipped on
# the right -- HomePage._reflow recomputes the column count on every resize
# (reflow, not a horizontal scrollbar, is the intended narrow-window behaviour).
_MAX_TILE_COLUMNS = 3
# A tile narrower than this is too cramped to read its wrapped description,
# so a column is dropped before tiles get squeezed below it.
_TILE_MIN_WIDTH = 200

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
        # Horizontal Expanding (fill the grid column), vertical Minimum: the
        # tile grows to whatever height its word-wrapped description needs at
        # the current width. A Fixed vertical height locked the tile to its
        # initial one/two-line hint, so narrowing the window made the
        # description overflow past the bottom border into the row below.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

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
        # Preferred/Minimum so the label drives the tile's height-for-width:
        # the layout asks heightForWidth() at the tile's actual width and the
        # tile grows to fit every wrapped line instead of clipping.
        desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
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

        self._grid_host = QWidget()
        # Maximum (not Preferred) vertically: inside a widgetResizable scroll
        # area this keeps the grid at its natural height instead of stretching
        # rows to fill the viewport (which left tall gaps inside every tile).
        # The scroll area only kicks in when the natural height already exceeds
        # the viewport (narrow window -> taller wrapped tiles).
        self._grid_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        # Roomier vertical gap than horizontal, so rows read as a calm grid
        # rather than tiles pressed against each other.
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(24)

        specs = [spec for spec in registry.discover() if spec.id != 'home']
        specs.sort(key=lambda s: s.order)  # same order the sidebar uses
        self._tiles = []
        for spec in specs:
            tile = _ToolTile(spec)
            tile.clicked.connect(lambda id_=spec.id: self.toolRequested.emit(id_))
            self._tiles.append(tile)

        self._grid_scroll = QScrollArea()
        self._grid_scroll.setObjectName('homeScroll')
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setFrameShape(QFrame.NoFrame)
        # No horizontal scrollbar by design: as the window narrows the grid
        # reflows to fewer columns (see _reflow) so tiles keep a readable width
        # and are never clipped on the right -- reflow, not a scroll bar.
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_scroll.setWidget(self._grid_host)
        # Watch the scroll area's own resizes (not HomePage's): its width is
        # stable against the vertical scrollbar toggling, which keeps _reflow
        # from feeding a resize -> column -> height -> scrollbar -> resize loop.
        self._grid_scroll.installEventFilter(self)

        # Debounced reflow: rebuilding the grid (moving every tile + resetting
        # column stretches) on *every* Resize event thrashes the layout for the
        # whole duration of an interactive drag, and Qt/Windows paints
        # inconsistent ghost frames mid-drag (the sidebar region not yet
        # repainted, a stale column count). Restarting a short single-shot timer
        # on each resize means the grid is rebuilt once, just after the drag
        # settles, instead of continuously during it.
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.setInterval(70)
        self._reflow_timer.timeout.connect(self._reflow)

        root.addWidget(self._grid_scroll, 1)

        self._cols = 0  # 0 = nothing placed yet; first _reflow lays out
        self._reflow()

    def eventFilter(self, obj, event):
        if obj is self._grid_scroll and event.type() == QEvent.Resize:
            self._reflow_timer.start()
        return super().eventFilter(obj, event)

    def _columns_for(self, avail_width):
        """Widest column count (up to ``_MAX_TILE_COLUMNS``) that still leaves
        every tile at least ``_TILE_MIN_WIDTH``; drop a column before tiles get
        squeezed past readable rather than clipping the rightmost one.
        """
        gap = self._grid.horizontalSpacing()
        for cols in range(_MAX_TILE_COLUMNS, 1, -1):
            needed = cols * _TILE_MIN_WIDTH + (cols - 1) * gap
            if avail_width >= needed:
                return cols
        return 1

    def _reflow(self):
        """Re-place the tiles for the current width. A no-op unless the column
        count actually changes, so dragging the window edge only rebuilds the
        grid at the 3 -> 2 -> 1 thresholds.
        """
        # Read the scroll area's width (viewport + any vertical scrollbar),
        # reserving a scrollbar's worth so a column is dropped just before the
        # bar would appear. This width doesn't move when the scrollbar toggles,
        # which is what keeps the reflow stable.
        avail = self._grid_scroll.width() - 16
        cols = self._columns_for(avail)
        if cols == self._cols:
            return
        self._cols = cols
        for i, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, i // cols, i % cols)
        # Equal-width tiles, left-packed: every column in the current layout
        # (0..cols-1) stretches the same, columns beyond that stay 0. A
        # partially-filled last row falls out of this for free -- its unused
        # columns still carry stretch (nothing else uses them either, this
        # being the last row), so they just hold blank space on the right
        # instead of a tile stretching across it. This must NOT be scoped to
        # "however many columns the last row happens to fill": a QGridLayout
        # column's width is shared by every row, so giving only the last
        # row's used columns any stretch starves that same column's tiles in
        # every *earlier*, fully-packed row too -- verified: with 9 tiles at
        # cols=2 (a 4-full-rows + 1 lone last row shape), scoping stretch to
        # the last row's single column left column 0 at 190px and column 1 at
        # 280px, visibly uneven, in rows that both had a tile.
        for c in range(_MAX_TILE_COLUMNS + 1):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)
