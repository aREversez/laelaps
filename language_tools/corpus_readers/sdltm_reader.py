"""Read a Trados Studio .sdltm file directly into TranslationUnit list.

Mirrors writers/sdltm_writer.py's schema; only touches source_segment/
target_segment (the <Segment><Elements><Text><Value> XML) plus guid/
timestamps for informational purposes. Doesn't touch source_hash/
target_hash/fuzzy_data -- see sdltm_writer.py's module docstring for why
those aren't meaningful to round-trip (private Trados hash algorithm,
Level 2 compatibility target).

Uses a real XML parser (ElementTree) rather than a regex over the raw
Segment XML string. Two reasons, not just style preference:
1. Our own writer's hand-rolled ``unesc()`` only reverses the specific
   3-entity escaping our own ``esc()`` produces (&amp;/&lt;/&gt;) -- a
   *real* Trados-native .sdltm could contain other valid XML entities
   (e.g. numeric character references) that unesc() wouldn't decode
   correctly. ElementTree handles every valid XML entity per spec, not
   just the ones our own writer happens to produce.
2. A regex search for the first ``<Value>...</Value>`` is fragile if the
   Segment XML is ever nested/structured differently than our own writer's
   exact output shape (again: relevant for real Trados-native files this
   reader should also be able to open, not just our own round-trips).

Deliberately does NOT additionally call html.unescape() on the parsed
text -- ElementTree already fully decodes XML entities during parsing, so
an extra unescape pass double-decodes any text that legitimately contains
an entity-like substring (e.g. literal text "R&D output &lt; 5%" would
come back as "R&D output < 5%", silently corrupting content that was
never itself an escaped "<"). Confirmed via tests/test_corpus_readers.py's
adversarial literal-&lt; case, which an earlier draft with an added
html.unescape() call failed.
"""
import sqlite3
import xml.etree.ElementTree as ET

from language_tools.model import TranslationUnit


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _extract(seg_xml_text):
    if not seg_xml_text:
        return '', ''
    try:
        root = ET.fromstring(seg_xml_text)
    except ET.ParseError:
        return '', ''
    value_el = next((e for e in root.iter() if _local_name(e.tag) == 'Value'), None)
    culture_el = next((e for e in root.iter() if _local_name(e.tag) == 'CultureName'), None)
    text = (value_el.text or '') if value_el is not None else ''
    lang = (culture_el.text or '') if culture_el is not None else ''
    return text, lang


def read(path, **opts):
    con = sqlite3.connect(path)
    try:
        tm_row = con.execute(
            'SELECT source_language, target_language FROM translation_memories LIMIT 1'
        ).fetchone()
        tm_src_lang, tm_tgt_lang = tm_row if tm_row else ('', '')
        rows = con.execute(
            'SELECT guid, source_segment, target_segment, creation_date, change_date '
            'FROM translation_units'
        ).fetchall()
    finally:
        con.close()

    units = []
    for guid, src_seg, tgt_seg, created, changed in rows:
        src_text, src_lang = _extract(src_seg)
        tgt_text, tgt_lang = _extract(tgt_seg)
        units.append(TranslationUnit(
            src_lang=src_lang or tm_src_lang,
            tgt_lang=tgt_lang or tm_tgt_lang,
            src_text=src_text, tgt_text=tgt_text,
            guid=guid.hex() if isinstance(guid, (bytes, bytearray)) else guid,
            created_at=created, modified_at=changed,
            source_file=path,
        ))
    return units
