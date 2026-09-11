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

2. ``FileLock``: an OS-level lock on the *real* glossary file itself.

   An earlier version of this locked a separate sidecar file instead
   (``<path>.lock``), specifically to avoid this tool's own save
   conflicting with a lock it held on the real file. That turned out to
   defeat the entire point: a sidecar file only this tool ever reads
   isn't something WPS/Office can be blocked by or checks against, and
   real testing confirmed it -- WPS could open, edit, and save a file
   this tool had "locked" via a sidecar with no conflict at all, and this
   tool never noticed when WPS had the file open first either. Locking
   the real file is the only version of this that can actually interact
   with another *application*, not just another instance of this tool.

   On Windows this uses ``msvcrt.locking()`` on a 1-byte region at the
   start of the file. Unlike POSIX advisory locking, Windows file locking
   is mandatory: the OS itself denies another process's read/write
   across that region regardless of how permissively that other process
   opened the file -- which is what gives this a real chance of causing
   WPS/Office's own read or write to fail (and, for anything in the
   Office family specifically, surface as their own "file in use"
   handling) rather than only ever protecting against another instance
   of this same tool.

   This tool's own read/write need to coexist with a lock it's holding on
   the very file they touch. Reading happens *before* a lock is
   acquired (``glossary.read()`` uses its own separate, short-lived file
   handle -- see the page's ``_open_glossary()``), so there's no overlap
   there. Writing while a lock is already held is the harder case:
   Windows mandatory locking blocks a second handle from the *same*
   process too, not just other processes, so this tool's own
   ``glossary.write()`` -- which opens its own handle -- would otherwise
   be blocked by a lock this tool is holding on itself. ``write_around()``
   handles that: release, run the write via a fresh unlocked handle,
   re-acquire.

   On non-Windows platforms (dev/CI -- this app ships as a Windows exe,
   real end users are on Windows) this falls back to ``fcntl.flock``,
   which is advisory-only: correct for testing this module's own logic
   in this environment, but -- unlike the Windows path -- not something a
   non-Python process would ever be blocked by. Neither backend has been
   verified against a real Microsoft Office or WPS installation -- there
   isn't one in this project's dev/CI environment to test against (same
   class of limitation as this codebase's documented "Linux offscreen
   rendering can't verify Windows font/CSS behavior" for the docx
   viewer). If you hit a case where either check gives a false positive
   or false negative against a real Office/WPS session, that's useful to
   know about.
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
    """Locks ``path`` itself (see module docstring for why, and for what
    this can and can't actually do). Only usable on a file that already
    exists and has at least one byte -- true for every glossary this tool
    would ever lock, since ``glossary.write()`` always writes a header row
    at minimum.

    ``acquire()`` raises ``OSError`` if the region is already locked
    (another process -- ideally WPS/Office, but most reliably tested here
    against another instance of this tool -- or a lock this same
    ``FileLock`` already holds; re-acquiring without releasing first is a
    caller bug, not something this class silently tolerates). Callers
    should catch ``OSError`` specifically, not a lock-specific type, since
    the two platform backends raise different concrete subclasses of it.
    """

    def __init__(self, path):
        self.path = path
        self._fh = None

    def acquire(self):
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
        """Runs ``write_fn()`` (a callable that rewrites ``self.path`` on
        disk -- e.g. ``lambda: glossary.write(path, entries)``) with this
        lock momentarily released, then re-acquired -- see module
        docstring for why a held lock on the real file needs this instead
        of just calling ``write_fn()`` directly.

        If ``write_fn()`` raises, that propagates normally (the save
        failed; the lock is left released -- re-acquiring it after a
        failed save that may not even have touched the file isn't this
        method's call to make, so it doesn't try). If the write succeeds
        but re-acquiring the lock afterward fails (something else grabbed
        it in the brief window it was released -- rare, but possible),
        that's swallowed rather than raised: the save itself already
        succeeded, and failing the whole operation over a lock that's now
        just protecting an already-completed write would be the wrong
        tradeoff. Callers that care can check ``is_held`` afterward.
        """
        self.release()
        write_fn()
        try:
            self.acquire()
        except OSError:
            pass

    @property
    def is_held(self):
        return self._fh is not None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
