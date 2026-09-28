"""UI internationalisation for the desktop toolbox.

Design in one paragraph: the source strings in the code are the original
Simplified Chinese (zh-CN) text, and ``tr(text)`` looks that exact text up
in the active language's catalog -- gettext-style, with the Chinese source
text as the message id. zh-CN therefore needs no catalog (``tr`` is the
identity), a missing entry falls back to English and then to the source
text (so a half-translated catalog degrades to English, never to a crash or
a blank label), and call sites stay readable: ``QPushButton(tr('开始检查'))``.
Everything here is deliberately Qt-free apart from ``install()`` /
``system_language()``, so the lookup itself is trivially unit-testable.

Rules for call sites:

* ``tr()`` takes a *literal*. It only looks text up; it never formats.
  Placeholders stay printf-style at the call site --
  ``tr('共 %d 条') % n`` -- and every translation must keep the same
  placeholders in the same order (tests/test_toolbox_i18n.py enforces it
  for every catalog).
* Text that is looked up later, at display time, rather than where it is
  written (labels owned by ``language_tools`` -- see ``library_labels.py``
  -- or a module-level table) is marked with ``tr_noop()`` where it is
  defined so the catalog check still sees it.
* The language is chosen once, at startup (``install()``), and changing it
  in 设置 takes effect on the next launch: pages build their text in their
  constructors and module-level tables (``LANG_CHOICES`` ...) are
  translated at import time, so ``main.py`` must call ``install()`` before
  importing anything from ``toolbox.main_window`` / ``toolbox.tools``.

Catalogs live in ``toolbox/resources/i18n/<code>.json`` as a flat
``{source text: translation}`` object. To add a language: drop in a
``<code>.json``, add its native name to ``LANGUAGES`` below, and let
``pytest tests/test_toolbox_i18n.py`` list what is still missing.
"""
import json
import os

from toolbox.paths import RESOURCES_DIR

SOURCE_LANGUAGE = 'zh-CN'
FALLBACK_LANGUAGE = 'en'
AUTO = 'auto'
I18N_DIR = os.path.join(RESOURCES_DIR, 'i18n')

# (code, native name) in the order the language picker lists them. Each
# language is shown in its own script so a person who can't read the
# current UI language can still find theirs. zh-CN is the source language
# and has no catalog file; every other code must have <code>.json.
LANGUAGES = (
    ('zh-CN', '简体中文'),
    ('zh-TW', '繁體中文'),
    ('en', 'English'),
    ('ja', '日本語'),
    ('ko', '한국어'),
    ('de', 'Deutsch'),
    ('fr', 'Français'),
    ('es', 'Español'),
    ('pt-BR', 'Português (Brasil)'),
    ('ru', 'Русский'),
)
_CODES = tuple(code for code, _ in LANGUAGES)

_language = SOURCE_LANGUAGE
_catalog = {}


def tr(text):
    """The active language's rendering of ``text`` (a zh-CN source string),
    or ``text`` itself when there is none."""
    return _catalog.get(text, text)


def tr_noop(text):
    """Marks ``text`` as translatable without translating it here -- for
    strings that are looked up with ``tr()`` later (see module docstring)."""
    return text


def load_catalog(code):
    """One language's ``{source: translation}`` dict; ``{}`` for the source
    language or a code without a catalog file."""
    if code == SOURCE_LANGUAGE:
        return {}
    path = os.path.join(I18N_DIR, '%s.json' % code)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def set_language(code):
    """Makes ``code`` the active language (unknown codes fall back to the
    source language). Returns the code actually activated."""
    global _language, _catalog
    if code not in _CODES:
        code = SOURCE_LANGUAGE
    catalog = {}
    if code not in (SOURCE_LANGUAGE, FALLBACK_LANGUAGE):
        catalog.update(load_catalog(FALLBACK_LANGUAGE))
    catalog.update(load_catalog(code))
    _language, _catalog = code, catalog
    return code


def current_language():
    return _language


def match_language(locale_name):
    """Maps a system locale / UI-language name (``zh_TW``, ``zh-Hant-HK``,
    ``pt_PT``, ``en_US`` ...) to the closest supported code; English when
    nothing fits."""
    parts = [p for p in locale_name.replace('_', '-').split('-') if p]
    if not parts:
        return FALLBACK_LANGUAGE
    lang, rest = parts[0].lower(), [p.upper() for p in parts[1:]]
    if lang == 'zh':
        traditional = 'HANT' in rest or any(r in ('TW', 'HK', 'MO') for r in rest)
        return 'zh-TW' if traditional else 'zh-CN'
    if lang == 'pt':
        return 'pt-BR'
    return lang if lang in _CODES else FALLBACK_LANGUAGE


def system_language():
    from PySide6.QtCore import QLocale
    locale = QLocale.system()
    ui = locale.uiLanguages()
    return match_language(ui[0] if ui else locale.name())


def default_choice(legacy_install):
    """What the language picker holds before anyone has chosen: follow the
    system -- except on an install that predates i18n, which has only ever
    seen Chinese and must not flip to English just because the OS locale
    isn't Chinese."""
    return SOURCE_LANGUAGE if legacy_install else AUTO


def resolve(choice):
    """A saved picker value (``'auto'`` or a language code) -> a code."""
    if choice == AUTO:
        return system_language()
    return choice if choice in _CODES else SOURCE_LANGUAGE


def install(app):
    """Startup hook, called once from ``main()`` right after the QApplication
    and its organization/application names exist and *before* any page
    module is imported. Resolves the saved choice (recording the default the
    first time, so a fresh install doesn't get mistaken for a pre-i18n one
    on its second launch), activates the catalog and loads Qt's own
    translations for its stock dialogs and menus (Open/Save/Cancel, Copy/
    Paste ...). Returns the active language code."""
    from PySide6.QtCore import QSettings

    from toolbox import settings

    choice = settings.get_ui_language()
    if not choice:
        legacy = QSettings().contains('mainWindow/geometry')
        choice = default_choice(legacy)
        settings.set_ui_language(choice)
    code = set_language(resolve(choice))
    _install_qt_translators(app, code)
    return code


def _install_qt_translators(app, code):
    if code != FALLBACK_LANGUAGE:  # Qt's own strings are English already
        _load_qt_translator(app, code.replace('-', '_'))


def _load_qt_translator(app, qt_code):
    """Best effort: Qt's qtbase_<code>.qm ships with the PySide6 wheel; if a
    build doesn't bundle it the stock dialogs simply stay English."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    dirs = [QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
    try:
        import PySide6
        dirs.append(os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'translations'))
    except ImportError:  # pragma: no cover
        pass
    for directory in dirs:
        translator = QTranslator(app)
        if translator.load('qtbase_%s' % qt_code, directory):
            app.installTranslator(translator)
            return translator
    return None
