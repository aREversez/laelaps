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
