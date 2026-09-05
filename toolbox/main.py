"""Entry point for the desktop toolbox app: ``python -m toolbox.main``."""
import sys

from PySide6.QtWidgets import QApplication

from toolbox.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
