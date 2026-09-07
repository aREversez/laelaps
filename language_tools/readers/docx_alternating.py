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


def _non_empty_paras(path):
    return [p for p in iter_body_paragraphs(path) if p.strip()]


def confidence(path):
    """Return a 0..1 score for how strongly this document looks like a
    bilingual alternating-paragraph layout.

    This is the only layout with no positive signal -- *any* document
    with an even, non-zero paragraph count "matches" the alternating
    shape, including a monolingual doc that just happens to have 4 or
    6 paragraphs. So we deliberately score this low: 0.5 *at most*, even
    for a long even-paragraph doc. Auto-detection only falls through to
    alternating when neither table nor numbered claims the document with
    a higher score, so 0.5 is enough to win that fallback race.

    Scoring:
    - odd paragraph count or 0 paragraphs -> 0.0 (definitely not)
    - 2 paragraphs -> 0.5 (could be a 1-pair bilingual doc, or just any
      2-paragraph monolingual doc -- genuinely ambiguous, low score)
    - >=4 even paragraphs -> 0.5 (same ambiguity, just longer)
    """
    paras = _non_empty_paras(path)
    if len(paras) < 2 or len(paras) % 2:
        return 0.0
    return 0.5


def read(path, **opts):
    paras = _non_empty_paras(path)
    if len(paras) < 2 or len(paras) % 2:
        raise ValueError('alternating layout requires an even, non-zero '
                          'number of non-empty paragraphs, got %d' % len(paras))
    return [ParagraphPair(key=str(i // 2 + 1), src_text=paras[i], tgt_text=paras[i + 1])
            for i in range(0, len(paras), 2)]
