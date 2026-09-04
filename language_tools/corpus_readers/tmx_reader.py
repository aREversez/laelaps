"""Read a TMX file directly into TranslationUnit list.

Corpus readers skip the align step bilingual-file readers require (see
DESIGN.md section 1): a TMX <tu> is already one aligned sentence pair.
ElementTree handles entity decoding for free, same reasoning as the
_ooxml.py rewrite in Phase 1.
"""
import xml.etree.ElementTree as ET

from language_tools.model import TranslationUnit

_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


def _tuv_lang(tuv):
    return tuv.get(_XML_LANG) or tuv.get('lang') or ''


def _tuv_text(tuv):
    seg = tuv.find('seg')
    return (seg.text or '').strip() if seg is not None else ''


def read(path, **opts):
    root = ET.parse(path).getroot()
    body = root.find('body')
    if body is None:
        return []

    units = []
    for tu in body.findall('tu'):
        tuvs = tu.findall('tuv')
        if len(tuvs) < 2:
            continue
        # TMX technically allows >2 tuv per tu (multilingual TMs); this
        # project is bilingual-only, so only the first two are used.
        src_tuv, tgt_tuv = tuvs[0], tuvs[1]
        units.append(TranslationUnit(
            src_lang=_tuv_lang(src_tuv), tgt_lang=_tuv_lang(tgt_tuv),
            src_text=_tuv_text(src_tuv), tgt_text=_tuv_text(tgt_tuv),
            created_at=tu.get('creationdate'), source_file=path,
        ))
    return units
