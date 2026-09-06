"""Main window: a branded sidebar (logo + tool list) + a stacked widget
showing the selected tool's page. Never needs to change when a new tool
is added -- it just iterates ``registry.discover()``.
"""
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from toolbox import registry
from toolbox.paths import RESOURCES_DIR


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('语言工具箱')
        self.resize(960, 660)

        sidebar_panel = self._build_sidebar_panel()
        self.stack = QStackedWidget()

        tools = registry.discover()
        if not tools:
            self.stack.addWidget(self._empty_state())
        for spec in tools:
            item = QListWidgetItem(spec.name)
            if spec.icon and os.path.exists(spec.icon):
                item.setIcon(QIcon(spec.icon))
            item.setToolTip(spec.description)
            self.sidebar.addItem(item)
            self.stack.addWidget(spec.page_factory())

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        if tools:
            self.sidebar.setCurrentRow(0)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(sidebar_panel)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _build_sidebar_panel(self):
        panel = QWidget()
        panel.setFixedWidth(200)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 16, 14, 12)
        header_layout.setSpacing(8)

        logo_label = QLabel()
        logo_path = os.path.join(RESOURCES_DIR, 'logo.svg')
        if os.path.exists(logo_path):
            logo_label.setPixmap(QPixmap(logo_path).scaled(
                24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_label = QLabel('语言工具箱')
        title_label.setObjectName('sidebarHeaderTitle')
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        layout.addWidget(header)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setFrameShape(QListWidget.NoFrame)
        layout.addWidget(self.sidebar, 1)
        return panel

    def _empty_state(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        label = QLabel('没有已注册的工具')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return w
