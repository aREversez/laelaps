import os

import pytest

from language_tools.terms.filelock import FileLock, office_lock_marker_exists, office_lock_marker_path


def _write(path, content=b'src_term,tgt_term\n'):
    with open(path, 'wb') as f:
        f.write(content)


# --------------------------------------------------------- office marker

def test_office_lock_marker_path_prefixes_filename_with_tilde_dollar(tmp_path):
    path = str(tmp_path / 'glossary.xlsx')
    assert office_lock_marker_path(path) == str(tmp_path / '~$glossary.xlsx')


def test_office_lock_marker_exists_false_when_absent(tmp_path):
    path = str(tmp_path / 'glossary.xlsx')
    assert office_lock_marker_exists(path) is False


def test_office_lock_marker_exists_true_when_present(tmp_path):
    path = str(tmp_path / 'glossary.xlsx')
    (tmp_path / '~$glossary.xlsx').write_bytes(b'')
    assert office_lock_marker_exists(path) is True


# ------------------------------------------------------------------ FileLock

def test_acquire_and_release_round_trip(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    assert lock.is_held is False
    lock.acquire()
    assert lock.is_held is True
    lock.release()
    assert lock.is_held is False


def test_release_is_idempotent(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()
    lock.release()
    lock.release()  # must not raise


def test_second_lock_on_same_path_raises_oserror(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    first = FileLock(path)
    first.acquire()
    try:
        second = FileLock(path)
        with pytest.raises(OSError):
            second.acquire()
    finally:
        first.release()


def test_lock_is_released_and_reacquirable_after_release(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    first = FileLock(path)
    first.acquire()
    first.release()

    second = FileLock(path)
    second.acquire()  # must not raise -- first's lock is gone
    second.release()


def test_different_paths_do_not_conflict(tmp_path):
    path_a = str(tmp_path / 'a.csv')
    path_b = str(tmp_path / 'b.csv')
    _write(path_a)
    _write(path_b)
    a = FileLock(path_a)
    b = FileLock(path_b)
    a.acquire()
    try:
        b.acquire()  # must not raise
        b.release()
    finally:
        a.release()


def test_context_manager_releases_on_exit(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    with FileLock(path) as lock:
        assert lock.is_held is True
    assert lock.is_held is False


def test_context_manager_releases_on_exception(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    try:
        with lock:
            raise ValueError('boom')
    except ValueError:
        pass
    assert lock.is_held is False


# -------------------------------------------------------------- write_around

def test_write_around_runs_write_fn(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()
    calls = []
    lock.write_around(lambda: calls.append(1))
    assert calls == [1]
    lock.release()


def test_write_around_reacquires_lock_after_write(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()
    lock.write_around(lambda: None)
    assert lock.is_held is True

    # Confirm it's a genuinely fresh, working lock post-write, not just a
    # flag left set -- another lock on the same path must still conflict.
    other = FileLock(path)
    with pytest.raises(OSError):
        other.acquire()
    lock.release()


def test_write_around_does_not_self_block_a_real_write(tmp_path):
    """The whole reason write_around() exists: calling glossary.write()
    directly while still holding this same lock would fail on Windows
    (mandatory locking blocks the owning process's own second handle,
    not just other processes'). This can't be reproduced on POSIX
    (flock is per-process, not per-handle, so a second open from the
    same process was never blocked here to begin with) -- so this test
    exercises write_around()'s actual release-write-reacquire sequence
    end to end rather than the Windows-specific failure it prevents.
    """
    from language_tools.terms import glossary as glossary_module
    from language_tools.terms.model import TermEntry

    path = str(tmp_path / 'glossary.csv')
    glossary_module.write(path, [])
    lock = FileLock(path)
    lock.acquire()

    entries = [TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term='cloud', tgt_term='云')]
    lock.write_around(lambda: glossary_module.write(path, entries))

    back = glossary_module.read(path, 'en-US', 'zh-CN')
    assert len(back) == 1
    assert back[0].src_term == 'cloud'
    assert lock.is_held is True
    lock.release()


def test_write_around_propagates_write_fn_exception_but_still_restores_the_lock(tmp_path):
    # Matches write_around()'s "always try to restore protection, even
    # after a failed write" design (see that method's docstring): the
    # write failing is a reason to still attempt re-locking, not a
    # reason to leave the file unprotected on top of whatever else went
    # wrong with the write itself.
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()

    def boom():
        raise ValueError('write failed')

    with pytest.raises(ValueError):
        lock.write_around(boom)
    assert lock.is_held is True
    lock.release()


# ------------------------------------------------- shared vs exclusive locking

def test_held_lock_still_permits_a_plain_unlocked_read(tmp_path):
    # The actual bug this two-lock design exists to fix: an earlier
    # version locked the real file exclusively, which (on Windows, via
    # mandatory locking) blocked even plain reads from other programs --
    # a shared lock on the real file must not do that.
    path = str(tmp_path / 'glossary.csv')
    _write(path, b'src_term,tgt_term\ncloud,\xe4\xba\x91\n')
    lock = FileLock(path)
    lock.acquire()
    try:
        with open(path, 'rb') as f:
            content = f.read()
        assert b'cloud' in content
    finally:
        lock.release()


def test_two_locks_on_different_paths_can_both_be_held(tmp_path):
    path_a = str(tmp_path / 'a.csv')
    path_b = str(tmp_path / 'b.csv')
    _write(path_a)
    _write(path_b)
    a = FileLock(path_a)
    b = FileLock(path_b)
    a.acquire()
    try:
        b.acquire()  # must not raise -- unrelated files
        b.release()
    finally:
        a.release()


def test_acquire_creates_and_release_removes_the_sidecar_file(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()
    assert os.path.exists(path + '.lock')
    lock.release()
    assert not os.path.exists(path + '.lock')


def test_double_acquire_on_the_same_lock_object_raises(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    lock.acquire()
    try:
        with pytest.raises(OSError):
            lock.acquire()
    finally:
        lock.release()


def test_write_around_raises_if_the_lock_is_not_currently_held(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    _write(path)
    lock = FileLock(path)
    with pytest.raises(OSError, match='not held'):
        lock.write_around(lambda: None)
