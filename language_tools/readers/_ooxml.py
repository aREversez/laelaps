"""Shared low-level OOXML (.docx) structural parsing.

Replaces the seed script's regex-based ``docx_paragraphs()`` (raw
``<w:p[ >].*?</w:p>`` matching + manual ``html.unescape`` of leftover
entities) with a real ``xml.etree.ElementTree`` parse. This is not a
speculative improvement: regex matching XML is fragile in general, and
ElementTree gets entity decoding correct for free (no more manual
``html.unescape`` + tag-stripping dance). ``docx_numbered.py`` and the
future table-layout reader both build on ``iter_body_paragraphs`` /
``iter_body_tables`` here instead of duplicating XML-walking logic.
"""
import xml.etree.ElementTree as ET
import zipfile

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
MC_NS = 'http://schemas.openxmlformats.org/markup-compatibility/2006'


def w(tag):
    return '{%s}%s' % (W_NS, tag)


def _paragraph_text(p_elem):
    """Visible text of one <w:p>: every <w:t> run's text, concatenated.

    Matches the seed reader's behaviour: runs are joined with no separator,
    so a paragraph split across a <w:tab/> or <w:br/> without an explicit
    space in a run will still concatenate without a space. Not fixed here --
    it's a known, documented limitation carried over unchanged, not a new
    one introduced by this rewrite.
    """
    texts = [t.text or '' for t in p_elem.iter(w('t'))]
    return ''.join(texts).replace('\u00a0', ' ').strip()


def _doc_root(path):
    with zipfile.ZipFile(path) as z:
        xml_bytes = z.read('word/document.xml')
    return ET.fromstring(xml_bytes)


def iter_body_paragraphs(path):
    """Yield the text of every <w:p> in word/document.xml, in document
    order, including paragraphs nested inside tables -- matches the seed
    reader's behaviour of scanning every <w:p> anywhere in the document.
    """
    root = _doc_root(path)
    body = root.find(w('body'))
    if body is None:
        return
    for p in body.iter(w('p')):
        yield _paragraph_text(p)


def iter_body_tables(path):
    """Yield each <w:tbl> as a list of rows, each row a list of cell texts
    (a cell's text is its paragraphs joined with '\\n'). For the table-
    layout bilingual reader (Phase 2); unused by docx_numbered.py.
    """
    root = _doc_root(path)
    body = root.find(w('body'))
    if body is None:
        return
    for tbl in body.findall(w('tbl')):
        rows = []
        for tr in tbl.findall(w('tr')):
            cells = []
            for tc in tr.findall(w('tc')):
                paras = [_paragraph_text(p) for p in tc.findall(w('p'))]
                cells.append('\n'.join(t for t in paras if t))
            rows.append(cells)
        yield rows


def iter_body_tables_with_merge_flags(path):
    """Same shape as ``iter_body_tables()`` (list of rows, each a list of
    cell texts), plus a per-table count of cells participating in a
    horizontal (``<w:gridSpan w:val>1>``) or vertical (``<w:vMerge>``)
    merge. Kept as its own function rather than changing
    ``iter_body_tables()``'s return shape: every existing caller
    (``docx_table.py``'s ``confidence()``/``read()``) only wants cell
    text and would need updating for no benefit. Only ``docx_preflight.py``
    (DESIGN.md 15.2) needs the merge info, so it gets its own walk.

    A vertical-merge continuation cell counts once per row it spans
    (matches how many ``<w:tc>`` elements OOXML actually emits for it),
    not once per logical merged region -- callers that just want "does
    this table have any merged cells at all" only need the count to be
    nonzero, so this doesn't try to reconstruct merge regions.
    """
    root = _doc_root(path)
    body = root.find(w('body'))
    if body is None:
        return
    for tbl in body.findall(w('tbl')):
        rows = []
        merged = 0
        for tr in tbl.findall(w('tr')):
            cells = []
            for tc in tr.findall(w('tc')):
                paras = [_paragraph_text(p) for p in tc.findall(w('p'))]
                cells.append('\n'.join(t for t in paras if t))
                tc_pr = tc.find(w('tcPr'))
                if tc_pr is not None:
                    grid_span = tc_pr.find(w('gridSpan'))
                    v_merge = tc_pr.find(w('vMerge'))
                    span_val = grid_span.get(w('val')) if grid_span is not None else None
                    if (span_val and int(span_val) > 1) or v_merge is not None:
                        merged += 1
            rows.append(cells)
        yield rows, merged


# Subtrees the monolingual walk never enters: text-box content (a drawing
# anchored inside a body paragraph -- its text is not part of the running
# body text, and ``iter_body_paragraphs`` above would report it twice, once
# inside the anchoring paragraph and once as a paragraph of its own) and
# markup-compatibility fallbacks (the legacy-renderer copy of content that
# ``mc:Choice`` already carries, e.g. the same text box drawn a second time
# as VML).
_MONO_SKIP = {w('txbxContent'), '{%s}Fallback' % MC_NS}
# Elements that separate words visually but carry no <w:t> of their own.
_MONO_SPACE = {w('tab'), w('br'), w('cr')}


def _visible_text(elem, out):
    for child in elem:
        tag = child.tag
        if tag in _MONO_SKIP:
            continue
        if tag == w('t'):
            out.append(child.text or '')
        elif tag in _MONO_SPACE:
            out.append(' ')
        elif tag == w('noBreakHyphen'):
            out.append('-')
        else:
            _visible_text(child, out)


def _mono_paragraphs(elem):
    for child in elem:
        tag = child.tag
        if tag in _MONO_SKIP:
            continue
        if tag == w('p'):
            out = []
            _visible_text(child, out)
            yield ''.join(out)
        else:
            yield from _mono_paragraphs(child)


def iter_text_paragraphs(path):
    """Yield the running body text of a .docx, one string per <w:p>, in
    document order, for *monolingual* consumers (leverage analysis).

    Differs from ``iter_body_paragraphs`` -- which the bilingual readers
    depend on and which is deliberately left unchanged -- in three ways:

    - Paragraphs inside table cells and content controls are included (same
      as before), but text-box content and ``mc:Fallback`` copies are not,
      so nothing is counted twice or pulled in out of reading order.
    - ``<w:tab/>``, ``<w:br/>`` and ``<w:cr/>`` become a space. The bilingual
      readers concatenate runs with no separator ("Name<tab>Value" reads as
      "NameValue"), a documented limitation that is harmless for pairing but
      would make a sentence unmatchable against a TM built from clean text.
    - Deleted tracked-change text is not visible text (it lives in
      ``<w:delText>``, not ``<w:t>``), so this reads the document as if all
      revisions were accepted; inserted text is included.

    Text is NBSP-normalized and stripped; empty paragraphs are yielded as
    ``''`` (callers decide whether to drop them). Headers, footers,
    footnotes, endnotes and comments live in other package parts and are not
    read.
    """
    root = _doc_root(path)
    body = root.find(w('body'))
    if body is None:
        return
    for text in _mono_paragraphs(body):
        yield text.replace('\u00a0', ' ').strip()
