from PySide6.QtWidgets import QMessageBox

from language_tools.terms.model import TermEntry
from toolbox.main_window import MainWindow, _DEFAULT_SIZE


def test_main_window_lists_corpus_convert_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    labels = [w.sidebar.item(i).text() for i in range(w.sidebar.count())]
    assert '语料转换' in labels


def test_sidebar_items_have_icons(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(w.sidebar.count()):
        assert not w.sidebar.item(i).icon().isNull()


def test_sidebar_has_object_name_for_qss_targeting(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar.objectName() == 'sidebar'


def test_selecting_sidebar_item_switches_stack_page(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.stack.currentIndex() == 0
    if w.sidebar.count() > 1:
        w.sidebar.setCurrentRow(1)
        assert w.stack.currentIndex() == 1


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
    labels = [w.sidebar.item(i).text() for i in range(w.sidebar.count())]
    return w.stack.widget(labels.index('术语管理'))


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
