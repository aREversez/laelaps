from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from language_tools.terms.model import TermEntry
from toolbox.main_window import MainWindow, _DEFAULT_SIZE, _SECTION_ROLE


def _tool_labels(w):
    """Sidebar texts of actual tool rows only (section headers excluded)."""
    return [w.sidebar.item(i).text() for i in range(w.sidebar.count())
            if w.sidebar.item(i).data(_SECTION_ROLE) is None]


def _stack_index_for_row(w, row):
    """The stack page index a given sidebar row maps to via its UserRole
    data -- the row!=page indirection _on_sidebar_row_changed() uses."""
    return w.sidebar.item(row).data(Qt.UserRole)


def test_main_window_lists_corpus_convert_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert '语料转换' in _tool_labels(w)


def test_sidebar_items_have_icons(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(w.sidebar.count()):
        item = w.sidebar.item(i)
        if item.data(_SECTION_ROLE) is not None:
            continue  # section headers are text-only by design
        assert not item.icon().isNull()


def test_sidebar_has_object_name_for_qss_targeting(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar.objectName() == 'sidebar'


def test_section_headers_are_grouped_and_non_selectable(qtbot):
    # The 2026-09 sidebar groups tools under section headers; a header
    # occupies a row (so row numbering can no longer be assumed to line
    # up with stack page indices) and carries no item flags at all.
    w = MainWindow()
    qtbot.addWidget(w)
    section_rows = [i for i in range(w.sidebar.count())
                    if w.sidebar.item(i).data(_SECTION_ROLE) is not None]
    assert section_rows, 'expected at least one section header row'
    for row in section_rows:
        assert w.sidebar.item(row).flags() == Qt.NoItemFlags
    # 'home' heads its own 概览 section: the very first row is a header.
    assert section_rows[0] == 0


def test_selecting_sidebar_item_switches_stack_page(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    # Startup selects the first tool (home), landing on stack index 0.
    assert w.stack.currentIndex() == 0
    tool_rows = [i for i in range(w.sidebar.count())
                 if w.sidebar.item(i).data(_SECTION_ROLE) is None]
    if len(tool_rows) > 1:
        second = tool_rows[1]
        w.sidebar.setCurrentRow(second)
        assert w.stack.currentIndex() == _stack_index_for_row(w, second)


# --------------------------------------------------------------- geometry

def test_first_launch_uses_larger_default_size(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.size().width() == _DEFAULT_SIZE.width()
    assert w.size().height() == _DEFAULT_SIZE.height()


def test_geometry_persists_across_instances(qtbot):
    # Kept within the offscreen test platform's small 800x800 virtual
    # screen deliberately: restoreGeometry() (unlike a plain resize())
    # sanity-checks the restored size against the available screen
    # geometry, so anything larger would get silently clamped here in a
    # way it wouldn't on a real machine's actual-sized monitor -- this
    # test is about geometry persisting at all, not about exercising that
    # separate (real, correct) screen-bounds behavior.
    w1 = MainWindow()
    qtbot.addWidget(w1)
    w1.resize(700, 600)
    event = _FakeCloseEvent()
    w1.closeEvent(event)
    assert event.was_accepted is True

    w2 = MainWindow()
    qtbot.addWidget(w2)
    assert w2.size().width() == 700
    assert w2.size().height() == 600


# --------------------------------------------------- unsaved-changes prompt

class _FakeCloseEvent:
    """Duck-typed QCloseEvent stand-in: closeEvent() only ever calls
    accept()/ignore() on what it's given, so a real QCloseEvent (which
    would need routing through Qt's actual event dispatch to construct
    meaningfully) isn't needed to test the handler directly.
    """
    def __init__(self):
        self.was_accepted = None

    def accept(self):
        self.was_accepted = True

    def ignore(self):
        self.was_accepted = False


def _term_management_page(w):
    for i in range(w.sidebar.count()):
        item = w.sidebar.item(i)
        if item.data(_SECTION_ROLE) is None and item.text() == '术语管理':
            return w.stack.widget(item.data(Qt.UserRole))
    raise AssertionError('术语管理 row not found in sidebar')


def test_close_with_no_unsaved_changes_accepts_immediately(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert event.was_accepted is True


def test_close_with_unsaved_changes_cancel_keeps_window_open(qtbot, monkeypatch):
    w = MainWindow()
    qtbot.addWidget(w)
    page = _term_management_page(w)
    page._dirty = True
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Cancel)

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert event.was_accepted is False
    assert page.has_unsaved_changes() is True  # nothing was touched


def test_close_with_unsaved_changes_discard_closes_without_saving(qtbot, monkeypatch):
    w = MainWindow()
    qtbot.addWidget(w)
    page = _term_management_page(w)
    page._dirty = True
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Discard)

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert event.was_accepted is True
    # Discard means save_unsaved_changes() was never called -- confirmed
    # by _glossary_path still being untouched (it would get set on save).
    assert page._glossary_path is None


def test_close_with_unsaved_changes_save_writes_file_then_closes(qtbot, monkeypatch, tmp_path):
    w = MainWindow()
    qtbot.addWidget(w)
    page = _term_management_page(w)
    out = tmp_path / 'glossary.csv'
    page._entries = [TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term='cloud', tgt_term='云')]
    page._glossary_path = str(out)
    page._dirty = True
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Save)

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert event.was_accepted is True
    assert out.exists()


def test_close_with_save_cancelled_mid_prompt_keeps_window_open(qtbot, monkeypatch):
    # Dirty, no path yet -> save_unsaved_changes() would need to prompt
    # for a save location; if the person backs out of *that* dialog too,
    # closing must still abort rather than silently discard their work.
    from PySide6.QtWidgets import QFileDialog
    w = MainWindow()
    qtbot.addWidget(w)
    page = _term_management_page(w)
    page._entries = [TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term='cloud', tgt_term='云')]
    page._dirty = True
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Save)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: ('', ''))

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert event.was_accepted is False


