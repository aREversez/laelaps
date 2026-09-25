"""Write a Trados Studio .sdltm translation memory (SQLite).

Compatibility target: **Level 2 — Studio-readable**, not Level 3.
Studio can open, browse, and edit a TM written by this module. Since the
round-2/3 findings (compatibility/studio-readable.md) the DDL emits the
**post-FGA-upgrade schema** — `fga_support`/`data_version`/
`text_context_match_type`/`id_context_match` on `translation_memories`,
the 9 FGA columns on `translation_units`, the 7 fragment/model tables, and
the `TokenDataVersion`/`AlignmentDataVersion`/`VERSION_CREATED`
parameters — all captured verbatim from a Studio-2024-upgraded fixture.
That state is what Studio accepts as fully upgraded: TU edits commit
normally (verified at 1000 TUs with empty FGA tables), so the writer does
not need to fabricate Trados-private token/model data (upgraded TUs keep
those NULL until Studio itself edits a row).

Caveats that remain Studio-side, not writer bugs: the "An upgrade is
available" prompt on File → Open Translation Memory appears even for
fully-upgraded TMs (confirmed against a Studio-upgraded native fixture),
and clicking Yes on a ≥1,000-TU TM still dies in "Build Translation
Model" ("The TM does not support FGA") — advise clicking No; commits
work regardless once this schema is present. The round-5 native-control
comparison proved that step validates Trados-private per-TU computation
(real segment hash / tokenization / fragment state): the Level 3
boundary, unreachable from a third-party writer.

The ``fuzzy_data`` table is deliberately left empty; Studio recomputes its
own fuzzy-match index the first time the TM is used (it is not designed to
be populated by third-party writers, and Trados' actual per-segment
hashing algorithm for that index is private/undocumented).
``source_hash`` / ``target_hash`` here are a deterministic FNV-1a64
stand-in good enough for this writer's own bookkeeping, not a reproduction
of Trados' real hash.
"""
import datetime
import os
import re
import sqlite3
import uuid

