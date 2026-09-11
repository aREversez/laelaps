import pytest

from language_tools.terms.filelock import FileLock


def _write(path, content=b'src_term,tgt_term\n'):
    path.write_bytes(content)


def test_write_around_requires_held_lock(tmp_path):
    path = tmp_path / 'glossary.csv'
    _write(path)
    lock = FileLock(str(path))
    with pytest.raises(OSError, match='not held'):
        lock.write_around(lambda: None)


def test_write_around_restores_lock_after_success(tmp_path):
    path = tmp_path / 'glossary.csv'
    _write(path)
    lock = FileLock(str(path))
    lock.acquire()
    try:
        lock.write_around(lambda: path.write_bytes(b'updated\n'))
        assert path.read_bytes() == b'updated\n'
        assert lock.is_held is True
    finally:
        lock.release()


def test_write_around_restores_lock_after_write_failure(tmp_path):
    path = tmp_path / 'glossary.csv'
    _write(path)
    lock = FileLock(str(path))
    lock.acquire()
    try:
        with pytest.raises(RuntimeError, match='boom'):
            lock.write_around(lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        assert lock.is_held is True
    finally:
        lock.release()
