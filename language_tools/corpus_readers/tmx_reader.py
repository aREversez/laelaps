"""Read a TMX file directly into TranslationUnit list.

Corpus readers skip the align step bilingual-file readers require (see
DESIGN.md section 1): a TMX <tu> is already one aligned sentence pair.
ElementTree handles entity decoding for free, same reasoning as the
_ooxml.py rewrite in Phase 1.

Two real interop bugs fixed here, both confirmed empirically before
landing (not just reasoned about) -- real-world TMX exports from other
CAT tools hit both:

1. Plain ``root.find('body')``/``tu.findall('tu')`` etc. only match an
   unqualified tag name, which silently returns nothing at all if the TMX
   declares a default XML namespace (some tools' exports do). Confirmed:
   a namespaced TMX round-tripped through this reader produced zero
   units. Fixed by matching on local tag name (stripping any ``{ns}``
   prefix) instead of assuming no namespace.
2. ``seg.text`` only captures the text node immediately before the first
   child element -- any text inside or after an inline tag (``<bpt>``,
   ``<ept>``, ``<ph>``, ``<hi>``, all common in real TMX for placeholders/
   formatting) was silently dropped. Confirmed: "Click <b>OK</b> to
   continue." round-tripped to just "Click". Fixed with
   ``''.join(seg.itertext())``, which recursively flattens all text in
   document order regardless of nesting -- simpler and more complete than
   manually walking direct children only. This still discards the
   markup structure itself (only the visible text survives); preserving
   it properly belongs in a future tagged IR, per the QA layer's existing
   tag-handling scope note in DESIGN.md section 9.
"""
import xml.etree.ElementTree as ET

from language_tools.model import TranslationUnit

_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _tuv_lang(tuv):
    return tuv.get(_XML_LANG) or tuv.get('lang') or ''


def _tuv_text(tuv):
    seg = next((c for c in tuv if _local_name(c.tag) == 'seg'), None)
    if seg is None:
        return ''
    return ''.join(seg.itertext()).strip()


def read(path, src_lang=None, tgt_lang=None, **opts):
    """``src_lang``/``tgt_lang`` (optional): if given, each ``<tu>``'s tuv
    is matched by language code (case-insensitive) instead of blindly
    taking the first two -- needed for a TMX with more than two languages,
    or where tuv order doesn't happen to match the wanted direction. Falls
    back to positional (first two tuv) when not given, unchanged from
    before. Wired through from api.convert()'s own src_lang/tgt_lang
    arguments when both are given (see api.py).
    """
    root = ET.parse(path).getroot()
    body = next((c for c in root if _local_name(c.tag) == 'body'), None)
    if body is None:
        return []

    units = []
    skipped_lang_mismatch = 0
    for tu in body:
        if _local_name(tu.tag) != 'tu':
            continue
        tuvs = [c for c in tu if _local_name(c.tag) == 'tuv']
        if len(tuvs) < 2:
            continue

        if src_lang and tgt_lang:
            src_tuv = next((t for t in tuvs if _tuv_lang(t).lower() == src_lang.lower()), None)
            tgt_tuv = next((t for t in tuvs if _tuv_lang(t).lower() == tgt_lang.lower()), None)
            if src_tuv is None or tgt_tuv is None:
                skipped_lang_mismatch += 1
                continue
        else:
            # TMX technically allows >2 tuv per tu (multilingual TMs); with
            # no language hint to match against, fall back to the first two.
            src_tuv, tgt_tuv = tuvs[0], tuvs[1]

        units.append(TranslationUnit(
            src_lang=_tuv_lang(src_tuv), tgt_lang=_tuv_lang(tgt_tuv),
            src_text=_tuv_text(src_tuv), tgt_text=_tuv_text(tgt_tuv),
            created_at=tu.get('creationdate'), source_file=path,
        ))

    if skipped_lang_mismatch:
        print('warning: tmx: %d <tu> elements had no tuv matching the requested '
              'language pair, skipped' % skipped_lang_mismatch)
    return units