DDL = [
    """CREATE TABLE translation_memories(
\tid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, guid BLOB NOT NULL,
\tname TEXT NOT NULL UNIQUE, source_language TEXT NOT NULL,
\ttarget_language TEXT NOT NULL, copyright TEXT, description TEXT,
\tsettings INT NOT NULL, creation_user TEXT NOT NULL,
\tcreation_date DATETIME NOT NULL, expiration_date DATETIME,
\tfuzzy_indexes INT NOT NULL, last_recompute_date DATETIME,
\tlast_recompute_size INT, flags INT NOT NULL DEFAULT 0,
\ttucount INT NOT NULL DEFAULT 0, fga_support int not null default 1,
\tdata_version INTEGER NOT NULL DEFAULT 1,
\ttext_context_match_type INTEGER NOT NULL DEFAULT 1,
\tid_context_match BIT DEFAULT 0)""",
    """CREATE TABLE translation_units(
\tid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, guid BLOB NOT NULL,
\ttranslation_memory_id INT NOT NULL CONSTRAINT FK_tu_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
\tsource_hash INTEGER NOT NULL, source_segment TEXT, target_hash INTEGER NOT NULL,
\ttarget_segment TEXT, creation_date DATETIME NOT NULL, creation_user TEXT NOT NULL,
\tchange_date DATETIME NOT NULL, change_user TEXT NOT NULL,
\tlast_used_date DATETIME NOT NULL, last_used_user TEXT NOT NULL,
\tusage_counter INT NOT NULL, flags INT,
\tsource_token_data BLOB, target_token_data BLOB, alignment_data BLOB,
\talign_model_date DATETIME, insert_date DATETIME, tokenization_sig_hash INTEGER,
\tsource_tags BLOB, target_tags BLOB, fragment_hash integer)""",
    """CREATE TABLE attributes(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
\tguid BLOB NOT NULL, name TEXT NOT NULL, type INT NOT NULL, tm_id INT NOT NULL,
CONSTRAINT CK_a UNIQUE (name, tm_id))""",
    """CREATE TABLE picklist_values(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
\tguid BLOB NOT NULL, attribute_id INT NOT NULL CONSTRAINT FK_pv_a REFERENCES attributes(id) ON DELETE CASCADE,
\tvalue TEXT NOT NULL)""",
    """CREATE TABLE picklist_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_pa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tpicklist_value_id INT NOT NULL CONSTRAINT FK_pa_pv REFERENCES picklist_values(id) ON DELETE CASCADE)""",
    """CREATE TABLE string_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_sa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tattribute_id INT NOT NULL CONSTRAINT FK_sa_a REFERENCES attributes(id) ON DELETE CASCADE, value TEXT NOT NULL)""",
    """CREATE TABLE numeric_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_na_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tattribute_id INT NOT NULL CONSTRAINT FK_na_a REFERENCES attributes(id) ON DELETE CASCADE, value INT NOT NULL)""",
    """CREATE TABLE date_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_da_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tattribute_id INT NOT NULL CONSTRAINT FK_da_a REFERENCES attributes(id) ON DELETE CASCADE, value DATETIME NOT NULL)""",
    """CREATE TABLE translation_unit_contexts(translation_unit_id INT NOT NULL CONSTRAINT FK_tuc_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tleft_source_context INTEGER NOT NULL, left_target_context INTEGER NOT NULL,
CONSTRAINT PK_tuc PRIMARY KEY (translation_unit_id, left_source_context, left_target_context))""",
    """CREATE TABLE resources(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
\tguid BLOB NOT NULL, type INT NOT NULL, language TEXT, data BLOB NOT NULL)""",
    """CREATE TABLE tm_resources(tm_id INT NOT NULL CONSTRAINT FK_tr_t REFERENCES translation_memories(id) ON DELETE CASCADE,
\tresource_id INT NOT NULL CONSTRAINT FK_tr_r REFERENCES resources(id) ON DELETE CASCADE,
CONSTRAINT PK_tr PRIMARY KEY (tm_id, resource_id))""",
    """CREATE TABLE fuzzy_data(translation_memory_id INT NOT NULL CONSTRAINT FK_fi1_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
\ttranslation_unit_id INT NOT NULL, fi1 TEXT, fi2 TEXT, fi4 TEXT, fi8 TEXT,
CONSTRAINT PK_fi1 PRIMARY KEY (translation_memory_id, translation_unit_id))""",
    """CREATE TABLE parameters(translation_memory_id INT NULL CONSTRAINT FK_p_tm REFERENCES translation_memories ON DELETE CASCADE,
\tname TEXT NOT NULL, value TEXT NOT NULL)""",
    # --- FGA / upLIFT structures, verbatim from a Studio 2024-upgraded TM
    # (round-2 schema research, compatibility/studio-readable.md). Studio
    # treats their presence — even fully empty — as "upgraded".
    """CREATE TABLE translation_unit_fragments(translation_unit_id INT NOT NULL
\tCONSTRAINT FK_tuf_tu REFERENCES translation_units(id) ON DELETE CASCADE,
\tfragment_hash INTEGER NOT NULL)""",
    """CREATE TABLE translation_unit_idcontexts(
\ttranslation_unit_id INT NOT NULL
\t\tCONSTRAINT FK_translation_unit_idcontexts REFERENCES translation_units(id) ON DELETE CASCADE,
\tidcontext TEXT NOT NULL,
\tCONSTRAINT PK_tuidc PRIMARY KEY (translation_unit_id, idcontext))""",
    """CREATE TABLE trans_model(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
\tsourcekey INTEGER NOT NULL, targetkey INTEGER NOT NULL, floatval REAL NOT NULL)""",
    """CREATE TABLE trans_model_rev(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
\tsourcekey INTEGER NOT NULL, targetkey INTEGER NOT NULL, floatval REAL NOT NULL)""",
    """CREATE TABLE vocab_src(id INT NOT NULL, vocab TEXT NOT NULL, freq INT NOT NULL)""",
    """CREATE TABLE vocab_trg(id INT NOT NULL, vocab TEXT NOT NULL, freq INT NOT NULL)""",
    """CREATE TABLE vocabfilter(token TEXT NOT NULL)""",
    "CREATE INDEX idx_Resources1 ON resources (type, language)",
    "CREATE INDEX idx_Resources2 ON resources (id)",
    "CREATE INDEX idx_attributes1 ON attributes (tm_id)",
    "CREATE INDEX idx_attributes2 ON attributes (name, type)",
    "CREATE INDEX idx_date_attributes ON date_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_numeric_attributes ON numeric_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_picklist_attributes ON picklist_attributes (translation_unit_id)",
    "CREATE INDEX idx_string_attributes ON string_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_tus_hashes ON translation_units(translation_memory_id, source_hash, target_hash)",
    "CREATE INDEX p_main ON parameters(translation_memory_id, name)",
    "CREATE INDEX idx_tufragments_ids ON translation_unit_fragments(translation_unit_id)",
    "CREATE INDEX idx_tufragments_hashes ON translation_unit_fragments(fragment_hash)",
    "CREATE INDEX idx_tus_idcontexts ON translation_unit_idcontexts(translation_unit_id, idcontext)",
    "CREATE INDEX idx_trans_model_sourcekey ON trans_model (sourcekey)",
    "CREATE INDEX idx_trans_model_targetkey ON trans_model (targetkey)",
    "CREATE INDEX idx_trans_model_rev_sourcekey ON trans_model_rev (sourcekey)",
    "CREATE INDEX idx_trans_model_rev_targetkey ON trans_model_rev (targetkey)",
    "CREATE INDEX idx_vocab_src ON vocab_src (vocab)",
    "CREATE INDEX idx_vocab_trg ON vocab_trg (vocab)",
    "CREATE INDEX idx_vocabfilter ON vocabfilter (token)",
]


def s64(x):
    return x - (1 << 64) if x >= (1 << 63) else x


