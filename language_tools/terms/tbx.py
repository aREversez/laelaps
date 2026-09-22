"""TBX (TermBase eXchange, ISO 30042) glossary read/write -- DESIGN.md
15.2's TBX / MultiTerm XML 互通 item.

**Read this before pointing a real MultiTerm/Trados export at this
module.** TBX is not one format; DESIGN.md 15.2 flagged this explicitly
("不要类比 tmx_reader 的工程量") and the flag turned out to be correct.
Concretely:

- **Two incompatible element vocabularies exist in the wild.** TBX 2008
  and the still-current TBX-Basic dialect use ``<termEntry>``/
  ``<langSet>``/``<tig>``; ISO 30042:2019 ("TBX 3.0") renamed those to
  ``<conceptEntry>``/``<langSec>``/``<termSec>``. MultiTerm, Trados
  Studio, Phrase, and most real-world TBX exports still use the older
  names -- ``read()`` accepts both (matched by local tag name, ignoring
  whichever one is present), but ``write()`` emits only the older
  (TBX-Basic) names, since that is what DESIGN.md 15.2's named target
  tools (Trados/MultiTerm) actually consume.
- **``administrativeStatus`` is a many-valued picklist; TermEntry.status
  is two-valued.** The TBX-Basic spec's controlled vocabulary is
  ``preferredTerm-admn-sts``/``admittedTerm-admn-sts``/
  ``deprecatedTerm-admn-sts``/``supersededTerm-admn-sts`` (plus a few
  more in full TBX); some real tools (Weblate, at least) instead emit
  bare words like ``forbidden``/``deprecated``. ``read()`` recognizes
  both the official picklist and the common shorthand, collapsed into
  this codebase's ``approved``/``forbidden`` two-state model (see
  ``terms/model.py``) -- this is a deliberate, lossy simplification, not
  an oversight; a TBX file distinguishing preferred-vs-admitted or
  deprecated-vs-superseded will not get that distinction back.
- **Synonyms are dropped, not merged.** A TBX concept can hold more than
  one ``<tig>``/``<termSec>`` per language (synonymous terms for the same
  concept) -- ``read()`` keeps only the first term group per language and
  counts (and warns about) the rest, rather than guessing which src
  synonym pairs with which tgt synonym or exploding every combination
  into its own row. ``write()`` mirrors this: each ``TermEntry`` becomes
  its own independent ``<termEntry>`` with exactly one term per side,
  never a multi-synonym concept.
- **MultiTerm's custom/vendor fields are not read at all.** Real MultiTerm
  exports carry ``descripGrp``/``descrip`` fields with tool-specific type
  names (custom user-defined fields, entry IDs re-encoded into
  ``descripGrp``, etc. -- see the module-level risk this item was filed
  against in DESIGN.md 15.2) that have no defined mapping onto
  ``TermEntry``'s fixed field set. Only ``<term>``, the
  ``administrativeStatus`` ``<termNote>``, a first ``<note>``, and a
  ``<descrip type="subjectField"|"domain"|"category">`` (best-effort,
  mapped to ``domain``) are read; everything else in the file is
  silently ignored, not partially reconstructed.
- **Round-trip fidelity is only claimed for THIS module's own writes.**
  ``read()`` then ``write()`` on a file this module itself produced comes
  back unchanged (modulo entry ``id`` numbering and XML formatting).
  ``write()`` on entries read from a real third-party TBX export will NOT
  reproduce that export byte-for-byte -- everything the paragraph above
  drops stays dropped.

None of this is a defect list to fix before shipping -- it is the actual
shape of "TBX interop" for a two-field (approved/forbidden), one-term-
per-language glossary model. A future reader hitting an unsupported real-
world TBX quirk should extend the specific mapping in question (adding a
new ``administrativeStatus`` synonym, say), not assume the whole module
needs a rewrite.
"""
import xml.etree.ElementTree as ET

from language_tools.terms.model import TermEntry

_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'

# TBX-Basic/TBX-2008 element names (write() emits these) alongside their
# TBX 3.0 (ISO 30042:2019) renames (read() also accepts these). See
# module docstring's first bullet.
_CONCEPT_TAGS = ('termEntry', 'conceptEntry')
_LANG_TAGS = ('langSet', 'langSec')
_TERM_GROUP_TAGS = ('tig', 'termSec', 'ntig')

