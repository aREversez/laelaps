import os

import pytest

from language_tools.terms.filelock import SidecarLock, office_lock_marker_exists, office_lock_marker_path


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


# --------------------------------------------------------------- SidecarLock

def test_acquire_creates_lock_file(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    lock = SidecarLock(path)
    lock.acquire()
    try:
        assert os.path.exists(path + '.lock')
    finally:
        lock.release()


def test_release_removes_lock_file(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    lock = SidecarLock(path)
    lock.acquire()
    lock.release()
    assert not os.path.exists(path + '.lock')


def test_release_is_idempotent(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    lock = SidecarLock(path)
    lock.acquire()
    lock.release()
    lock.release()  # must not raise


def test_second_lock_on_same_path_raises_oserror(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    first = SidecarLock(path)
    first.acquire()
    try:
        second = SidecarLock(path)
        with pytest.raises(OSError):
            second.acquire()
    finally:
        first.release()


def test_lock_is_released_and_reacquirable_after_release(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    first = SidecarLock(path)
    first.acquire()
    first.release()

    second = SidecarLock(path)
    second.acquire()  # must not raise -- first's lock is gone
    second.release()


def test_different_paths_do_not_conflict(tmp_path):
    a = SidecarLock(str(tmp_path / 'a.csv'))
    b = SidecarLock(str(tmp_path / 'b.csv'))
    a.acquire()
    try:
        b.acquire()  # must not raise
        b.release()
    finally:
        a.release()


def test_context_manager_releases_on_exit(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    with SidecarLock(path):
        assert os.path.exists(path + '.lock')
    assert not os.path.exists(path + '.lock')


def test_context_manager_releases_on_exception(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    try:
        with SidecarLock(path):
            raise ValueError('boom')
    except ValueError:
        pass
    assert not os.path.exists(path + '.lock')
