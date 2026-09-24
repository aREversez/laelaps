"""Pin the sdltm_writer's Level-1 schema baseline.

These are deliberately *conservative* pins, not correctness assertions: the
writer's DDL is schema fidelity to the real Trados format (see its module
docstring), so any change here must be an intentional, documented decision.

Baseline updated 2026-09-24 after the round-2/3 Studio findings
(compatibility/studio-readable.md): the writer now emits the full
post-FGA-upgrade schema (fga_support flag, FGA columns/tables/parameters)
so Studio accepts edits without a successful upgrade. If these pins ever
fail, check the schema research in that ledger before changing either the
writer or the test.
"""
import sqlite3

from language_tools.model import TranslationUnit
from language_tools.writers import sdltm_writer

# 20 tables in sdltm_writer.DDL: the original 13 + 7 FGA/upLIFT structures
WRITER_TABLES = {
    'translation_memories', 'translation_units', 'attributes', 'picklist_values',
    'picklist_attributes', 'string_attributes', 'numeric_attributes',
    'date_attributes', 'translation_unit_contexts', 'resources', 'tm_resources',
    'fuzzy_data', 'parameters',
    'translation_unit_fragments', 'translation_unit_idcontexts',
    'trans_model', 'trans_model_rev', 'vocab_src', 'vocab_trg', 'vocabfilter',
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


def test_writer_emits_exactly_the_level1_table_set(tmp_path):
    path = _write_minimal(tmp_path)
    assert _tables(path) == WRITER_TABLES


def test_writer_version_parameter_is_806(tmp_path):
    # Studio 2024 keeps VERSION='8.06' even after a successful FGA upgrade
    # (verified 2026-09-23 against a Studio-upgraded fixture) — the upgrade
    # prompt is NOT driven by this value. Pinned so a future writer change
    # can't silently drift it. The three NULL-tm_id FGA markers are what
    # Studio's upgrade writes; TranslationModelName/Version must stay
    # absent (no model built — see writer comment on the round-3 fixture
    # poisoning).
    path = _write_minimal(tmp_path)
    assert _params(path) == {'VERSION': '8.06', 'FREQUENCYTOP': '1000',
                             'LAST_ANALYZE': '0',
                             'TokenDataVersion': '1',
                             'AlignmentDataVersion': '1',
                             'VERSION_CREATED': '8.12'}


def test_writer_emits_post_fga_upgrade_schema(tmp_path):
    path = _write_minimal(tmp_path)
    # Round-2/3 fix: Studio treats these structures (even empty) as
    # "upgraded" and commits TU edits against them.
    con = sqlite3.connect(path)
    try:
        assert con.execute(
            'select fga_support from translation_memories').fetchone()[0] == 1
        tu_cols = {c[1] for c in con.execute('pragma table_info(translation_units)')}
    finally:
        con.close()
    assert {'source_token_data', 'target_token_data', 'alignment_data',
            'fragment_hash'} <= tu_cols
    assert 'translation_unit_fragments' in _tables(path)
