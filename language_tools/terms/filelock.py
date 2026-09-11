"""Best-effort "is this glossary file already in use elsewhere" checks for
the term-management GUI page.

Two complementary checks, combined by the page rather than used alone --
see that module's ``_open_glossary()``/``_write_glossary()`` for exactly
how:

1. ``office_lock_marker_exists(path)``: a read-only check for the hidden
   sibling marker file ("~$<filename>") Office/WPS create next to a
   workbook while it's open for editing, and check for before opening one
   themselves -- that's literally how their own "already open by ..."
   warning works: they check the marker's existence, not any particular
   content. This tool never *writes* one of these markers itself: the
   exact content/encoding Office expects is an undocumented
   implementation detail, and writing a malformed one risks confusing
   *their* UI in ways worse than not detecting anything at all here.
   One-directional (tells this tool about Office/WPS, can't tell
   Office/WPS about this tool) and best-effort: a stale marker left
   behind by a crashed Office/WPS session looks identical to a
   genuinely-open file from out here, so a hit should be surfaced as a
   dismissible warning, not treated as a hard block.

2. ``FileLock``: real OS-level locking, held for as long as a glossary is
   open for editing in this tool.

   This went through two earlier designs before this one, each fixed
   after real testing surfaced a concrete problem with it:

   - v1 locked a separate sidecar file (``<path>.lock``) only. Real
     testing showed WPS could open, edit, and save the real glossary file
     with zero conflict -- a sidecar only this tool ever reads isn't
     something WPS/Office can be blocked by or checks against at all.
   - v2 locked the real file directly, but with a single EXCLUSIVE lock
     (``msvcrt.locking()`` on Windows has no shared-lock mode). Real
     testing showed this over-corrected: it blocked *reads* too -- a
     plain text editor opening the csv read-only, or WPS's own
     read-only-open path, both failed, when the actual goal was only
     ever to block *writes* while this tool has the file open.

   This version locks in two different ways at once, because the two
   problems each earlier version was trying to solve need genuinely
   different lock semantics and neither alone covers both:

   - An EXCLUSIVE lock on the sidecar file, same mechanism as v1 --
     this is what detects a second instance of *this tool* trying to
     edit the same glossary. It has to be exclusive: a SHARED lock
     wouldn't conflict with another shared lock, so two instances of
     this tool could both "hold" a shared lock at once and this check
     would never fire.
   - A SHARED lock on the real glossary file. Unlike v2's exclusive
     lock, a shared lock still permits other processes' *reads* of the
     file (multiple shared-lock holders can coexist) while still
     blocking other processes' *writes* (a write needs an exclusive
     lock, which conflicts with any existing shared lock) -- which is
     the actual "can look, can't touch while I'm editing" behavior
     wanted here. On Windows this needs ``LockFileEx`` called through
     ctypes, since Python's ``msvcrt`` module only exposes exclusive
     locking, not Win32's shared-lock mode.

   Only the sidecar lock is exclusive; only the real-file lock needs to
   distinguish shared from exclusive, since only the real file is
   something other applications might independently want to read.

   This tool's own writes need to coexist with the shared lock it holds
   on the very file being written to: Windows locking is mandatory
   against the *same* process's other handles too, not just other
   processes', so a second handle (``glossary.write()`` opens its own)
   writing to a region this tool has locked from a different handle would
   itself be blocked. ``write_around()`` handles that by releasing only
   the real-file lock (not the sidecar instance-lock) around the write,
   then reacquiring it -- see that method's docstring for the failure
   modes this briefly-unprotected window creates and how they're
   surfaced rather than hidden.

   None of this has been verified against a real Microsoft Office or WPS
   installation -- there isn't one in this project's dev/CI environment
   to test against (same class of limitation as this codebase's
   documented "Linux offscreen rendering can't verify Windows font/CSS
   behavior" for the docx viewer). The POSIX fallback (``fcntl.flock``,
   used for both the sidecar and the real-file lock on non-Windows) has
   been tested here and proves this module's own two-lock coordination is
   internally consistent, but -- being advisory rather than Windows'
   mandatory locking -- doesn't prove anything about actual behavior
   against a real non-Python application on Windows. If you hit a case
   where this still gives a false positive or false negative against a
   real Office/WPS session, that's useful to know about.
"""
import os


def office_lock_marker_path(path):
    directory, filename = os.path.split(path)
    return os.path.join(directory, '~$%s' % filename)


def office_lock_marker_exists(path):
    """Best-effort, not authoritative -- see module docstring. A stale
    marker left behind by a crashed Office/WPS session looks identical to
    a genuinely open file from out here; callers should surface a hit as
    a warning the person can choose to override, not a hard block.
    """
    return os.path.exists(office_lock_marker_path(path))


def _ensure_nonempty(fh):
    """msvcrt.locking()/LockFileEx lock a byte *range*, which needs at
    least one actual byte to lock on Windows -- a brand-new empty sidecar
    file wouldn't have one yet.
    """
    fh.seek(0)
    if fh.read(1) == b'':
        fh.write(b'\0')
        fh.flush()
    fh.seek(0)


def _lock_exclusive(fh):
    if os.name == 'nt':
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_exclusive(fh):
    if os.name == 'nt':
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _lock_shared(fh):
    if os.name == 'nt':
        _win32_lock_file_ex(fh, exclusive=False)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)


def _unlock_shared(fh):
    if os.name == 'nt':
        _win32_unlock_file_ex(fh)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# Windows-only: Python's msvcrt module only exposes exclusive locking
# (_locking() has no shared mode), so a real shared lock needs Win32's
# LockFileEx called directly through ctypes. Kept lazy/function-local
# (imports and struct definition both) rather than at module level, same
# pattern the rest of this module already uses for msvcrt/fcntl: this
# module is imported on every app launch (the term-management page is
# imported at startup regardless of which tool someone opens -- see
# registry.discover()), so anything Windows-only has to stay off the
# import path entirely on other platforms, not just conditionally skipped
# after being imported.

