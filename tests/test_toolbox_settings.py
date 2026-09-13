from toolbox import settings


def test_get_str_returns_default_when_key_unset():
    assert settings.get_str('nope/key', 'fallback') == 'fallback'


def test_get_bool_returns_default_when_key_unset():
    assert settings.get_bool('nope/key', True) is True
    assert settings.get_bool('nope/key2', False) is False


def test_str_round_trips():
    settings.set_value('test/str', 'hello 世界')
    assert settings.get_str('test/str') == 'hello 世界'


def test_bool_round_trips_as_actual_bool_not_string():
    # get_bool() passes type=bool defensively (see toolbox/settings.py's
    # module docstring for why -- Qt documents .value()'s type coercion
    # as backend-dependent, though empirically this project's actual
    # PySide6/Qt version already gets it right on the INI backend these
    # tests run under even without the hint). This test pins the
    # contract get_bool() promises regardless of backend quirks: real
    # Python bools out, not truthy strings.
    settings.set_value('test/boolTrue', True)
    settings.set_value('test/boolFalse', False)
    assert settings.get_bool('test/boolTrue') is True
    assert settings.get_bool('test/boolFalse') is False


def test_bool_default_only_applies_when_key_missing():
    settings.set_value('test/explicitFalse', False)
    assert settings.get_bool('test/explicitFalse', default=True) is False
    assert settings.get_bool('test/neverSet', default=True) is True
