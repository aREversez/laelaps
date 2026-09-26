"""Regression coverage for deferred openpyxl imports (see
``readers/xlsx_bilingual.py`` and ``terms/glossary.py``'s docstrings for
why): importing either module by itself must not pull in openpyxl, or
every app launch pays its load cost (openpyxl pulls in chart/pivot/
drawing submodules on import -- roughly 100-300ms even on a quick Linux
check, worse under Windows antivirus real-time scanning) regardless of
whether the session ever touches an xlsx file. ``toolbox.registry.
discover()`` imports every ``toolbox/tools/*/page.py`` at startup to
build the sidebar, so both modules get imported on every launch whether
or not xlsx comes up -- this is exactly the app-startup-vs-first-xlsx-use
distinction that made the eager import worth fixing.

Runs in a fresh subprocess -- sys.modules is process-global, so checking
this in-process (after pytest's own collection has already imported who
knows what for other test files) would give a false pass regardless of
whether these two modules are actually lazy.
"""
import subprocess
import sys


def _import_does_not_pull_in_openpyxl(module_name):
    code = (
        'import sys\n'
        'import %s\n'
        'assert "openpyxl" not in sys.modules, "%s eagerly imported openpyxl"\n'
    ) % (module_name, module_name)
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_xlsx_bilingual_reader_import_does_not_pull_in_openpyxl():
    _import_does_not_pull_in_openpyxl('language_tools.readers.xlsx_bilingual')


def test_terms_glossary_import_does_not_pull_in_openpyxl():
    _import_does_not_pull_in_openpyxl('language_tools.terms.glossary')
