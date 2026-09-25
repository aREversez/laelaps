"""The README promises "不需要联网、不上传文件" (no network, no file
upload). Until the semantic-review hook (DESIGN.md 15.2 third priority)
that was a docs claim only; this file turns it into a tested invariant of
the *core library*.

Scope is deliberate and narrow in one direction, wide in the other:
``language_tools`` only -- the offline guarantee is about what the
library does to your corpus files, and ``toolbox`` (GUI) is free to grow
non-network webengine-ish needs later without tripping this. Forbidden
names are the stdlib/third-party modules that can open a network
connection (``urllib.request``/``http.client``, not bare ``urllib`` --
``urllib.parse`` is local string work and already fine); a reviewer with
network access can of course still be *injected* (that's the feature),
but it must live outside this package, so its imports can never hide
here (see ``language_tools/semantic_review.py``'s docstring for why the
library ships no implementation of its own).

Static AST scan rather than a sys.modules probe (the ``test_lazy_openpyxl_import``
technique): the openpyxl test checks an *import-time side effect* of one
module, which is what a subprocess probe measures; here the claim is about
the source text of ~80 files, and a module-level ``import socket`` that
never executes at import time would sail through a sys.modules check.
"""
import ast
import pathlib

_CORE_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / 'language_tools'

_FORBIDDEN_ROOTS = {'socket', 'requests', 'httpx', 'urllib3'}
_FORBIDDEN_MODULES = {'socket', 'requests', 'httpx', 'urllib3',
                      'urllib.request', 'http.client'}


def _forbidden_hits(path):
    """Return descriptions of forbidden imports in one source file."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split('.')[0]
                if root in _FORBIDDEN_ROOTS or alias.name in _FORBIDDEN_MODULES:
                    hits.append('%s (line %d)' % (alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 = relative import; can't name a stdlib module.
            if node.level == 0 and node.module in _FORBIDDEN_MODULES:
                hits.append('%s (line %d)' % (node.module, node.lineno))
    return hits


def test_core_library_imports_no_network_capable_modules():
    files = sorted(_CORE_PACKAGE.rglob('*.py'))
    # Guard against the scan silently passing on a wrong path (or on the
    # package being emptied out by a refactor).
    assert files and all(p.is_relative_to(_CORE_PACKAGE) for p in files)
    offenders = {str(p): hit for p in files if (hit := _forbidden_hits(p))}
    assert not offenders, (
        'language_tools must stay network-free (README offline promise); '
        'an outside reviewer belongs behind semantic_review.attach() '
        'instead: %s' % offenders)
