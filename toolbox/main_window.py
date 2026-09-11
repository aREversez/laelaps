"""Main window: a branded sidebar (logo + tool list) + a stacked widget
showing the selected tool's page. Never needs to change when a new tool
is added -- it just iterates ``registry.discover()``.

Unsaved-changes-on-close and window-geometry persistence are both handled
here, in ``closeEvent()``, rather than in each tool page, since only this
window's own close is the event that matters for either -- switching
sidebar tools doesn't lose anything (``QStackedWidget`` keeps every page
alive, just hidden) or need the window's size remembered again.

Any tool page can opt into the unsaved-changes prompt by implementing
``has_unsaved_changes()`` (-> bool), ``unsaved_changes_label()`` (-> str,
shown in the prompt), and ``save_unsaved_changes()`` (-> bool, True if
it's now safe to close). This is a soft convention checked with
``getattr(page, name, None)``, not an ABC/Protocol every page must
implement -- most tool pages have nothing to lose on close (they only
ever write a file when the person explicitly clicks convert/export, never
hold in-memory state the person would expect to survive), so forcing an
interface on all of them for one page's (``term_management``'s) actual
need would be the wrong amount of coupling. A page can also implement
``cleanup()`` (no return value) for any last-moment teardown that should
happen on a real close regardless of the save outcome (``term_management``
uses this to release its glossary file lock -- see that page's module
docstring).
"""
import os

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from toolbox import registry
from toolbox.paths import RESOURCES_DIR

# Bigger than Qt's/this window's old fixed 960x660 default: the first
# thing a person sees on first launch should show a full results table
# (e.g. term_management's 一致性检查 tab) more than a couple of rows tall,
# not require an immediate manual resize before the app is usable.
# Only used the very first time the app runs on a given machine --
# _restore_geometry() below remembers whatever the person resizes to
# after that, same as any desktop app.
_DEFAULT_SIZE = QSize(1280, 860)
_GEOMETRY_KEY = 'mainWindow/geometry'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('语言工具箱')

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

        self._restore_geometry()

    def _restore_geometry(self):
        geometry = QSettings().value(_GEOMETRY_KEY)
        if geometry is not None and self.restoreGeometry(geometry):
            return
        self.resize(_DEFAULT_SIZE)

    def _pages(self):
        return [self.stack.widget(i) for i in range(self.stack.count())]

    def closeEvent(self, event):
        dirty_pages = [p for p in self._pages()
                        if getattr(p, 'has_unsaved_changes', lambda: False)()]
        if dirty_pages:
            choice = self._prompt_unsaved_changes(dirty_pages)
            if choice == QMessageBox.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.Save:
                for page in dirty_pages:
                    if not page.save_unsaved_changes():
                        # Save failed or the person backed out of a
                        # save-location prompt mid-close -- stay open
                        # rather than lose their work silently.
                        event.ignore()
                        return

        QSettings().setValue(_GEOMETRY_KEY, self.saveGeometry())
        for page in self._pages():
            cleanup = getattr(page, 'cleanup', None)
            if cleanup:
                cleanup()
        event.accept()

    def _prompt_unsaved_changes(self, dirty_pages):
        names = '、'.join(
            getattr(p, 'unsaved_changes_label', lambda: '未命名')() for p in dirty_pages)
        box = QMessageBox(self)
        box.setWindowTitle('有未保存的更改')
        box.setText('%s 有未保存的更改，要保存吗？' % names)
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        return box.exec()

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
