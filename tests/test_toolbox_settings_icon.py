import os
import re

from PySide6.QtSvg import QSvgRenderer

from toolbox.widgets import _GLYPH_INDIGO, _GLYPH_SLATE, tinted_icon_pixmap

RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'toolbox', 'resources')


def test_settings_icon_is_a_gear_in_the_shared_glyph_color(qtbot):
    """The settings glyph used to be a sun (read as a theme switch). Pin the
    gear: a valid SVG whose only stroke color is the slate that
    tinted_icon_pixmap() swaps for the accent indigo, and which really tints."""
    path = os.path.join(RESOURCES_DIR, 'icons', 'settings.svg')
    assert QSvgRenderer(path).isValid()
    with open(path, encoding='utf-8') as f:
        svg = f.read()
    assert set(re.findall(r'stroke="(#[0-9A-Fa-f]{6})"', svg)) == {_GLYPH_SLATE}
    # a gear outline is one closed path with many teeth, not eight loose rays
    assert svg.count('<path') == 1 and svg.count('L') >= 16
    pm = tinted_icon_pixmap(path, 32).toImage()
    colors = {pm.pixelColor(x, y).name() for x in range(32) for y in range(32)
              if pm.pixelColor(x, y).alpha() == 255}
    assert _GLYPH_INDIGO.lower() in colors
