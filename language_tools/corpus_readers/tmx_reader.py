"""Read a TMX file directly into TranslationUnit list.

Corpus readers skip the align step bilingual-file readers require (see
DESIGN.md section 1): a TMX <tu> is already one aligned sentence pair.
ElementTree handles entity decoding for free, same reasoning as the
_ooxml.py rewrite in Phase 1.

Three real interop bugs fixed here, all confirmed empirically before
landing (not just reasoned about) -- real-world TMX exports from other
CAT tools hit all three:

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
   manually walking direct children only.
3. Inline markup structure itself was dropped entirely (only the visible
   text survived) -- ``Click <bpt i="1">&lt;b&gt;</bpt>OK<ept
   i="1">&lt;/b&gt;</ept>`` round-tripped to ``Click <b>OK</b> to
   continue.`` and the actual ``<bpt>/<ept>`` wrapper (which carries
   formatting/placeholder info) was lost on the way back out through
   tmx_writer. Fixed by populating ``TranslationUnit.src_markup``/
   ``tgt_markup`` with an ``InlineNode`` list when a <seg> contains any
   child element; tmx_writer round-trips it losslessly. Text-only TUs
   keep ``markup=None`` so existing call sites see no change.
"""
import xml.etree.ElementTree as ET

from language_tools.model import InlineNode, TranslationUnit

_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'

# TMX 1.4b inline element local names -- any of these appearing as a
# direct child of <seg> means the segment has markup worth preserving.
# Reference: TMX 1.4b spec section "Inline Element descriptions".
_TMX_INLINE_TAGS = frozenset({
    'bpt', 'ept', 'ph', 'hi', 'it', 'ut', 'sub',
})


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _tuv_lang(tuv):
    return tuv.get(_XML_LANG) or tuv.get('lang') or ''


def _seg_to_text_and_markup(seg):
    """Return (visible_text, markup_or_None) for a <seg> element.

    ``visible_text`` is the same string ``''.join(seg.itertext()).strip()``
    produced before -- all text in document order, markup stripped. When
    the <seg> has no child elements, ``markup`` is None (the common case
    -- text-only TUs stay shape-compatible with existing callers). When it
    has any inline tag, ``markup`` is an ordered list of ``InlineNode``
    capturing the visible-text/tag-fragment interleaving so tmx_writer
    can rebuild the <seg> verbatim. Elements not in ``_TMX_INLINE_TAGS``
    (e.g. stray formatting from non-conforming TMX producers) are treated
    as tag nodes too -- the alternative (silently dropping them) would
    lose data the producer clearly intended to be there.
    """
    has_children = any(True for _ in seg)
    text = ''.join(seg.itertext()).strip()
    if not has_children:
        return text, None

    markup = []
    if seg.text and seg.text.strip():
        markup.append(InlineNode(kind='text', content=seg.text))
    for child in seg:
        # Serialize this child element WITHOUT its tail text -- ET.tostring
        # includes .tail by default, which would double-count the tail (we
        # add it as a separate text node below). Save/nul/restore is the
        # idiomatic way to get a tail-less serialization from ElementTree.
        original_tail = child.tail
        child.tail = None
        try:
            fragment = ET.tostring(child, encoding='unicode', short_empty_elements=False)
        finally:
            child.tail = original_tail
        markup.append(InlineNode(kind='tag', content=fragment))
        if child.tail and child.tail.strip():
            markup.append(InlineNode(kind='text', content=child.tail))
    # Drop trailing/leading empty-text nodes if any
    while markup and markup[0].kind == 'text' and not markup[0].content.strip():
        markup.pop(0)
    while markup and markup[-1].kind == 'text' and not markup[-1].content.strip():
        markup.pop()
    return text, (markup or None)


def _tuv_text(tuv):
    seg = next((c for c in tuv if _local_name(c.tag) == 'seg'), None)
    if seg is None:
        return '', None
    return _seg_to_text_and_markup(seg)


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

        src_text, src_markup = _tuv_text(src_tuv)
        tgt_text, tgt_markup = _tuv_text(tgt_tuv)
        units.append(TranslationUnit(
            src_lang=_tuv_lang(src_tuv), tgt_lang=_tuv_lang(tgt_tuv),
            src_text=src_text, tgt_text=tgt_text,
            src_markup=src_markup, tgt_markup=tgt_markup,
            created_at=tu.get('creationdate'), source_file=path,
        ))

    if skipped_lang_mismatch:
        print('warning: tmx: %d <tu> elements had no tuv matching the requested '
              'language pair, skipped' % skipped_lang_mismatch)
    return units
