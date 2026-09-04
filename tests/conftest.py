import os

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
DOCX_DIR = os.path.join(FIXTURES, 'docx')
EXPECTED_DIR = os.path.join(FIXTURES, 'expected')


def fixture_path(name):
    return os.path.join(DOCX_DIR, name)


def expected_path(name):
    return os.path.join(EXPECTED_DIR, name)
