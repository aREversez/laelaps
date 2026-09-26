from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from toolbox.main_window import MainWindow
from toolbox.tools.home.page import HomePage


def _tile_names(page):
    """Tool names shown on home tiles, read off the name labels (each tile
    holds exactly one objectName='homeTileName')."""
    return [lbl.text() for lbl in page.findChildren(QLabel)
            if lbl.objectName() == 'homeTileName']


def test_home_page_is_registered_first_tool(qtbot):
    # 'home' must head the sidebar/stack so the app opens on the overview
    # page rather than jumping straight into the first real tool.
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar.item(0).data(Qt.UserRole) is None  # 概览 section header
    home_row = w.sidebar.item(1)
    assert home_row.text() == '首页'
    assert w.stack.widget(home_row.data(Qt.UserRole)) is not None


def test_home_lists_every_other_tool_as_a_tile(qtbot):
    page = HomePage()
    qtbot.addWidget(page)
    names = _tile_names(page)
    # The headline tools each get a tile; home never tiles itself.
    for expected in ('语料转换', 'QA 检查', '术语管理', '条目编辑'):
        assert expected in names
    assert '首页' not in names


def test_tile_click_emits_tool_requested(qtbot):
    # Clicking a tile emits toolRequested(tool_id) -- the only navigation
    # the page knows about; it never reaches into MainWindow itself.
    page = HomePage()
    qtbot.addWidget(page)
    # Find the 语料转换 tile by its name label rather than trusting grid
    # cell coordinates (registry order decides placement).
    tile = next(t for t in page.findChildren(QWidget)
                if t.objectName() == 'homeTile'
                and any(l.objectName() == 'homeTileName' and l.text() == '语料转换'
                        for l in t.findChildren(QLabel)))
    with qtbot.waitSignal(page.toolRequested, timeout=1000) as blocker:
        tile.clicked.emit()
    assert blocker.args == ['corpus_convert']


def test_home_selecting_tile_navigates_main_window(qtbot):
    # End-to-end: MainWindow wires HomePage.toolRequested to select_tool,
    # so emitting the signal actually switches the visible stack page.
    w = MainWindow()
    qtbot.addWidget(w)
    w.sidebar.setCurrentRow(1)  # home is the first tool row (row 0 = 概览 header)
    home_row = w.sidebar.item(1)
    home_page = w.stack.widget(home_row.data(Qt.UserRole))
    assert isinstance(home_page, HomePage)

    home_page.toolRequested.emit('qa_check')
    # qa_check's page is now visible: the sidebar row that maps to the
    # current stack index reads 'QA 检查'.
    current = w.stack.currentIndex()
    for i in range(w.sidebar.count()):
        item = w.sidebar.item(i)
        if item.data(Qt.UserRole) == current:
            assert item.text() == 'QA 检查'
            break
def test_reflow_gives_every_used_column_equal_stretch(qtbot):
    """Regression test: _reflow() must not scope column stretch to however
    many columns the *last* row happens to fill. A QGridLayout column's
    width is shared by every row, so with a tile count that doesn't divide
    evenly by the column count (9 tiles is not a multiple of 2), scoping
    stretch to the last row's lone used column previously starved that same
    column's tiles in the earlier, fully-packed rows -- visibly unequal
    widths even though every column in those rows held a tile."""
    page = HomePage()
    qtbot.addWidget(page)
    assert len(page._tiles) % 2 != 0  # otherwise this case can't reproduce the bug

    # Force the 2-column breakpoint (see _TILE_MIN_WIDTH/_columns_for).
    page._grid_scroll.resize(500, 600)
    page._reflow()
    assert page._cols == 2
    stretches = [page._grid.columnStretch(c) for c in range(page._cols)]
    assert len(set(stretches)) == 1 and stretches[0] > 0

    # Same invariant at the 1-column breakpoint.
    page._grid_scroll.resize(250, 600)
    page._reflow()
    assert page._cols == 1
    assert page._grid.columnStretch(0) > 0

    # And back at 3 columns (the currently-full-dividing case) for good measure.
    page._grid_scroll.resize(900, 600)
    page._reflow()
    assert page._cols == 3
    stretches = [page._grid.columnStretch(c) for c in range(page._cols)]
    assert len(set(stretches)) == 1 and stretches[0] > 0
