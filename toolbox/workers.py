"""Shared QThread worker for tool pages whose slow operation is just
"call a function, get back a result or an error" -- no specialized
``run()`` body needed.

Originally a private class (``TmWorker``) inside ``tm_maintenance/page.py``,
which explained why it's generic rather than shaped like
``corpus_convert.ConvertWorker`` (specific to ``api.convert()``'s kwargs).
Promoted here once ``qa_check`` needed the identical class rather than a
second copy -- ``ConvertWorker`` stays where it is, unmoved: it's a
different shape (kwargs-driven, not callable-driven) serving one call
site, not a duplicate of this.
"""
from PySide6.QtCore import QThread, Signal


def wait_for_running(*workers):
    """Blocks until every one of ``workers`` that is still running has
    finished; a ``None`` (a worker attribute that was never started, or
    already finished and cleared) is skipped.

    Call this from a tool page's ``cleanup()`` hook (see
    ``main_window.py``'s docstring for that soft convention) with every
    ``QThread`` attribute the page can start. Without it, a window close
    landing while one of them is still running destroys a live ``QThread``
    -- Qt's own "QThread: Destroyed while thread is still running" fatal
    error, not a catchable exception -- because ``MainWindow`` tears down
    every page (and any ``QThread`` parented to it) on close whether or
    not its worker has finished. It only reproduces when the close lands
    mid-run, which is why it shows up as an intermittent crash rather
    than a reliable repro (first found and fixed in ``batch_convert``,
    see that page's ``cleanup()``).

    Blocking here until the worker actually finishes is simpler and safer
    than trying to interrupt it: none of the callables these workers run
    (``api.convert()``, the alignment/QA/TM-maintenance jobs) are written
    to be cancellable, and killing one mid-write risks a half-written
    output file next to the source it came from.
    """
    for worker in workers:
        if worker is not None and worker.isRunning():
            worker.wait()


class CallableWorker(QThread):
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as e:  # noqa: BLE001 -- surfaced to the user, not swallowed
            self.finished_err.emit(str(e))
            return
        self.finished_ok.emit(result)
