"""Main window: a sidebar tool list + a stacked widget showing the
selected tool's page. Never needs to change when a new tool is added --
it just iterates ``registry.discover()``.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from toolbox import registry


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('语言工具箱')
        self.resize(900, 640)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.stack = QStackedWidget()

        tools = registry.discover()
        if not tools:
            self.stack.addWidget(self._empty_state())
        for spec in tools:
            item = QListWidgetItem(spec.name)
            item.setToolTip(spec.description)
            self.sidebar.addItem(item)
            self.stack.addWidget(spec.page_factory())

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        if tools:
            self.sidebar.setCurrentRow(0)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.sidebar)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _empty_state(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        label = QLabel('没有已注册的工具')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return w
