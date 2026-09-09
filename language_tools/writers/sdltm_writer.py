"""Write a Trados Studio .sdltm translation memory (SQLite).

Compatibility target: **Level 2 — Studio-readable**, not Level 3.
Studio can open, browse, and edit a TM written by this module. The
``fuzzy_data`` table is deliberately left empty; Studio recomputes its own
fuzzy-match index the first time the TM is used (it is not designed to be
populated by third-party writers, and Trados' actual per-segment hashing
algorithm for that index is private/undocumented). ``source_hash`` /
``target_hash`` here are a deterministic FNV-1a64 stand-in good enough for
this writer's own bookkeeping, not a reproduction of Trados' real hash.

DDL and insert logic are unchanged from the seed script -- this is schema
fidelity to the real Trados format, not something to improve on without a
concrete, tested reason.
"""
import datetime
import os
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
\ttucount INT NOT NULL DEFAULT 0)""",
    """CREATE TABLE translation_units(
\tid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, guid BLOB NOT NULL,
\ttranslation_memory_id INT NOT NULL CONSTRAINT FK_tu_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
\tsource_hash INTEGER NOT NULL, source_segment TEXT, target_hash INTEGER NOT NULL,
\ttarget_segment TEXT, creation_date DATETIME NOT NULL, creation_user TEXT NOT NULL,
\tchange_date DATETIME NOT NULL, change_user TEXT NOT NULL,
\tlast_used_date DATETIME NOT NULL, last_used_user TEXT NOT NULL,
\tusage_counter INT NOT NULL, flags INT)""",
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


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def unesc(t):
    return t.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


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
    con.execute('INSERT INTO attributes(guid,name,type,tm_id) VALUES(?,?,?,?)',
                (uuid.uuid4().bytes, 'StructureContext', 2, 1))
    n = 0
    for u in units:
        src_text, tgt_text = u.src_text.strip(), u.tgt_text.strip()
        if not src_text or not tgt_text:
            continue
        con.execute('INSERT INTO translation_units(guid,translation_memory_id,source_hash,'
                    'source_segment,target_hash,target_segment,creation_date,creation_user,'
                    'change_date,change_user,last_used_date,last_used_user,usage_counter,flags) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().bytes, 1, fnv1a64(src_text), seg_xml(src_text, src_lang),
                     fnv1a64(tgt_text), seg_xml(tgt_text, tgt_lang), now, 'laelaps', now, 'laelaps',
                     now, 'laelaps', 0, 131073))
        n += 1
    con.execute('UPDATE translation_memories SET tucount=? WHERE id=1', (n,))
    con.commit()
    con.execute('VACUUM')
    con.close()
    return n
