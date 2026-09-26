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

Same soft-convention treatment for persisted form settings (语言/排版/
输出格式 and the like -- see ``toolbox/settings.py``): a page can
implement ``restore_settings()`` (called once, right after this window
creates it, before it's ever shown) and ``save_settings()`` (called here
in ``closeEvent()``, alongside ``cleanup()``). Neither is required --
a page with no such state to remember just doesn't define them, same as
today's ``cleanup()``.

Sidebar layout (2026-09 UI modernization round): tools group under
section headers by ``ToolSpec.group`` (first-seen order, ungrouped specs
land under 其它), and rows carry their stack index in ``Qt.UserRole`` --
section-header items are rows too, so ``currentRowChanged``'s row number
is no longer the page index and nothing may assume the two line up.
The home page (itself just a registered tool) asks to be navigated to
another tool via a ``toolRequested(id)`` signal, soft-convention'd the
same way as the hooks above and connected here to ``select_tool()`` --
still no hardcoded knowledge of any specific tool, ``select_tool()``
looks ids up in the same registry the sidebar was built from.
"""
import os

from PySide6.QtCore import QSettings, QSize, Qt, QRect
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QStackedWidget, QStyledItemDelegate, QVBoxLayout, QWidget,
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

# The app's brand name. Shown in the sidebar header (constant) and used as
# the window title only while the home page is up; every other tool swaps
# the title bar to its own name (see _on_sidebar_row_changed) so the native
# title bar stops duplicating the sidebar's "语言工具箱".
_APP_TITLE = '语言工具箱'

# Data roles on sidebar QListWidgetItems: a section header carries
# _SECTION_ROLE (marks it non-selectable, value unused); a tool row
# carries its index into self.stack under Qt.UserRole, which is what
# currentRowChanged maps through -- rows and pages no longer share
# numbering once section headers take up rows.
_SECTION_ROLE = Qt.UserRole + 1

# QSS design-token mirrors (toolbox/resources/style.qss header is the
# source of truth; these exist because painting section headers is
# delegate work QSS's ::item selectors can't reach -- an item is not a
# QWidget, property selectors like [role="section"] silently do nothing).
_SLATE = '#6B7280'
_HAIRLINE = '#E3E6EB'
_SIDEBAR_SURFACE = '#FFFFFF'


class _SidebarDelegate(QStyledItemDelegate):
    """Sidebar rows, two kinds: a section header (marked by
    _SECTION_ROLE data on its item) paints as a small slate label with
    breathing room above and a hairline underline; everything else is
    the stock item rendering the QSS ::item rules already style."""

    def paint(self, painter, option, index):
        item = None
        if isinstance(option.widget, QListWidget):
            item = option.widget.item(index.row())
        if item is None or item.data(_SECTION_ROLE) is None:
            super().paint(painter, option, index)
            return
        painter.save()
        # Opaque sidebar-surface fill first: whatever hover/selection
        # chrome the view painted underneath must not bleed through a
        # section row (NoFlag keeps this row out of both states, but the
        # delegate is also the only place that knows it's a header).
        painter.fillRect(option.rect, QColor(_SIDEBAR_SURFACE))
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(_SLATE))
        text_rect = QRect(option.rect.left() + 12, option.rect.top() + 10,
                          option.rect.width() - 24, option.rect.height() - 14)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, item.text())
        painter.setPen(QColor(_HAIRLINE))
        painter.drawLine(option.rect.left() + 12, option.rect.bottom() - 3,
                         option.rect.right() - 12, option.rect.bottom() - 3)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        widget = option.widget
        if isinstance(widget, QListWidget):
            item = widget.item(index.row())
            if item is not None and item.data(_SECTION_ROLE) is not None:
                return QSize(base.width(), 34)
        return base


def _app_version():
    """Version string for the sidebar footer: importlib.metadata reads
    whatever the installed/editable laelaps distribution declares; a
    plain source checkout (no dist-info) falls back to pyproject's
    current value rather than showing nothing.
    """
    try:
        from importlib.metadata import version
        return version('laelaps')
    except Exception:  # noqa: BLE001 -- any metadata miss just means "unknown"
        return '0.1.0'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_APP_TITLE)

        sidebar_panel = self._build_sidebar_panel()
        self.stack = QStackedWidget()
        self._rows_by_tool_id = {}
        self._titles_by_index = {}

        tools = sorted(registry.discover(), key=lambda s: s.order)
        if not tools:
            self.stack.addWidget(self._empty_state())
        last_group = None
        for spec in tools:
            group = spec.group or '其它'
            if group != last_group:
                self._add_sidebar_section(group)
                last_group = group
            item = QListWidgetItem(spec.name)
            if spec.icon and os.path.exists(spec.icon):
                item.setIcon(QIcon(spec.icon))
            item.setToolTip(spec.description)
            page = spec.page_factory()
            restore_settings = getattr(page, 'restore_settings', None)
            if restore_settings:
                restore_settings()
            stack_index = self.stack.count()
            item.setData(Qt.UserRole, stack_index)
            # Home keeps the brand name in the title bar; every other tool
            # swaps it to the tool's own name (see _on_sidebar_row_changed).
            self._titles_by_index[stack_index] = (
                _APP_TITLE if spec.id == 'home' else spec.name)
            self._rows_by_tool_id[spec.id] = self.sidebar.count()
            self.sidebar.addItem(item)
            self.stack.addWidget(page)
            # Soft convention, same style as has_unsaved_changes(): a page
            # that wants shell-level navigation (today: only the home
            # page's tiles) declares toolRequested; nobody else pays for it.
            tool_requested = getattr(page, 'toolRequested', None)
            if tool_requested:
                tool_requested.connect(self.select_tool)

        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        if tools:
            # Row 0 is now the first section *header* (non-selectable), so
            # the default selection must be the first actual tool row --
            # self.select_tool on the first discovered spec resolves that
            # row through the same id map everything else uses rather than
            # assuming row 0 is selectable.
            self.select_tool(tools[0].id)

        central = QWidget()
        # The app's paper background is painted HERE, on the plain central
        # widget, not on QMainWindow: with the global `QWidget {
        # background: transparent }` rule, a stylesheet background on
        # QMainWindow does not reach its central area on Windows, so every
        # transparent descendant (stack, page) had nothing to show through
        # to and rendered black. A plain QWidget honours its QSS background
        # reliably, so paper lives here; the white card / sidebar / tab pane
        # sit on top of it and their transparent children show white.
        central.setObjectName('centralWidget')
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

    def select_tool(self, tool_id):
        """Switch to a tool by registry id -- the shell still resolves it
        through the discovered specs (sidebar row map), never through
        per-tool code. Unknown ids are ignored rather than raising: this
        is wired to a signal, and a stale tile click must not take the
        window down.
        """
        row = self._rows_by_tool_id.get(tool_id)
        if row is not None:
            self.sidebar.setCurrentRow(row)

    def _on_sidebar_row_changed(self, row):
        item = self.sidebar.item(row)
        if item is None or item.data(_SECTION_ROLE) is not None:
            return  # a section header got selected by keyboard nav -- skip
        index = item.data(Qt.UserRole)
        self.stack.setCurrentIndex(index)
        # Title bar tracks the active tool (home maps back to the brand
        # name), so it no longer duplicates the sidebar header's fixed
        # "语言工具箱" -- and Alt-Tab / the taskbar gain real context.
        self.setWindowTitle(self._titles_by_index.get(index, _APP_TITLE))

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
            save_settings = getattr(page, 'save_settings', None)
            if save_settings:
                save_settings()
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
        panel.setObjectName('sidebarPanel')
        panel.setFixedWidth(216)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 18, 14, 14)
        header_layout.setSpacing(9)

        logo_label = QLabel()
        logo_path = os.path.join(RESOURCES_DIR, 'logo.svg')
        if os.path.exists(logo_path):
            logo_label.setPixmap(QPixmap(logo_path).scaled(
                28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_label = QLabel(_APP_TITLE)
        title_label.setObjectName('sidebarHeaderTitle')
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        layout.addWidget(header)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setFrameShape(QListWidget.NoFrame)
        self.sidebar.setItemDelegate(_SidebarDelegate(self.sidebar))
        layout.addWidget(self.sidebar, 1)

        version_label = QLabel('v' + _app_version())
        version_label.setObjectName('sidebarVersion')
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 8, 14, 12)
        footer_layout.addWidget(version_label)
        footer_layout.addStretch(1)
        layout.addWidget(footer)
        return panel

    def _add_sidebar_section(self, title):
        """A non-selectable section header row above the tools sharing a
        group. _SECTION_ROLE data drives both the delegate's custom
        paint and _on_sidebar_row_changed()'s skip -- keyboard nav can
        still land on the row despite Qt.NoItemFlags, so the guard can't
        rely on the flags alone.
        """
        item = QListWidgetItem(title)
        item.setData(_SECTION_ROLE, True)
        item.setFlags(Qt.NoItemFlags)
        self.sidebar.addItem(item)

    def _empty_state(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        label = QLabel('没有已注册的工具')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return w
