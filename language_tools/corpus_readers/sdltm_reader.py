"""Read a Trados Studio .sdltm file directly into TranslationUnit list.

Mirrors writers/sdltm_writer.py's schema; only touches source_segment/
target_segment (the <Segment><Elements><Text><Value> XML) plus guid/
timestamps for informational purposes. Doesn't touch source_hash/
target_hash/fuzzy_data -- see sdltm_writer.py's module docstring for why
those aren't meaningful to round-trip (private Trados hash algorithm,
Level 2 compatibility target).
"""
import re
import sqlite3

from language_tools.model import TranslationUnit
from language_tools.writers.sdltm_writer import unesc

_VALUE_RE = re.compile(r'<Value>(.*?)</Value>', re.S)
_CULTURE_RE = re.compile(r'<CultureName>(.*?)</CultureName>')


def _extract(seg_xml_text):
    if not seg_xml_text:
        return '', ''
    vm = _VALUE_RE.search(seg_xml_text)
    cm = _CULTURE_RE.search(seg_xml_text)
    text = unesc(vm.group(1)) if vm else ''
    lang = cm.group(1) if cm else ''
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
