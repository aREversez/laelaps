"""Best-effort "is this glossary file already in use elsewhere" checks for
the term-management GUI page.

Two independent, one-directional checks -- deliberately not one unified
mechanism, because the two directions need genuinely different techniques
and neither can see into the other's world:

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

2. ``SidecarLock``: an OS-level advisory lock on a *separate* sidecar
   file (``<path>.lock``), not the glossary file itself. Locking the real
   file directly was the first design tried here, and was dropped: this
   module's own ``glossary.read()``/``write()`` open the real file
   independently for I/O, and a lock held on it -- especially msvcrt's
   Windows byte-range locking, which (unlike POSIX flock) is enforced
   against the very process holding it too -- risks this tool blocking
   its own save. A sidecar avoids that risk entirely, at the cost of a
   narrower guarantee: it only protects against a *second instance of
   this tool* editing the same glossary concurrently, not against
   Office/WPS (a sidecar file only this tool ever reads isn't something
   Office checks). Stated plainly here rather than implied to be a
   general "detect any other program has it open" mechanism, which it
   isn't.

Neither mechanism has been verified against a real Microsoft Office or
WPS installation -- there isn't one in this project's dev/CI environment
to test against (same class of limitation as this codebase's documented
"Linux offscreen rendering can't verify Windows font/CSS behavior" for
the docx viewer). If you hit a case where either check gives a false
positive or false negative against a real Office/WPS session, that's
useful to know about.
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


class SidecarLock:
    """Advisory lock on ``<path>.lock``, held for as long as this object
    stays alive (until ``release()``, or the process exits -- the OS
    releases the underlying lock automatically then even without an
    explicit release, so a crash doesn't leave a permanently-stuck lock
    the way a plain marker *file*'s mere existence would). See module
    docstring for why the sidecar, not the real glossary file, is locked.

    ``acquire()`` raises ``OSError`` if another ``SidecarLock`` already
    holds it (this tool's own other instance, most plausibly). Callers
    should catch ``OSError`` specifically (not some lock-specific
    exception type) since the two platform backends below raise
    different concrete subclasses of it.
    """

    def __init__(self, path):
        self.lock_path = path + '.lock'
        self._fh = None

    def acquire(self):
        fh = open(self.lock_path, 'a+b')
        fh.seek(0)
        if fh.read(1) == b'':
            # msvcrt.locking() below locks a byte range, which needs at
            # least one actual byte to lock on Windows -- a brand-new
            # empty sidecar file wouldn't have one yet.
            fh.write(b'\0')
            fh.flush()
        fh.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            raise
        self._fh = fh

    def release(self):
        if self._fh is None:
            return
        fh, self._fh = self._fh, None
        try:
            if os.name == 'nt':
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
            try:
                os.remove(self.lock_path)
            except OSError:
                pass  # already gone, or another process still has it open elsewhere -- either way, not fatal

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