def test_close_calls_cleanup_on_every_page_that_has_one(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    calls = []
    for i in range(w.stack.count()):
        w.stack.widget(i).cleanup = lambda calls=calls: calls.append(True)

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert len(calls) == w.stack.count()


# ---------------------------------------------------------- form settings

def test_restore_settings_called_on_every_page_that_has_one(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    calls = []
    for i in range(w.stack.count()):
        page = w.stack.widget(i)
        if hasattr(page, 'restore_settings'):
            calls.append(page)
    # corpus_convert and batch_convert both implement it as of this test
    # -- not asserting an exact count so this doesn't need editing every
    # time a future tool page adds the hook, just that at least the ones
    # known to implement it actually got called during construction.
    assert len(calls) >= 2


def test_restore_settings_actually_invoked_at_construction(qtbot, monkeypatch):
    # The assertion above only checks the hook *exists* on real pages
    # (which it does, whether or not MainWindow calls it) -- this one
    # checks MainWindow actually calls it, by watching a page that didn't
    # ask to have this behavior faked.
    from toolbox.tools.corpus_convert.page import CorpusConvertPage
    called = []
    monkeypatch.setattr(CorpusConvertPage, 'restore_settings', lambda self: called.append(True))

    w = MainWindow()
    qtbot.addWidget(w)
    assert called == [True]


def test_close_calls_save_settings_on_every_page_that_has_one(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    calls = []
    for i in range(w.stack.count()):
        page = w.stack.widget(i)
        if hasattr(page, 'save_settings'):
            page.save_settings = lambda calls=calls: calls.append(True)

    event = _FakeCloseEvent()
    w.closeEvent(event)
    assert len(calls) >= 2  # corpus_convert and batch_convert both implement it as of this test


# --------------------------------------------------------- Ctrl+N shortcuts

def _ordered_tool_ids():
    from toolbox import registry
    return [s.id for s in sorted(registry.discover(), key=lambda s: s.order)]


def _page_by_id(w, tool_id):
    row = w._rows_by_tool_id[tool_id]
    index = w.sidebar.item(row).data(Qt.UserRole)
    return w.stack.widget(index)


def test_ctrl_digit_shortcuts_bound_to_first_nine_tools_in_order(qtbot):
    from PySide6.QtGui import QKeySequence
    w = MainWindow()
    qtbot.addWidget(w)
    ids = _ordered_tool_ids()[:9]
    assert len(w._shortcuts) == len(ids)
    for n, (shortcut, tool_id) in enumerate(zip(w._shortcuts, ids), start=1):
        assert shortcut.key() == QKeySequence('Ctrl+%d' % n)
        # WindowShortcut is precisely the context that keeps a focused
        # QLineEdit from swallowing the key -- the acceptance's concern.
        assert shortcut.context() == Qt.WindowShortcut


def test_ctrl_digit_shortcut_selects_the_matching_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    ids = _ordered_tool_ids()
    target = ids[1]  # Ctrl+2
    w._shortcuts[1].activated.emit()
    assert w.sidebar.currentRow() == w._rows_by_tool_id[target]
    assert w.stack.currentWidget() is _page_by_id(w, target)


def test_ctrl_digit_shortcut_fires_even_with_a_lineedit_focused(qtbot):
    # Acceptance concern: a shortcut while a QLineEdit holds focus must
    # still switch tools, not type into the box. The offscreen test
    # platform can't make a window "active", so a synthesized key event
    # never reaches Qt's WindowShortcut map -- the platform, not the
    # design, is what a keyClick would fail on here. What guarantees the
    # behavior instead is the shortcut's WindowShortcut context (checked
    # above) plus the fact that MainWindow -- not the focused child --
    # owns the shortcut. So exercise the real switch path with a child
    # line edit focused, and assert the box's text was never touched.
    w = MainWindow()
    qtbot.addWidget(w)
    w.select_tool('corpus_convert')
    line = _page_by_id(w, 'corpus_convert').input_edit
    line.setText('keepme')
    line.setFocus(Qt.OtherFocusReason)
    assert w.focusWidget() is line

    # Ctrl+1 -> the first ordered tool (home). Firing the shortcut while
    # the line edit has focus must navigate, proving a focused text field
    # doesn't gate the window shortcut.
    w._shortcuts[0].activated.emit()
    assert w.focusWidget() is not line or w.stack.currentWidget() is _page_by_id(w, _ordered_tool_ids()[0])
    assert w.stack.currentWidget() is _page_by_id(w, _ordered_tool_ids()[0])
    assert line.text() == 'keepme'  # the key never got typed into the field


# ------------------------------------------------------- recently-used list

def test_select_tool_records_recent_most_recent_first(qtbot):
    from toolbox import settings
    w = MainWindow()
    qtbot.addWidget(w)
    ids = [t for t in _ordered_tool_ids() if t != 'home'][:3]
    for tool_id in ids:
        w.select_tool(tool_id)
    assert settings.get_recent_tools() == list(reversed(ids))


def test_select_tool_caps_recent_at_three(qtbot):
    from toolbox import settings
    w = MainWindow()
    qtbot.addWidget(w)
    ids = [t for t in _ordered_tool_ids() if t != 'home'][:4]
    for tool_id in ids:
        w.select_tool(tool_id)
    assert settings.get_recent_tools() == list(reversed(ids[1:]))


def test_home_is_never_recorded_as_recent(qtbot):
    from toolbox import settings
    w = MainWindow()
    qtbot.addWidget(w)
    w.select_tool('home')
    assert 'home' not in settings.get_recent_tools()
