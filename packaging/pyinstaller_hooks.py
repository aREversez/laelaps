"""Computes the ``hiddenimports`` the desktop-toolbox PyInstaller build
needs for ``toolbox/tools/*`` -- pulled out of ``language-toolbox.spec``
into its own plain, normally-importable module for one reason: a .spec
file is ``exec()``'d by PyInstaller with injected globals (``Analysis``,
``SPECPATH``, etc.) that don't exist under a normal import, which makes
its logic awkward to unit-test directly. This module has no such
dependency, so ``tests/test_packaging_spec.py`` can import and exercise
the exact function the spec calls, not a parallel reimplementation of it
that could quietly drift out of sync with what actually ships.

See that module's docstring, and the comment above the call site in
``language-toolbox.spec``, for the underlying bug this exists to catch:
``toolbox/tools/*`` subpackages are only ever imported dynamically
(``toolbox/registry.py``'s ``discover()``), which PyInstaller's static
Analysis can't see, so they silently don't get bundled without this.
"""
import os

from PyInstaller.utils.hooks import collect_submodules


def _actual_tool_packages(repo_root):
    tools_dir = os.path.join(repo_root, 'toolbox', 'tools')
    return sorted(
        name for name in os.listdir(tools_dir)
        if os.path.isdir(os.path.join(tools_dir, name))
        and os.path.exists(os.path.join(tools_dir, name, '__init__.py'))
    )


def collect_tool_hiddenimports(repo_root):
    """Returns the dotted-name list to pass as ``Analysis(hiddenimports=...)``.

    Raises ``RuntimeError`` if any actual ``toolbox/tools/<id>/`` package
    on disk didn't come back from ``collect_submodules()`` -- e.g. because
    the package fails to import cleanly during the build, or some future
    refactor moves tools somewhere collect_submodules can't see. Without
    this check the failure mode is silent: a normally-completing build
    that produces an exe with an empty sidebar, discovered only by
    actually launching it (that gap is exactly how this bug shipped the
    first time -- see the .spec file's comment for the full story).
    """
    hidden = collect_submodules('toolbox.tools')
    missing = [
        name for name in _actual_tool_packages(repo_root)
        if 'toolbox.tools.%s' % name not in hidden
    ]
    if missing:
        raise RuntimeError(
            'toolbox/tools packages missing from PyInstaller hiddenimports: %s '
            "(collect_submodules('toolbox.tools') only found %s) -- the packaged "
            'exe would launch with an empty sidebar ("没有已注册的工具"); fix '
            'whatever is breaking submodule collection before building.' %
            (missing, sorted(hidden)))
    return hidden
