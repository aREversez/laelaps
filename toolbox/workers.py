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
