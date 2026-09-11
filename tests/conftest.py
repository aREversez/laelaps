import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
DOCX_DIR = os.path.join(FIXTURES, 'docx')
XLSX_DIR = os.path.join(FIXTURES, 'xlsx')
CSV_DIR = os.path.join(FIXTURES, 'csv')
EXPECTED_DIR = os.path.join(FIXTURES, 'expected')
TMX_DIR = os.path.join(FIXTURES, 'tmx')


def fixture_path(name):
    return os.path.join(DOCX_DIR, name)


def xlsx_path(name):
    return os.path.join(XLSX_DIR, name)


def csv_path(name):
    return os.path.join(CSV_DIR, name)


def expected_path(name):
    return os.path.join(EXPECTED_DIR, name)


def tmx_path(name):
    return os.path.join(TMX_DIR, name)


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path):
    """Redirects every default-constructed QSettings() (MainWindow uses
    one, unqualified, to remember window geometry across launches -- see
    that module's docstring) to a per-test tmp_path ini file instead of
    the real user config location. Without this, running the test suite
    would read/write the actual developer machine's saved window geometry
    -- silently coupling test results to whatever that machine happens to
    have saved locally, and, worse, a test run could overwrite it.
    QSettings.setPath() is Qt's own sanctioned mechanism for exactly this
    ("testing purposes" per its own docs); harmless no-op for the many
    tests that never touch QSettings at all.
    """
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    yield
