"""Bilingual DOCX reader for the numbered-list layout:

    [1] Source paragraph 1
    [2] Source paragraph 2
    ...
    [1] Target paragraph 1
    [2] Target paragraph 2
    ...

The target block is detected as wherever the [N] numbering restarts at 1.
Ported from the seed script's ``find_blocks`` with one library-appropriate
change: raises ``ValueError`` instead of ``SystemExit`` on a malformed
document (a library shouldn't kill the interpreter out from under its
caller -- that's a CLI-layer decision, not a reader-layer one).
"""
import re

from language_tools.model import ParagraphPair
from language_tools.readers._ooxml import iter_body_paragraphs

_NUM_RE = re.compile(r'^\[(\d+)\]\s*(.*)$', re.S)


def read(path, **opts):
    paras = list(iter_body_paragraphs(path))
    hits = []
    for i, t in enumerate(paras):
        m = _NUM_RE.match(t)
        if m and m.group(2).strip():
            hits.append((i, int(m.group(1)), m.group(2).strip()))

    start = None
    for k in range(1, len(hits)):
        if hits[k][1] == 1:
            start = k
            break
    if start is None:
        raise ValueError('Could not locate the two language blocks; expected [1] to appear twice.')

    src = {n: b for _, n, b in hits[:start]}
    tgt = {n: b for _, n, b in hits[start:]}
    keys = sorted(set(src) & set(tgt))
    missing_src = sorted(set(tgt) - set(src))
    missing_tgt = sorted(set(src) - set(tgt))
    if missing_src:
        print('warning: numbers present only in target block, dropped: %s' % missing_src)
    if missing_tgt:
        print('warning: numbers present only in source block, dropped: %s' % missing_tgt)

    return [ParagraphPair(key=str(k), src_text=src[k], tgt_text=tgt[k]) for k in keys]
