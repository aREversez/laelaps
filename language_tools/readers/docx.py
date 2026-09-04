"""Auto-detects DOCX layout (table vs numbered-list) and dispatches to the
matching reader. See DESIGN.md section 7.3: "必须支持自动识别版式".
"""
from language_tools.readers import docx_numbered, docx_table


def read(path, layout='auto', **opts):
    if layout == 'table':
        return docx_table.read(path, **opts)
    if layout == 'numbered':
        return docx_numbered.read(path, **opts)
    if layout != 'auto':
        raise ValueError('unknown layout %r (expected auto/table/numbered)' % layout)

    try:
        return docx_table.read(path, **opts)
    except ValueError:
        pass
    return docx_numbered.read(path, **opts)
