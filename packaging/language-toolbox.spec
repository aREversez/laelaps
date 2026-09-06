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

a = Analysis(  # noqa: F821 -- SPECPATH is injected by PyInstaller
    [str(REPO_ROOT / 'toolbox' / 'main.py')],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[(str(REPO_ROOT / 'toolbox' / 'resources'), 'toolbox/resources')],
    hiddenimports=[],
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
