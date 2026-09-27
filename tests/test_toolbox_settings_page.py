from toolbox.tools.settings.page import SettingsPage


# ------------------------------------------------------- settings.py helpers

def test_default_output_dir_round_trips():
    from toolbox import settings
    assert settings.get_default_output_dir() == ''
    settings.set_default_output_dir('/some/dir')
    assert settings.get_default_output_dir() == '/some/dir'
    settings.set_default_output_dir('')
    assert settings.get_default_output_dir() == ''


def test_effective_start_dir_prefers_last_dir_then_global_default():
    from toolbox import settings
    settings.set_default_output_dir('/global')
    assert settings.effective_start_dir('/last') == '/last'
    assert settings.effective_start_dir('') == '/global'
    assert settings.effective_start_dir() == '/global'
    # no global default set -> exactly the old passthrough behavior
    settings.set_default_output_dir('')
    assert settings.effective_start_dir('') == ''


def test_record_recent_tool_dedups_caps_and_skips_home():
    from toolbox import settings
    settings.record_recent_tool('a')
    settings.record_recent_tool('b')
    settings.record_recent_tool('c')
    settings.record_recent_tool('d')  # caps at 3, drops oldest 'a'
    assert settings.get_recent_tools() == ['d', 'c', 'b']
    settings.record_recent_tool('d')  # re-use moves to front, no dup
    assert settings.get_recent_tools() == ['d', 'c', 'b']
    settings.record_recent_tool('home')  # home never recorded
    assert 'home' not in settings.get_recent_tools()


# ----------------------------------------------------------- registration

def test_settings_tool_is_registered_and_sorts_last():
    from toolbox import registry
    specs = sorted(registry.discover(), key=lambda s: s.order)
    assert specs[-1].id == 'settings'
    assert any(s.id == 'settings' for s in registry.discover())


# ------------------------------------------------------------- the page

def test_page_loads_persisted_default_output_dir(qtbot):
    from toolbox import settings
    settings.set_default_output_dir('/initial/dir')
    page = SettingsPage()
    qtbot.addWidget(page)
    assert page.output_dir_edit.text() == '/initial/dir'


def test_page_saves_edited_default_output_dir(qtbot):
    from toolbox import settings
    page = SettingsPage()
    qtbot.addWidget(page)
    page.output_dir_edit.setText('/new/dir')
    page._save_output_dir()
    assert settings.get_default_output_dir() == '/new/dir'


def test_page_browse_sets_and_persists_directory(qtbot, monkeypatch, tmp_path):
    from toolbox import settings
    from PySide6.QtWidgets import QFileDialog
    page = SettingsPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory',
                        lambda *a, **kw: str(tmp_path))
    page._browse_output_dir()
    assert page.output_dir_edit.text() == str(tmp_path)
    assert settings.get_default_output_dir() == str(tmp_path)


def test_page_browse_cancelled_leaves_value_untouched(qtbot, monkeypatch):
    from toolbox import settings
    from PySide6.QtWidgets import QFileDialog
    settings.set_default_output_dir('/keep')
    page = SettingsPage()
    qtbot.addWidget(page)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: '')
    page._browse_output_dir()
    assert page.output_dir_edit.text() == '/keep'
    assert settings.get_default_output_dir() == '/keep'
