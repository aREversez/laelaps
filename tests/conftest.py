import os

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
