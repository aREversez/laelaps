"""Pin the sdltm_writer's Level-1 schema baseline.

These are deliberately *conservative* pins, not correctness assertions: the
writer's DDL is schema fidelity to the real Trados format (see its module
docstring), so any change here must be an intentional, documented decision.

The FGA-gap test encodes the round-1 Studio 2024 finding
(compatibility/studio-readable.md, 2026-09-22): Studio's upLIFT/FGA upgrade
adds `translation_memories.fga_support` plus 6 other structures, and until
the writer emits them, every TM we produce will show Studio's "upgrade
available" prompt and cannot accept edited TUs. When the writer is upgraded
to emit the post-upgrade schema, update these pins deliberately in that
change — do not "fix" them here.
"""
import sqlite3

from language_tools.model import TranslationUnit
from language_tools.writers import sdltm_writer

# 13 tables in sdltm_writer.DDL (indexes are not tables)
WRITER_TABLES = {
    'translation_memories', 'translation_units', 'attributes', 'picklist_values',
    'picklist_attributes', 'string_attributes', 'numeric_attributes',
    'date_attributes', 'translation_unit_contexts', 'resources', 'tm_resources',
    'fuzzy_data', 'parameters',
}


def _write_minimal(tmp_path, name='pin.sdltm'):
    units = [TranslationUnit(src_lang='en-US', tgt_lang='zh-CN',
                             src_text='Hello.', tgt_text='你好。')]
    path = str(tmp_path / name)
    sdltm_writer.write(path, units, 'en-US', 'zh-CN', 'pin')
    return path


def _tables(path):
    con = sqlite3.connect(path)
    try:
        # sqlite_sequence is SQLite's own bookkeeping table for AUTOINCREMENT
        return {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")
            if r[0] != 'sqlite_sequence'}
    finally:
        con.close()


def _params(path):
    con = sqlite3.connect(path)
    try:
        return {r[0]: r[1] for r in con.execute('select name, value from parameters')}
    finally:
        con.close()


def _columns(path, table):
    con = sqlite3.connect(path)
    try:
        return [c[1] for c in con.execute(f'pragma table_info({table})')]
    finally:
        con.close()


def test_writer_emits_exactly_the_level1_table_set(tmp_path):
    path = _write_minimal(tmp_path)
    assert _tables(path) == WRITER_TABLES


def test_writer_version_parameter_is_806(tmp_path):
    # Studio 2024 keeps VERSION='8.06' even after a successful FGA upgrade
    # (verified 2026-09-23 against a Studio-upgraded fixture) — the upgrade
    # prompt is NOT driven by this value. Pinned so a future writer change
    # can't silently drift it.
    path = _write_minimal(tmp_path)
    assert _params(path) == {'VERSION': '8.06', 'FREQUENCYTOP': '1000',
                             'LAST_ANALYZE': '0'}


def test_writer_lacks_fga_structures_known_level2_gap(tmp_path):
    path = _write_minimal(tmp_path)
    # Gap found in Studio 2024 verification round 1 (2026-09-22):
    # a real Studio upgrade adds these; we don't emit them yet.
    assert 'fga_support' not in _columns(path, 'translation_memories')
    assert 'alignment_data' not in _columns(path, 'translation_units')
    assert 'translation_unit_fragments' not in _tables(path)
