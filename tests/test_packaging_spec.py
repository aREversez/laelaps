"""Regression coverage for the PyInstaller packaging bug: toolbox/tools/*
subpackages are only ever imported dynamically (registry.discover() builds
the module name at runtime from a pkgutil scan -- see that module's
docstring), which PyInstaller's static Analysis cannot see. Without an
explicit ``hiddenimports`` covering them, they silently don't get bundled
into the frozen exe, and the packaged app launches with an empty sidebar
("没有已注册的工具") even though a source checkout works fine -- and even
though the same .spec produces a *working* Linux binary (verified in this
sandbox by inspecting the built PYZ archive directly: the missing modules
aren't referenced anywhere OS/arch would affect, so catching this doesn't
require a Windows machine, just actually launching whatever gets built).

This exercises ``packaging/pyinstaller_hooks.collect_tool_hiddenimports()``
directly -- the exact function ``language-toolbox.spec`` calls for its
``hiddenimports`` -- rather than a parallel reimplementation of the same
check that could quietly drift out of sync with what actually ships.
Doesn't invoke PyInstaller's full Analysis()/build pipeline (slow, and
``pyinstaller`` isn't one of the ``gui``/``dev`` extras every environment
has installed) -- skips rather than fails if it's unavailable.
"""
import os
import sys

import pytest

pytest.importorskip('PyInstaller')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'packaging'))
from pyinstaller_hooks import _actual_tool_packages, collect_tool_hiddenimports  # noqa: E402


def test_at_least_the_four_known_tools_exist():
    # Sanity check on the check itself: if this ever comes back empty (or
    # missing a tool everyone knows exists), the real assertion below
    # would pass vacuously and prove nothing.
    assert set(_actual_tool_packages(_REPO_ROOT)) >= {
        'alignment_check', 'corpus_convert', 'qa_check', 'tm_maintenance'}


def test_collect_tool_hiddenimports_covers_every_tool_package():
    hidden = collect_tool_hiddenimports(_REPO_ROOT)
    for name in _actual_tool_packages(_REPO_ROOT):
        assert 'toolbox.tools.%s' % name in hidden


def test_collect_tool_hiddenimports_raises_if_a_tool_package_goes_missing(tmp_path, monkeypatch):
    # Simulates the exact failure this whole module exists to prevent: a
    # toolbox/tools/<id>/ package that exists on disk but that
    # collect_submodules() (for whatever reason -- broken imports, moved
    # elsewhere, etc.) doesn't return. This must be a loud build-time
    # error, not a silently-incomplete frozen exe.
    import pyinstaller_hooks

    monkeypatch.setattr(pyinstaller_hooks, 'collect_submodules', lambda pkg: ['toolbox.tools'])
    fake_root = tmp_path
    tools_dir = fake_root / 'toolbox' / 'tools' / 'some_tool'
    tools_dir.mkdir(parents=True)
    (tools_dir / '__init__.py').write_text('')

    with pytest.raises(RuntimeError, match='some_tool'):
        pyinstaller_hooks.collect_tool_hiddenimports(str(fake_root))
