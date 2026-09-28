"""Catalog completeness / consistency guard for toolbox/resources/i18n/*.json.

Runs against the source tree directly (ast, not import) so it also catches
new tr()/tr_noop() calls before anyone remembers to update the catalogs.
"""
import ast
import glob
import json
import re

import pytest

from toolbox import i18n

PLACEHOLDER = re.compile(r'%(?:\([^)]*\))?[#0\- +]*(?:\d+|\*)?(?:\.\d+)?[hlL]?[diouxXeEfFgGcrsa%]')
BRACE = re.compile(r'\{[^}]*\}')
NON_SOURCE_LANGS = [code for code, _ in i18n.LANGUAGES if code != i18n.SOURCE_LANGUAGE]


def _source_keys():
    """Every literal passed to tr()/tr_noop() across toolbox/, in source
    order. A non-literal argument (a dynamic tr() call on a value that isn't
    a string constant) is an error here: it can't be covered by a static
    catalog, and the call site should instead list its possible values with
    tr_noop() (see toolbox/library_labels.py) so this scan can see them."""
    keys = []
    for path in sorted(glob.glob('toolbox/**/*.py', recursive=True)):
        if path == 'toolbox/i18n.py':
            continue
        tree = ast.parse(open(path, encoding='utf-8').read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ('tr', 'tr_noop') and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.append(arg.value)
                elif isinstance(arg, ast.Call):
                    # tr(align_report.move_label(code)) / tr(ISSUE_LABELS.get(...))
                    # -- a lookup of a library-owned label, not a literal. Its
                    # possible values are covered by test_library_labels_are_registered
                    # instead of by this literal scan.
                    continue
                else:
                    pytest.fail(
                        'Non-literal tr()/tr_noop() argument at %s:%d -- catalog '
                        'coverage can only be checked for literal source strings. '
                        'List the possible values with tr_noop() instead (see '
                        'toolbox/library_labels.py) and look them up with tr().'
                        % (path, node.lineno)
                    )
    return keys


SOURCE_KEYS = sorted(set(_source_keys()))


def test_library_labels_are_registered():
    """Guards the other end of the tr_noop() escape hatch above: every label
    language_tools can hand back (MOVE_LABELS, ISSUE_LABELS) must be listed
    in toolbox/library_labels.py, or a translator would never see it and a
    checked-in call site (align_report.move_label(code), ISSUE_LABELS.get(...))
    would silently render in Chinese in every other language."""
    from language_tools.align.aligner import MOVE_LABELS
    from language_tools.qa import ISSUE_LABELS
    from toolbox.library_labels import LIBRARY_LABELS

    registered = set(LIBRARY_LABELS)
    missing = (set(MOVE_LABELS.values()) | set(ISSUE_LABELS.values())) - registered
    assert not missing, 'Labels missing from toolbox/library_labels.py: %r' % sorted(missing)


@pytest.mark.parametrize('lang', NON_SOURCE_LANGS)
def test_catalog_covers_every_source_string(lang):
    catalog = i18n.load_catalog(lang)
    missing = [k for k in SOURCE_KEYS if k not in catalog]
    assert not missing, '%s catalog is missing %d/%d source strings, e.g. %r' % (
        lang, len(missing), len(SOURCE_KEYS), missing[:5])


@pytest.mark.parametrize('lang', NON_SOURCE_LANGS)
def test_catalog_has_no_orphaned_entries(lang):
    """An entry with no matching source string is either stale (the source
    text changed and this wasn't updated) or was never reachable -- either
    way it's a maintenance trap, so the catalogs are kept exactly in step
    with the source."""
    catalog = i18n.load_catalog(lang)
    source_set = set(SOURCE_KEYS)
    orphaned = [k for k in catalog if k not in source_set]
    assert not orphaned, '%s catalog has %d orphaned entries, e.g. %r' % (
        lang, len(orphaned), orphaned[:5])


@pytest.mark.parametrize('lang', NON_SOURCE_LANGS)
def test_catalog_values_are_nonempty_and_distinct_from_key(lang):
    catalog = i18n.load_catalog(lang)
    for key, value in catalog.items():
        assert value.strip(), 'empty translation for %r in %s' % (key, lang)


@pytest.mark.parametrize('lang', NON_SOURCE_LANGS)
def test_catalog_placeholders_match_source(lang):
    """A translation that drops, reorders, or mistypes a %s/%d/{name}
    placeholder crashes the call site's ``%`` formatting at runtime --
    checked here so it's caught before it ships, not when a user hits it."""
    catalog = i18n.load_catalog(lang)
    bad = []
    for key, value in catalog.items():
        if PLACEHOLDER.findall(value) != PLACEHOLDER.findall(key) or \
                BRACE.findall(value) != BRACE.findall(key):
            bad.append(key)
    assert not bad, '%s catalog has placeholder mismatches, e.g. %r' % (lang, bad[:5])


def test_zh_cn_and_zh_tw_are_distinct_languages():
    """zh-TW is meant to be actual Traditional Chinese, not the zh-CN source
    text copied verbatim -- this would silently pass every other check here."""
    catalog = i18n.load_catalog('zh-TW')
    han = re.compile(r'[\u4e00-\u9fff]')
    # Restrict to keys that actually contain Chinese characters: punctuation-
    # or format-only strings (e.g. '%s（%d）', '、') are legitimately
    # identical in zh-CN and zh-TW and would otherwise dilute the check.
    han_keys = [k for k in SOURCE_KEYS if han.search(k)]
    identical = [k for k in han_keys if catalog.get(k) == k]
    # Many common words (原文, 分析, 重 ...) use characters that are
    # unchanged between Simplified and Traditional, so a real translation
    # still leaves a meaningful fraction byte-identical; only a much higher
    # rate indicates the catalog was left untranslated.
    assert len(identical) < len(han_keys) * 0.15, (
        'zh-TW catalog looks untranslated: %d/%d entries are byte-identical '
        'to the zh-CN source' % (len(identical), len(han_keys)))


def test_match_language_maps_common_locales():
    cases = {
        'zh_CN': 'zh-CN', 'zh-Hans-CN': 'zh-CN', 'zh_TW': 'zh-TW',
        'zh-Hant-TW': 'zh-TW', 'zh-HK': 'zh-TW', 'en_US': 'en',
        'en-GB': 'en', 'ja_JP': 'ja', 'ko-KR': 'ko', 'de_DE': 'de',
        'fr-FR': 'fr', 'es_MX': 'es', 'pt_BR': 'pt-BR', 'pt_PT': 'pt-BR',
        'ru_RU': 'ru', 'it_IT': 'en', '': 'en',
    }
    for locale_name, expected in cases.items():
        assert i18n.match_language(locale_name) == expected, locale_name


def test_set_language_falls_back_to_english_for_missing_key():
    i18n.set_language('de')
    try:
        assert i18n.tr('This string will never exist in any catalog xyz') == \
            'This string will never exist in any catalog xyz'
    finally:
        i18n.set_language(i18n.SOURCE_LANGUAGE)


def test_resolve_and_default_choice():
    assert i18n.resolve('not-a-real-code') == i18n.SOURCE_LANGUAGE
    assert i18n.resolve('ja') == 'ja'
    assert i18n.default_choice(legacy_install=True) == i18n.SOURCE_LANGUAGE
    assert i18n.default_choice(legacy_install=False) == i18n.AUTO


def test_tr_is_identity_for_source_language():
    i18n.set_language(i18n.SOURCE_LANGUAGE)
    assert i18n.tr('任何字符串') == '任何字符串'


def test_json_catalogs_load_cleanly():
    for code, _ in i18n.LANGUAGES:
        if code == i18n.SOURCE_LANGUAGE:
            continue
        with open('toolbox/resources/i18n/%s.json' % code, encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, dict) and data
