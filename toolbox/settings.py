"""Thin typed wrapper around QSettings for per-tool-page persisted form
state (语言/排版/输出格式/QA/上次浏览目录 and similar small values a page
wants to remember across launches) -- the "设置持久化" backlog item.
Window geometry already has its own QSettings() call in main_window.py;
this is for the per-tool form fields main_window.py has no business
knowing the shape of.

Why get_bool()/get_str() wrap QSettings().value() instead of every page
calling it directly: QSettings' untyped .value() is documented as
backend-dependent for anything that isn't already a string -- a bool can
come back as the literal string "false" instead of Python's False
depending on backend and Qt version, which is silently wrong (a non-empty
string is truthy) rather than loudly broken. Passing type=bool/type=str
explicitly is Qt's own documented fix. (Checked empirically on this
project's actual PySide6/Qt 6.11 + the INI backend tests run under --
see conftest.py's ``_isolated_qsettings`` -- bool already round-trips
correctly here even without the type hint; kept explicit anyway as
defensive practice, since the native registry backend Windows actually
ships with, and other Qt/PySide versions, aren't verified in this sandbox
and Qt's own docs describe this as backend-dependent in general.) If
every tool page's restore_settings() remembers to pass the right type=
at every call site, that's fine 5 times and silently wrong the 6th on
whatever backend doesn't cooperate -- centralized here once instead, so
a tool page never touches QSettings directly.

Keys are flat strings ``'<tool_id>/<field>'`` (same convention as
``main_window.py``'s ``mainWindow/geometry``), not QSettings groups --
groups add a stack-based beginGroup()/endGroup() calling convention for
no benefit at this scale (a few dozen keys total across every tool page).
"""
from PySide6.QtCore import QSettings


def get_str(key, default=''):
    return QSettings().value(key, default, type=str)


def get_bool(key, default=False):
    return QSettings().value(key, default, type=bool)


def get_int(key, default=0):
    return QSettings().value(key, default, type=int)


def set_value(key, value):
    QSettings().setValue(key, value)
