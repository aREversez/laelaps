"""Tests for ``toolbox.main._migrate_qsettings_org()`` -- the one-shot
carry-over of QSettings saved under the pre-rename organization name
('language-tools') to the post-rename one ('laelaps').

The repo rename (539a74d) deliberately deferred the QSettings
organization rename because re-pointing (organization, application)
orphaned every saved key -- window geometry plus every tool page's
persisted form state. The migration in toolbox/main.py is the deliberate
decision that followed; these tests pin its contract: copy without
clobbering newer values, run exactly once, empty the old location.

Every QSettings here is constructed as (defaultFormat(), UserScope,
org, app) -- the same form the migration helper itself uses -- and NEVER
as the plain two-arg QSettings(org, app): that form always uses
NativeFormat and bypasses conftest.py's _isolated_qsettings sandbox
(which redirects setDefaultFormat()+setPath), so two-arg instances
would read/write the developer's real user config mid-test.
"""

from PySide6.QtCore import QSettings

from toolbox.main import _migrate_qsettings_org

OLD_ORG = 'language-tools'
NEW_ORG = 'laelaps'
APP = 'toolbox'


def _qs(org):
    """QSettings for ``org`` on the same backend the helper resolves to."""
    return QSettings(QSettings.defaultFormat(), QSettings.UserScope, org, APP)


def test_migration_copies_saved_keys_and_clears_old_location():
    old = _qs(OLD_ORG)
    old.setValue('corpus_convert/src_lang', 'en-US')
    old.setValue('corpus_convert/chk_tmx', True)
    old.sync()

    _migrate_qsettings_org(OLD_ORG, NEW_ORG, APP)

    new = _qs(NEW_ORG)
    assert new.value('corpus_convert/src_lang', type=str) == 'en-US'
    assert new.value('corpus_convert/chk_tmx', type=bool) is True
    assert new.value('settings_migrated_from_old_org', False, type=bool) is True
    # The old location is emptied so a stale copy can't resurface later.
    assert _qs(OLD_ORG).allKeys() == []


def test_migration_is_a_noop_when_nothing_was_saved():
    _migrate_qsettings_org(OLD_ORG, NEW_ORG, APP)

    new = _qs(NEW_ORG)
    # Marker written even with nothing to carry over -- a fresh install
    # must not re-run the (harmless but pointless) old-org read forever.
    assert new.value('settings_migrated_from_old_org', False, type=bool) is True
    assert new.allKeys() == ['settings_migrated_from_old_org']


def test_migration_does_not_clobber_newer_values():
    # A user who already ran a new-org build keeps their newer values
    # over the pre-rename copy; only keys absent from the new location
    # are carried over.
    new = _qs(NEW_ORG)
    new.setValue('corpus_convert/src_lang', 'zh-CN')
    new.sync()

    old = _qs(OLD_ORG)
    old.setValue('corpus_convert/src_lang', 'en-US')
    old.setValue('qa_check/chk_numbers', True)
    old.sync()

    _migrate_qsettings_org(OLD_ORG, NEW_ORG, APP)

    new = _qs(NEW_ORG)
    assert new.value('corpus_convert/src_lang', type=str) == 'zh-CN'
    assert new.value('qa_check/chk_numbers', type=bool) is True


def test_migration_runs_only_once():
    old = _qs(OLD_ORG)
    old.setValue('corpus_convert/src_lang', 'en-US')
    old.sync()

    _migrate_qsettings_org(OLD_ORG, NEW_ORG, APP)

    # Something saved under the old org AFTER the migration (e.g. by
    # running an old build once more) must not get copied on the next
    # launch -- the marker short-circuits before the old org is read.
    old = _qs(OLD_ORG)
    old.setValue('corpus_convert/src_lang', 'fr-FR')
    old.sync()

    _migrate_qsettings_org(OLD_ORG, NEW_ORG, APP)

    new = _qs(NEW_ORG)
    assert new.value('corpus_convert/src_lang', type=str) == 'en-US'
