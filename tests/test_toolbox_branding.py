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
