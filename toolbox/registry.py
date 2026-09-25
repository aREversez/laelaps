"""Tool registry for the desktop toolbox shell.

Adding a new tool means: create ``toolbox/tools/<id>/``, define a QWidget
page factory, and call ``register()`` from that package's ``__init__.py``.
``main_window.py`` never needs to change -- it just iterates ``TOOLS``.
"""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QWidget


@dataclass
class ToolSpec:
    id: str
    name: str
    description: str
    icon: str                       # Tabler-style glyph name or a resource path; see resources/
    page_factory: Callable[[], QWidget]
    # Sidebar/home-page section this tool belongs to ('' = ungrouped, shows
    # under 其它). MainWindow groups sidebar items under a section header
    # per distinct non-empty group; order (below) is what makes a group's
    # members contiguous, so group alone must never be relied on for order.
    group: str = ''
    # Explicit global sort key for the sidebar and home-page grid. Chosen
    # over registration/discovery order because pkgutil's import order is
    # filesystem-dependent and leaks across a test session (a module that
    # was already imported earlier in the process is not re-imported, so
    # TOOLS ends up in first-import-seen order, not any stable order) --
    # and over alphabetical-by-id because that interleaves group members
    # into non-contiguous runs of one section name. Ties keep discovery
    # order (Python's sort is stable). Home uses order=0 to head the list.
    # The default is 999, not 0: every ToolSpec today sets order explicitly,
    # but a new one that forgets to would collide with home's 0 under a 0
    # default and land wherever discovery order happened to put it -- 999
    # instead sorts a forgotten order to the very end, visibly out of place
    # rather than silently first.
    order: int = 999


TOOLS: list[ToolSpec] = []


def register(spec: ToolSpec) -> None:
    if any(t.id == spec.id for t in TOOLS):
        raise ValueError('a tool with id %r is already registered' % spec.id)
    TOOLS.append(spec)


def discover() -> list[ToolSpec]:
    """Import every tools/<id> subpackage so its register() call runs, then
    return the populated registry. Called once at app startup.
    """
    import importlib
    import pkgutil

    import toolbox.tools as tools_pkg

    for _, name, _ in pkgutil.iter_modules(tools_pkg.__path__):
        importlib.import_module('toolbox.tools.%s' % name)
    return TOOLS
