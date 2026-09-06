"""Entry point for the desktop toolbox app: ``python -m toolbox.main``."""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from toolbox import tooltips
from toolbox.main_window import MainWindow
from toolbox.paths import RESOURCES_DIR


def _load_stylesheet():
    path = os.path.join(RESOURCES_DIR, 'style.qss')
    with open(path, encoding='utf-8') as f:
        content = f.read()
    # QSS url() needs a real filesystem path, not one relative to an
    # unpredictable CWD -- substitute in the actual resources dir (already
    # resolved correctly for both source and frozen builds by paths.py).
    # Forward slashes: Qt's QSS parser accepts them on every platform,
    # including Windows, so no os.sep juggling needed here.
    icons_dir = os.path.join(RESOURCES_DIR, 'icons').replace(os.sep, '/')
    return content.replace('{ICONS_DIR}', icons_dir)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(_load_stylesheet())
    app.setWindowIcon(QIcon(os.path.join(RESOURCES_DIR, 'logo.svg')))
    tooltips.install(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
