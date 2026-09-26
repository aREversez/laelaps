"""Entry point for the desktop toolbox app: ``python -m toolbox.main``."""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from toolbox import tooltips
from toolbox.main_window import MainWindow
from toolbox.paths import RESOURCES_DIR


def _load_stylesheet():
    path = os.path.join(RESOURCES_DIR, 'style.qss')
    with open(path, encoding='utf-8') as f:
        content = f.read()
    # QSS url() needs a real filesystem path, not one relative to an
    # unpredictable CWD -- substitute in the actual resources dir (already
    # resolved correctly for both source and frozen builds by paths.py).
    # Forward slashes: Qt's QSS parser accepts them on every platform,
    # including Windows, so no os.sep juggling needed here.
    icons_dir = os.path.join(RESOURCES_DIR, 'icons').replace(os.sep, '/')
    return content.replace('{ICONS_DIR}', icons_dir)


def _migrate_qsettings_org(old_org, new_org, app_name):
    """One-shot carry-over of QSettings saved under the pre-rename
    organization name to the post-rename one.

    QSettings keys its storage location off (organization, application) --
    changing the organization silently re-points every previously saved
    key (window geometry, every tool page's persisted form state) to an
    empty location: not a crash, just a one-time loss of remembered
    preferences on existing installs. This helper copies every key the
    new location doesn't already have from the old one, marks the
    migration done, and clears the old location so a stale copy can't
    resurface.

    Key-by-key "don't clobber" semantics: a user who already ran a
    new-org build and changed something there keeps the newer value over
    the pre-rename copy. Runs exactly once (the marker key short-circuits
    subsequent launches, so anything written to the old org afterwards --
    e.g. by running an old build again -- is deliberately left behind).

    Call it BEFORE the QApplication-wide setOrganizationName() switch and
    before any QSettings() is default-constructed (MainWindow reads its
    geometry in the constructor): QSettings binds its location at
    construction time, so the ordering here is load-bearing.

    Both instances are constructed as (defaultFormat(), UserScope, org,
    app) rather than with the plain (org, app) constructor: the two-arg
    form always uses NativeFormat and ignores QSettings.setDefaultFormat()
    entirely, so it would (a) desync from wherever the rest of the app
    reads/writes if a default format is ever set, and (b) escape the
    test suite's QSettings sandbox (conftest.py's _isolated_qsettings
    redirects setDefaultFormat()+setPath, which the two-arg constructor
    bypasses -- meaning migration tests would read/write the developer's
    real user config). Going through defaultFormat() keeps this helper
    on exactly the backend the app's default-constructed QSettings()
    calls resolve to, in production and under tests alike.
    """
    from PySide6.QtCore import QSettings

    fmt = QSettings.defaultFormat()
    new = QSettings(fmt, QSettings.UserScope, new_org, app_name)
    if new.value('settings_migrated_from_old_org', False, type=bool):
        return
    old = QSettings(fmt, QSettings.UserScope, old_org, app_name)
    old_keys = old.allKeys()
    if old_keys:
        new_keys = set(new.allKeys())
        for key in old_keys:
            if key not in new_keys:
                new.setValue(key, old.value(key))
    new.setValue('settings_migrated_from_old_org', True)
    new.sync()
    old.clear()
    old.sync()


def main():
    app = QApplication(sys.argv)
    # Carry over whatever was saved under the pre-rename organization
    # name, BEFORE the switch below re-points QSettings() -- see
    # _migrate_qsettings_org().
    _migrate_qsettings_org('language-tools', 'laelaps', 'toolbox')
    # QSettings() (used by MainWindow to remember window geometry across
    # launches) needs these set to know where to store its data -- without
    # them it falls back to a generic/unset scope that isn't guaranteed
    # stable across runs. The organization name now matches the repo name
    # (aREversez/laelaps); the old 'language-tools' location is carried
    # over once by _migrate_qsettings_org() so existing installs keep
    # their saved geometry and form state.
    app.setOrganizationName('laelaps')
    app.setApplicationName('toolbox')
    app.setStyleSheet(_load_stylesheet())
    app.setWindowIcon(QIcon(os.path.join(RESOURCES_DIR, 'logo.svg')))
    tooltips.install(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
