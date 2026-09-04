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