def fnv1a64(text):
    """Deterministic stand-in for Trados' private (stemming-based) segment hash."""
    h = 0xcbf29ce484222325
    for b in text.encode('utf-8'):
        h ^= b
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return s64(h)


# XML 1.0 forbids #x00-#x08, #x0B, #x0C, #x0E-#x1F outright -- no entity,
# no escaping makes them legal. Leaving one in a <Segment> Value writes a
# file that is not XML at all: Studio/SQLite won't notice (the text is a
# plain column), but tmx_reader's ET.parse dies on the whole file and our
# own sdltm_reader's per-segment parse silently yields '' (raw control
# bytes survive esc()'s 3-entity escaping untouched -- hand-built TMX/
# SDLTM exports and Excel/CSV round-trips really do carry them).
# Replaced with U+FFFD rather than dropped: losing one can flip meaning
# ("line\x0cbreak" vs "linebreak"), a visible replacement marker cannot.
_ILLEGAL_XML_CHARS_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')


def esc(t):
    return _ILLEGAL_XML_CHARS_RE.sub('\ufffd',
                                     t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def unesc(t):
    return t.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


# Timestamp strings reach a writer from two places with two different
# shapes: an SDLTM column ('2024-01-05 08:09:10') or a TMX attribute
# ('20240105T080910Z'). Writers must re-render the *instant* into their
# own format rather than stamp datetime.now() over it -- otherwise a
# round-trip silently resets every TU's provenance (P0-4 of the 2026-09
# fix list). Anything unrecognized falls back to the caller's default.
_INPUT_TS_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%SZ',
    '%Y-%m-%dT%H:%M:%S%z',
    '%Y-%m-%dT%H:%M:%S.%f',
    '%Y%m%dT%H%M%SZ',
)


def normalize_ts(value, out_fmt, fallback):
    if not value:
        return fallback
    s = str(value).strip()
    if not s:
        return fallback
    for fmt in _INPUT_TS_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).strftime(out_fmt)
        except ValueError:
            continue
    return fallback


def seg_xml(text, culture):
    return ('<Segment xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><Elements><Text><Value>%s</Value>'
            '</Text></Elements><CultureName>%s</CultureName></Segment>' % (esc(text), culture))


def write(path, units, src_lang, tgt_lang, name):
    """list[TranslationUnit] -> .sdltm file. Returns the number of TUs written."""
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.execute('pragma page_size=8192')
    con.execute('pragma encoding="UTF-8"')
    for d in DDL:
        con.execute(d)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con.execute('INSERT INTO translation_memories(guid,name,source_language,target_language,'
                'copyright,description,settings,creation_user,creation_date,expiration_date,'
                'fuzzy_indexes,last_recompute_date,last_recompute_size,flags,tucount) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().bytes, name, src_lang, tgt_lang, None, None, 127,
                 'laelaps', now, '9999-12-31 23:59:59', 9, None, None, 0, 0))
    for k, v in (('VERSION', '8.06'), ('FREQUENCYTOP', '1000'), ('LAST_ANALYZE', '0')):
        con.execute('INSERT INTO parameters VALUES(?,?,?)', (1, k, v))
    # FGA-era markers written by Studio's upgrade; NULL tm_id as observed.
    # Deliberately NOT writing TranslationModelName/Version — those appear
    # only when a model is actually built, and a half-populated model is
    # what poisoned the round-3 manual fixture ("only supports 1
    # translation model").
    for k, v in (('TokenDataVersion', '1'), ('AlignmentDataVersion', '1'),
                 ('VERSION_CREATED', '8.12')):
        con.execute('INSERT INTO parameters VALUES(?,?,?)', (None, k, v))
    con.execute('INSERT INTO attributes(guid,name,type,tm_id) VALUES(?,?,?,?)',
                (uuid.uuid4().bytes, 'StructureContext', 2, 1))
    n = 0
    for u in units:
        src_text, tgt_text = u.src_text.strip(), u.tgt_text.strip()
        if not src_text or not tgt_text:
            continue
        created = normalize_ts(getattr(u, 'created_at', None), '%Y-%m-%d %H:%M:%S', now)
        changed = normalize_ts(getattr(u, 'modified_at', None), '%Y-%m-%d %H:%M:%S', created)
        con.execute('INSERT INTO translation_units(guid,translation_memory_id,source_hash,'
                    'source_segment,target_hash,target_segment,creation_date,creation_user,'
                    'change_date,change_user,last_used_date,last_used_user,usage_counter,flags) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().bytes, 1, fnv1a64(src_text), seg_xml(src_text, src_lang),
                     fnv1a64(tgt_text), seg_xml(tgt_text, tgt_lang), created, 'laelaps', changed, 'laelaps',
                     now, 'laelaps', 0, 131073))
        n += 1
    con.execute('UPDATE translation_memories SET tucount=? WHERE id=1', (n,))
    con.commit()
    con.execute('VACUUM')
    con.close()
    return n