def _win32_lock_file_ex(fh, exclusive):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    LOCKFILE_EXCLUSIVE_LOCK = 0x00000002

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ('Internal', ctypes.c_void_p),
            ('InternalHigh', ctypes.c_void_p),
            ('Offset', wintypes.DWORD),
            ('OffsetHigh', wintypes.DWORD),
            ('hEvent', wintypes.HANDLE),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = msvcrt.get_osfhandle(fh.fileno())
    flags = LOCKFILE_FAIL_IMMEDIATELY | (LOCKFILE_EXCLUSIVE_LOCK if exclusive else 0)
    overlapped = _Overlapped()
    ok = kernel32.LockFileEx(
        wintypes.HANDLE(handle), wintypes.DWORD(flags),
        wintypes.DWORD(0), wintypes.DWORD(1), wintypes.DWORD(0), ctypes.byref(overlapped))
    if not ok:
        raise OSError('LockFileEx failed (Windows error %d)' % ctypes.get_last_error())


def _win32_unlock_file_ex(fh):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ('Internal', ctypes.c_void_p),
            ('InternalHigh', ctypes.c_void_p),
            ('Offset', wintypes.DWORD),
            ('OffsetHigh', wintypes.DWORD),
            ('hEvent', wintypes.HANDLE),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = msvcrt.get_osfhandle(fh.fileno())
    overlapped = _Overlapped()
    kernel32.UnlockFileEx(
        wintypes.HANDLE(handle), wintypes.DWORD(0),
        wintypes.DWORD(1), wintypes.DWORD(0), ctypes.byref(overlapped))


class FileLock:
    """Locks ``path`` for editing -- see module docstring for the two
    underlying locks this actually holds and why. Only usable on a real
    file that already exists (the real-file half of the lock needs
    something to open in ``'r+b'``), which is always true for a glossary
    this tool would ever lock: it's only ever locked right after
    ``glossary.read()`` (which requires the file to exist) or right after
    ``glossary.write()`` (which just created it).

    ``acquire()`` raises ``OSError`` if either lock is already held
    elsewhere. Callers should catch ``OSError`` specifically, not a
    lock-specific type, since the platform backends raise different
    concrete subclasses of it.
    """

    def __init__(self, path):
        self.path = path
        self._instance_fh = None  # exclusive lock on the sidecar -- see module docstring
        self._shared_fh = None    # shared lock on the real file -- see module docstring

    @property
    def is_held(self):
        return self._instance_fh is not None

    def acquire(self):
        if self._instance_fh is not None:
            raise OSError('file lock is already held')

        instance_fh = open(self.path + '.lock', 'a+b')
        _ensure_nonempty(instance_fh)
        try:
            _lock_exclusive(instance_fh)
        except OSError:
            instance_fh.close()
            raise

        shared_fh = open(self.path, 'r+b')
        try:
            _lock_shared(shared_fh)
        except OSError:
            _unlock_exclusive(instance_fh)
            instance_fh.close()
            shared_fh.close()
            raise

        self._instance_fh = instance_fh
        self._shared_fh = shared_fh

    def release(self):
        if self._instance_fh is None:
            return
        instance_fh, self._instance_fh = self._instance_fh, None
        shared_fh, self._shared_fh = self._shared_fh, None
        try:
            _unlock_shared(shared_fh)
        finally:
            shared_fh.close()
            try:
                _unlock_exclusive(instance_fh)
            finally:
                instance_fh.close()
                try:
                    os.remove(self.path + '.lock')
                except OSError:
                    pass  # already gone, or another process still has it open elsewhere -- either way, not fatal

    def write_around(self, write_fn):
        """Runs ``write_fn()`` (a callable that rewrites ``self.path`` on
        disk -- e.g. ``lambda: glossary.write(path, entries)``) with only
        the real-file *shared* lock released around it, not the sidecar
        instance-lock (which never touches the real file, so this tool's
        own write can't collide with it -- no reason to release it too).
        See module docstring for why the shared lock needs releasing at
        all.

        Always attempts to re-acquire the shared lock afterward,
        regardless of whether ``write_fn()`` raised -- even a failed
        write is a reason to try to restore protection, not a reason to
        give up on it (the file may not have been touched, or may be in
        an otherwise-valid state; leaving it deliberately unprotected
        after a failure would only make a bad situation worse). If the
        write raised, that exception propagates once re-acquisition has
        been attempted either way. If the write succeeded but
        re-acquiring afterward fails (something else grabbed a
        conflicting lock in the brief window it was released -- rare,
        but possible), that's raised as ``OSError``: the save did
        succeed, but silently leaving the caller believing the file is
        still protected when it no longer is would be worse than a loud
        failure over a save that otherwise went fine. If *both* the
        write and the re-acquire fail, the write's own exception is what
        propagates -- that's the more actionable one to report, and the
        file is already in a failure state either way.
        """
        if self._shared_fh is None:
            raise OSError('file lock is not held')

        shared_fh, self._shared_fh = self._shared_fh, None
        _unlock_shared(shared_fh)
        shared_fh.close()

        write_error = None
        try:
            write_fn()
        except BaseException as exc:
            write_error = exc
        finally:
            try:
                new_shared_fh = open(self.path, 'r+b')
                _lock_shared(new_shared_fh)
                self._shared_fh = new_shared_fh
            except OSError as reacquire_error:
                if write_error is None:
                    raise OSError(
                        'file was saved, but the file lock could not be reacquired'
                    ) from reacquire_error

        if write_error is not None:
            raise write_error

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
