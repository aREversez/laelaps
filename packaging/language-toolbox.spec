# PyInstaller spec for the desktop toolbox app.
#
# Build (on the target OS -- PyInstaller does not cross-compile):
#   pip install -e ".[gui]"
#   pyinstaller packaging/language-toolbox.spec
#
# Produces dist/language-toolbox/ (onedir build -- faster startup than
# onefile, and easier to inspect if something's missing). Switch to a
# single EXE by setting ONEFILE=True below once the app is stable enough
# that startup time / antivirus false-positive risk from onefile's
# self-extraction is worth trading for a single distributable file.
import sys
from pathlib import Path

block_cipher = None
ONEFILE = False

REPO_ROOT = Path(SPECPATH).parent  # noqa: F821 -- SPECPATH is injected by PyInstaller

# toolbox/registry.py's discover() finds each tool package with
# pkgutil.iter_modules() + importlib.import_module() using a *runtime-built*
# dotted name (see that module's docstring). That's exactly the ergonomics
# we want at the source level -- drop a new toolbox/tools/<id>/ folder in
# and main_window.py never needs to change -- but PyInstaller's Analysis
# only sees import statements and importlib calls with a literal string
# argument; a name assembled at runtime from pkgutil's scan is invisible to
# it. The result: alignment_check/corpus_convert/qa_check/tm_maintenance
# silently never get bundled, discover() finds nothing at runtime (the
# frozen app's own pkgutil scan is empty because there's nothing there to
# scan), and MainWindow falls back to its "没有已注册的工具" empty state --
# confirmed by inspecting the built PYZ archive: toolbox.tools' four
# subpackages are absent from it without the hiddenimports computed below.
# pyinstaller_hooks.collect_tool_hiddenimports() walks toolbox/tools the
# same way at *build* time (a normal, unfrozen Python process, so pkgutil
# works as expected) and returns every submodule's dotted name explicitly,
# so this needs no maintenance when a new tool is added later -- same
# "just add a folder" promise registry.py's docstring makes, just
# satisfied at the packaging layer instead of assuming static analysis
# will figure it out. That helper (not inlined here) also raises loudly
# if a tool package ever goes missing from the result -- see its
# docstring -- and living in its own plain module means
# tests/test_packaging_spec.py can unit-test that exact logic directly,
# instead of only ever finding out via a full PyInstaller build.
sys.path.insert(0, str(REPO_ROOT / 'packaging'))
from pyinstaller_hooks import collect_tool_hiddenimports  # noqa: E402

hidden_tool_imports = collect_tool_hiddenimports(str(REPO_ROOT))

a = Analysis(  # noqa: F821 -- SPECPATH is injected by PyInstaller
    [str(REPO_ROOT / 'toolbox' / 'main.py')],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[(str(REPO_ROOT / 'toolbox' / 'resources'), 'toolbox/resources')],
    hiddenimports=hidden_tool_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

if ONEFILE:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name='language-toolbox', console=False, onefile=True,
        icon=str(REPO_ROOT / 'toolbox' / 'resources' / 'icons' / 'app.ico'),
    )
else:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, [], exclude_binaries=True,
        name='language-toolbox', console=False,
        icon=str(REPO_ROOT / 'toolbox' / 'resources' / 'icons' / 'app.ico'),
    )
    coll = COLLECT(  # noqa: F821
        exe, a.binaries, a.zipfiles, a.datas,
        name='language-toolbox',
    )