# The TBX-Basic administrativeStatus picklist, plus the shorter
# non-standard values some real tools emit instead -- see module
# docstring's second bullet for the many-to-two collapse this performs.
_FORBIDDEN_STATUS_VALUES = frozenset({
    'forbidden', 'deprecated', 'deprecatedterm-admn-sts', 'superseded',
    'supersededterm-admn-sts', 'notrecommended', 'obsolete',
})
_APPROVED_STATUS_VALUES = frozenset({
    'preferred', 'preferredterm-admn-sts', 'admitted', 'admittedterm-admn-sts',
    'approved', 'confirmed', 'legalterm-admn-sts', 'regulatedterm-admn-sts',
    'standardizedterm-admn-sts',
})

_DOMAIN_DESCRIP_TYPES = frozenset({'subjectfield', 'domain', 'category'})


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _lang_base(tag):
    return tag.split('-', 1)[0].lower() if tag else ''


def _lang_matches(requested, actual):
    """Same tolerant match ``corpus_readers/tmx_reader.py`` uses (case-
    insensitive, region-subtag-optional on either side) -- kept as a
    separate local copy rather than a cross-module import, matching how
    ``tm.clean``/``tm.leverage`` each already keep their own small local
    helpers instead of sharing one.
    """
    if not requested or not actual:
        return False
    requested, actual = requested.lower(), actual.lower()
    return requested == actual or _lang_base(requested) == _lang_base(actual)


def _children(elem, tags):
    return [c for c in elem if _local(c.tag) in tags]


def _first_child(elem, tags):
    found = _children(elem, tags)
    return found[0] if found else None


def _text(elem):
    return ''.join(elem.itertext()).strip() if elem is not None else ''


def _term_group_text(tg):
    return _text(_first_child(tg, ('term',)))


def _term_group_status(tg):
    """Scans ``<termNote type="administrativeStatus">`` inside a term
    group. Returns ``(status, declared)`` -- ``declared`` is False when no
    recognized value was found, same "fallback vs. explicit choice"
    distinction ``glossary.read()`` already makes for its own status
    column (see ``TermEntry.status_declared``).
    """
    for note in _children(tg, ('termNote',)):
        if note.get('type', '').lower() != 'administrativestatus':
            continue
        value = _text(note).lower()
        if value in _FORBIDDEN_STATUS_VALUES:
            return 'forbidden', True
        if value in _APPROVED_STATUS_VALUES:
            return 'approved', True
    return 'approved', False


def _term_group_note(tg):
    return _text(_first_child(tg, ('note',))) or None


def _descrip_domain(elem):
    for d in _children(elem, ('descrip',)):
        if d.get('type', '').lower() in _DOMAIN_DESCRIP_TYPES:
            return _text(d) or None
    return None


