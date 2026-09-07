"""Auto-detects DOCX layout (table / numbered-list / alternating-paragraph)
and dispatches to the matching reader. See DESIGN.md section 7.3:
"必须支持自动识别版式".

Each reader exposes a ``confidence(path) -> float`` function (a cheap probe
without doing the full read) scoring how strongly that layout claims the
document. Auto-detection picks the layout with the highest confidence,
not the first reader that doesn't raise -- this matters because the old
"try table, then numbered, then alternating" order had a real false-positive
risk: a single stray 2-column table anywhere in the document (e.g. a
layout-element table on the cover page of an otherwise-numbered-layout
doc) would steal detection from the numbered reader.

Ties (e.g. both table and numbered score 0.95) go to the earlier reader in
_AUTO_ORDER, matching the old behavior for cases where the document
genuinely could be either layout -- the user can still override with
--layout if needed.

``layout='alternating'`` remains the lowest-confidence fallback (capped at
0.5 by design -- see docx_alternating.confidence's docstring) because it
has no positive signal: any document with an even paragraph count
"matches" alternating, so it should only win when nothing else does.
"""
from language_tools.readers import docx_alternating, docx_numbered, docx_table

_AUTO_ORDER = [docx_table, docx_numbered, docx_alternating]
_BY_NAME = {'table': docx_table, 'numbered': docx_numbered, 'alternating': docx_alternating}

# Below this threshold, a reader is treated as "not claiming the document
# at all" -- e.g. alternating never exceeds 0.5, but if table also returns
# 0.5 (one tiny table, 2 paragraphs), the table reader is the stronger
# signal because it has a positive structural feature. The threshold
# itself is mostly a safety floor; with the current scoring, only
# alternating actually scores below 0.85 when it claims a document.
_MIN_CLAIM_THRESHOLD = 0.0


def read(path, layout='auto', **opts):
    if layout != 'auto':
        reader = _BY_NAME.get(layout)
        if reader is None:
            raise ValueError('unknown layout %r (expected auto/table/numbered/alternating)' % layout)
        return reader.read(path, **opts)

    # Score every reader, pick the argmax. We compute all scores up front
    # (cheap probes -- table confidence walks tables once, numbered walks
    # paragraphs once, alternating just counts paragraphs) rather than
    # short-circuiting, because the only way to know "X is the best" is
    # to also know "Y and Z aren't better".
    scored = [(reader.confidence(path), reader) for reader in _AUTO_ORDER]
    best_score, best_reader = max(scored, key=lambda sr: sr[0])
    if best_score <= _MIN_CLAIM_THRESHOLD:
        raise ValueError('could not auto-detect a bilingual DOCX layout '
                          '(table=%g, numbered=%g, alternating=%g); use --layout to specify'
                          % (scored[0][0], scored[1][0], scored[2][0]))
    return best_reader.read(path, **opts)
