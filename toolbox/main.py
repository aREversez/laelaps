"""Entry point for the desktop toolbox app: ``python -m toolbox.main``."""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from toolbox.main_window import MainWindow
from toolbox.paths import RESOURCES_DIR


def _load_stylesheet():
    path = os.path.join(RESOURCES_DIR, 'style.qss')
    with open(path, encoding='utf-8') as f:
        return f.read()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(_load_stylesheet())
    app.setWindowIcon(QIcon(os.path.join(RESOURCES_DIR, 'logo.svg')))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
