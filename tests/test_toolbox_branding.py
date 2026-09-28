import os

from PySide6.QtGui import QIcon
from PySide6.QtSvg import QSvgRenderer

RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'toolbox', 'resources')


def test_logo_svg_is_valid(qtbot):
    path = os.path.join(RESOURCES_DIR, 'logo.svg')
    assert os.path.exists(path)
    renderer = QSvgRenderer(path)
    assert renderer.isValid()


def test_corpus_convert_icon_is_valid(qtbot):
    path = os.path.join(RESOURCES_DIR, 'icons', 'corpus_convert.svg')
    assert os.path.exists(path)
    renderer = QSvgRenderer(path)
    assert renderer.isValid()


def test_app_ico_exists_for_windows_packaging(qtbot):
    path = os.path.join(RESOURCES_DIR, 'icons', 'app.ico')
    assert os.path.exists(path)
    icon = QIcon(path)
    assert not icon.isNull()


def test_stylesheet_loads_and_is_non_trivial():
    path = os.path.join(RESOURCES_DIR, 'style.qss')
    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    assert 'QPushButton#primaryButton' in content
    assert '#2E4374' in content  # the accent color, defined once, referenced by name in docs


def test_tab_bar_is_styled_as_its_own_rounded_box():
    # QTabBar itself needs a background + border + radius of its own
    # (the segmented-control look) -- not just QTabBar::tab:selected --
    # or an unselected tab has no box at all and the whole row reads as
    # loosely connected to the pane below rather than one grouped control.
    path = os.path.join(RESOURCES_DIR, 'style.qss')
    with open(path, encoding='utf-8') as f:
        content = f.read()
    tab_bar_rule = content.split('QTabBar {', 1)[1].split('}', 1)[0]
    assert 'background' in tab_bar_rule
    assert 'border-radius' in tab_bar_rule


def test_main_stylesheet_loader_substitutes_icons_dir_placeholder():
    # style.qss itself contains a literal {ICONS_DIR} placeholder (checked
    # above) -- toolbox.main._load_stylesheet() must resolve it to a real,
    # existing path before the stylesheet reaches QApplication, or the
    # checkbox/combobox icons silently fail to render (no error, just
    # missing images -- confirmed this class of bug is easy to miss without
    # an explicit check, since Qt doesn't warn loudly about a bad url()).
    import re

    import toolbox.main as m

    content = m._load_stylesheet()
    assert '{ICONS_DIR}' not in content
    for path in re.findall(r'url\(([^)]+)\)', content):
        assert os.path.exists(path), 'stylesheet references a missing icon: %s' % path


# --- HiDPI-crisp rendering + selected-state sidebar icons -------------------
# Regressions for: (1) sidebar logo / page-header chip / home tiles being
# rasterized at logical pixel size and then stretched on scaled displays;
# (2) QIcon's generated Selected-mode pixmap blending the palette highlight
# over the opaque white fills of the batch_* / qa_check glyphs.

_WHITE_FILLED_GLYPHS = ('batch_convert', 'batch_alignment_check',
                        'batch_preflight', 'qa_check')


def test_svg_pixmap_is_backed_by_device_pixels(qtbot):
    from toolbox.widgets import svg_pixmap
    path = os.path.join(RESOURCES_DIR, 'logo.svg')
    for dpr, expected in ((1.0, 28), (1.5, 42), (2.0, 56)):
        pm = svg_pixmap(path, 28, dpr)
        assert (pm.width(), pm.height()) == (expected, expected)
        assert pm.devicePixelRatio() == dpr
        assert pm.toImage().pixelColor(expected // 2, expected // 2).alpha() != 0


def test_tinted_icon_pixmap_scales_with_dpr(qtbot):
    from toolbox.widgets import tinted_icon_pixmap
    path = os.path.join(RESOURCES_DIR, 'icons', 'batch_convert.svg')
    pm = tinted_icon_pixmap(path, 34, 2.0)
    assert (pm.width(), pm.height()) == (68, 68)
    assert pm.devicePixelRatio() == 2.0
    # default (no dpr given) must keep working for callers that don't pass one
    assert tinted_icon_pixmap(path, 34).width() >= 34


def test_sidebar_icon_selected_pixels_match_normal(qtbot):
    from PySide6.QtCore import QSize
    from toolbox.widgets import sidebar_icon
    for name in _WHITE_FILLED_GLYPHS:
        icon = sidebar_icon(os.path.join(RESOURCES_DIR, 'icons', name + '.svg'))
        normal = icon.pixmap(QSize(20, 20), QIcon.Normal, QIcon.Off).toImage()
        selected = icon.pixmap(QSize(20, 20), QIcon.Selected, QIcon.Off).toImage()
        assert normal == selected, name


def test_plain_qicon_would_tint_the_white_fill(qtbot):
    """Guards the premise of sidebar_icon(): if Qt ever stops tinting the
    generated Selected pixmap, this fails and the helper can be retired."""
    from PySide6.QtCore import QSize
    path = os.path.join(RESOURCES_DIR, 'icons', 'batch_convert.svg')
    plain = QIcon(path)
    normal = plain.pixmap(QSize(20, 20), QIcon.Normal, QIcon.Off).toImage()
    selected = plain.pixmap(QSize(20, 20), QIcon.Selected, QIcon.Off).toImage()
    assert normal != selected


def test_every_sidebar_row_icon_is_untinted_when_selected(qtbot):
    from PySide6.QtCore import QSize
    from toolbox.main_window import MainWindow, _SECTION_ROLE
    w = MainWindow()
    qtbot.addWidget(w)
    checked = 0
    for i in range(w.sidebar.count()):
        item = w.sidebar.item(i)
        if item.data(_SECTION_ROLE) is not None:
            continue
        icon = item.icon()
        normal = icon.pixmap(QSize(20, 20), QIcon.Normal, QIcon.Off).toImage()
        selected = icon.pixmap(QSize(20, 20), QIcon.Selected, QIcon.Off).toImage()
        assert normal == selected, item.text()
        checked += 1
    assert checked > 0
