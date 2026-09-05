"""Bilingual DOCX reader for the alternating-paragraph layout: source
paragraph, target paragraph, source paragraph, target paragraph, ...
(as opposed to docx_numbered.py's two-block convention or docx_table.py's
table convention).

No positive signal distinguishes this layout from an arbitrary monolingual
document with an even paragraph count -- see docx.py's module docstring
for why this is tried last in auto-detection, not first.
"""
from language_tools.model import ParagraphPair
from language_tools.readers._ooxml import iter_body_paragraphs


def read(path, **opts):
    paras = [p for p in iter_body_paragraphs(path) if p.strip()]
    if len(paras) < 2 or len(paras) % 2:
        raise ValueError('alternating layout requires an even, non-zero '
                          'number of non-empty paragraphs, got %d' % len(paras))
    return [ParagraphPair(key=str(i // 2 + 1), src_text=paras[i], tgt_text=paras[i + 1])
            for i in range(0, len(paras), 2)]
