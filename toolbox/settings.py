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


# Cross-tool global keys (DESIGN.md 15.4 P2): the ``'global/'`` prefix sits
# alongside the per-tool ``'<tool_id>/'`` convention for the handful of
# values that aren't owned by one page's form -- home's recently-used list
# and the shared default output directory.
_GLOBAL_PREFIX = 'global/'
_RECENT_KEY = 'home/recent_tools'
_RECENT_MAX = 3


def get_default_output_dir():
    """The cross-tool default output directory (DESIGN.md 15.4 P2), or ''
    when unset. Pages may use it as a fallback start dir for a save/browse
    dialog when they haven't remembered their own last directory."""
    return get_str(_GLOBAL_PREFIX + 'default_output_dir')


def set_default_output_dir(path):
    set_value(_GLOBAL_PREFIX + 'default_output_dir', path or '')


def effective_start_dir(last_dir=''):
    """A save/export dialog's starting directory: the page's own remembered
    last dir if it has one, else the cross-tool 默认输出目录 (DESIGN.md 15.4
    P2). Purely additive -- with no global default set it returns
    ``last_dir`` unchanged, so a page that never adopted the global default
    (or a user who left it blank) behaves exactly as before."""
    return (last_dir or '').strip() or get_default_output_dir()


def get_recent_tools():
    """Most-recent-first list of tool ids last opened (max ``_RECENT_MAX``),
    recorded centrally in ``MainWindow.select_tool`` -- the one convergence
    point for every navigation route (sidebar, home tile, Ctrl+N) -- so
    none of them has to remember to update it itself. Empty string / unknown
    entries are dropped rather than shown as blank tiles."""
    return [t for t in get_str(_RECENT_KEY).split(',') if t]


def record_recent_tool(tool_id):
    if not tool_id or tool_id == 'home':
        return
    items = [t for t in get_recent_tools() if t != tool_id]
    items.insert(0, tool_id)
    set_value(_RECENT_KEY, ','.join(items[:_RECENT_MAX]))
