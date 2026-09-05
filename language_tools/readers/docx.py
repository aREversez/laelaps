"""Auto-detects DOCX layout (table / numbered-list / alternating-paragraph)
and dispatches to the matching reader. See DESIGN.md section 7.3:
"必须支持自动识别版式".

Detection order: table, then numbered, then alternating. Table and
numbered layouts have a strong positive signal (a qualifying table exists;
"[1]" appears twice) so they're tried first and cheaply rule themselves
out via ValueError when absent. Alternating is the fallback of last resort
because it has no positive signal at all -- any document with an even,
non-zero number of non-empty paragraphs "matches" the alternating shape,
which makes it prone to false positives on documents that are not actually
bilingual (e.g. two unrelated paragraphs in a monolingual doc). Only use
``layout='alternating'`` explicitly unless you've confirmed auto-detect
picks it correctly for your documents.
"""
from language_tools.readers import docx_alternating, docx_numbered, docx_table

_AUTO_ORDER = [docx_table, docx_numbered, docx_alternating]
_BY_NAME = {'table': docx_table, 'numbered': docx_numbered, 'alternating': docx_alternating}


def read(path, layout='auto', **opts):
    if layout != 'auto':
        reader = _BY_NAME.get(layout)
        if reader is None:
            raise ValueError('unknown layout %r (expected auto/table/numbered/alternating)' % layout)
        return reader.read(path, **opts)

    last_err = None
    for reader in _AUTO_ORDER:
        try:
            return reader.read(path, **opts)
        except ValueError as e:
            last_err = e
    raise ValueError('could not auto-detect a bilingual DOCX layout '
                      '(tried table, numbered, alternating): %s' % last_err)
