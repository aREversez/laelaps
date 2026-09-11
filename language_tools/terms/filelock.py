"""Best-effort file-in-use checks for the term-management GUI.

The real-file lock is intended as best-effort concurrent-edit protection.
Windows uses ``msvcrt.locking``; POSIX uses advisory ``fcntl.flock``.
Office/WPS marker detection is a separate, read-only warning mechanism.

Saving while this process holds the real-file lock requires a short
release/write/reacquire window because Windows can block a second handle
from the same process. ``write_around`` therefore never silently swallows
failure to reacquire the lock: if the write succeeds but the lock cannot
be restored, it raises ``OSError`` so the caller does not report a fully
protected save.
"""
import os


def office_lock_marker_path(path):
    directory, filename = os.path.split(path)
    return os.path.join(directory, '~$%s' % filename)


def office_lock_marker_exists(path):
    """Best-effort, not authoritative -- see module docstring."""
    return os.path.exists(office_lock_marker_path(path))


def _lock_region(fh):
    if os.name == 'nt':
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_region(fh):
    if os.name == 'nt':
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class FileLock:
    """Lock an existing glossary file for best-effort edit protection."""

    def __init__(self, path):
        self.path = path
        self._fh = None

    def acquire(self):
        if self._fh is not None:
            raise OSError('file lock is already held')
        fh = open(self.path, 'r+b')
        try:
            _lock_region(fh)
        except OSError:
            fh.close()
            raise
        self._fh = fh

    def release(self):
        if self._fh is None:
            return
        fh, self._fh = self._fh, None
        try:
            _unlock_region(fh)
        finally:
            fh.close()

    def write_around(self, write_fn):
        """Write ``self.path`` while temporarily releasing this lock.

        The lock is restored in all cases when possible. A write exception
        is propagated unchanged. If the write succeeds but reacquisition
        fails, ``OSError`` is raised because the file is no longer protected
        by this lock instance, even though the new bytes are already on disk.
        """
        if not self.is_held:
            raise OSError('file lock is not held')

        self.release()
        write_error = None
        try:
            write_fn()
        except BaseException as exc:
            write_error = exc
        finally:
            try:
                self.acquire()
            except OSError as reacquire_error:
                if write_error is None:
                    raise OSError(
                        'file was saved, but the file lock could not be reacquired'
                    ) from reacquire_error

        if write_error is not None:
            raise write_error

    @property
    def is_held(self):
        return self._fh is not None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
