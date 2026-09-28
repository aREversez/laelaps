"""Minimal .docx writer for tests that need specific body XML (text boxes,
tabs, tracked changes, ...) the checked-in fixtures don't contain.

Only ``word/document.xml`` matters to the readers, but the package is made
well-formed enough (content types + root rels) that Word/LibreOffice open it.
"""
import zipfile

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"')

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>')

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>')


def run(text):
    return '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % _esc(text)


def para(*runs):
    """A <w:p> from plain strings (wrapped as runs) or raw run XML (starts with '<')."""
    return '<w:p>%s</w:p>' % ''.join(r if r.startswith('<') else run(r) for r in runs)


def table(rows):
    """rows: list of lists of cell contents; a cell is a str or a list of paragraph strings."""
    out = ['<w:tbl>']
    for row in rows:
        out.append('<w:tr>')
        for cell in row:
            paras = cell if isinstance(cell, list) else [cell]
            out.append('<w:tc>%s</w:tc>' % ''.join(para(p) for p in paras))
        out.append('</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)


def write(path, body_xml):
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document %s><w:body>%s</w:body></w:document>' % (_NS, body_xml))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _CONTENT_TYPES)
        z.writestr('_rels/.rels', _RELS)
        z.writestr('word/document.xml', document)
    return str(path)


def _esc(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