def read(path, src_lang, tgt_lang):
    """Reads a TBX file into a ``TermEntry`` list for the ``(src_lang,
    tgt_lang)`` pair -- same signature and language-pair-is-a-parameter
    convention as ``glossary.read()``. A concept with no ``langSet``/
    ``langSec`` matching both requested languages is skipped (it isn't
    part of this language pair, not an error). See the module docstring
    for what is and isn't read from each matched concept.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    body = next((el for el in root.iter() if _local(el.tag) == 'body'), None)
    if body is None:
        return []

    entries = []
    dropped_synonyms = 0
    skipped_incomplete = 0
    for concept in _children(body, _CONCEPT_TAGS):
        lang_sets = _children(concept, _LANG_TAGS)
        src_ls = next((ls for ls in lang_sets if _lang_matches(src_lang, ls.get(_XML_LANG, ''))),
                       None)
        tgt_ls = next((ls for ls in lang_sets if _lang_matches(tgt_lang, ls.get(_XML_LANG, ''))),
                       None)
        if src_ls is None or tgt_ls is None:
            skipped_incomplete += 1
            continue

        src_groups = _children(src_ls, _TERM_GROUP_TAGS)
        tgt_groups = _children(tgt_ls, _TERM_GROUP_TAGS)
        if not src_groups or not tgt_groups:
            skipped_incomplete += 1
            continue
        dropped_synonyms += (len(src_groups) - 1) + (len(tgt_groups) - 1)

        src_tg, tgt_tg = src_groups[0], tgt_groups[0]
        src_term, tgt_term = _term_group_text(src_tg), _term_group_text(tgt_tg)
        if not src_term and not tgt_term:
            continue

        status, declared = _term_group_status(tgt_tg)
        if not declared:
            status, declared = _term_group_status(src_tg)

        note = _term_group_note(tgt_tg) or _term_group_note(src_tg)
        domain = (_descrip_domain(tgt_tg) or _descrip_domain(src_tg) or
                  _descrip_domain(tgt_ls) or _descrip_domain(src_ls) or
                  _descrip_domain(concept))

        entries.append(TermEntry(
            src_lang=src_lang, tgt_lang=tgt_lang, src_term=src_term, tgt_term=tgt_term,
            status=status, status_declared=declared, domain=domain, note=note))

    if dropped_synonyms:
        print('warning: %d synonym term(s) in %s were dropped -- only the first <tig>/'
              '<termSec> per language is read per concept (see language_tools.terms.tbx '
              'module docstring)' % (dropped_synonyms, path))
    if skipped_incomplete:
        print('warning: %d concept(s) in %s had no langSet/langSec for both %s and %s and '
              'were skipped' % (skipped_incomplete, path, src_lang, tgt_lang))
    return entries


def write(path, entries):
    """Writes ``entries`` as a TBX-Basic-dialect file: one ``<termEntry>``
    per entry, each with exactly one src-language and one tgt-language
    ``<langSet>``, each holding exactly one ``<tig><term>``. See the
    module docstring's "round-trip fidelity" bullet -- this is lossless
    for a file this module itself produced, not a claim to reproduce a
    third-party TBX export.

    ``status='forbidden'`` writes an ``administrativeStatus`` termNote of
    ``deprecatedTerm-admn-sts`` (the closest TBX-Basic picklist value to
    "should not be used" -- there is no literal "forbidden" in the
    official picklist, see module docstring). A declared ``'approved'``
    status writes ``preferredTerm-admn-sts``; an undeclared (fallback)
    ``'approved'`` writes nothing, so a glossary row that never actually
    had its status set doesn't come out the other end asserting it's the
    officially preferred term.
    """
    root = ET.Element('martif', {'type': 'TBX', _XML_LANG: 'en'})
    header = ET.SubElement(root, 'martifHeader')
    file_desc = ET.SubElement(header, 'fileDesc')
    source_desc = ET.SubElement(file_desc, 'sourceDesc')
    ET.SubElement(source_desc, 'p').text = 'laelaps'
    body = ET.SubElement(ET.SubElement(root, 'text'), 'body')

    for i, e in enumerate(entries, 1):
        concept = ET.SubElement(body, 'termEntry', {'id': 'e%d' % i})
        if e.domain:
            ET.SubElement(concept, 'descrip', {'type': 'subjectField'}).text = e.domain

        src_ls = ET.SubElement(concept, 'langSet', {_XML_LANG: e.src_lang})
        ET.SubElement(ET.SubElement(src_ls, 'tig'), 'term').text = e.src_term

        tgt_ls = ET.SubElement(concept, 'langSet', {_XML_LANG: e.tgt_lang})
        tgt_tig = ET.SubElement(tgt_ls, 'tig')
        ET.SubElement(tgt_tig, 'term').text = e.tgt_term
        if e.status == 'forbidden':
            ET.SubElement(tgt_tig, 'termNote',
                          {'type': 'administrativeStatus'}).text = 'deprecatedTerm-admn-sts'
        elif e.status == 'approved' and e.status_declared:
            ET.SubElement(tgt_tig, 'termNote',
                          {'type': 'administrativeStatus'}).text = 'preferredTerm-admn-sts'
        if e.note:
            ET.SubElement(tgt_tig, 'note').text = e.note

    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(path, encoding='utf-8', xml_declaration=True)
