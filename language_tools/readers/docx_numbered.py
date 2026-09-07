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


def _numbered_hits(path):
    """Yield (paragraph_index, n, body) for every paragraph matching the
    ``[N] body`` pattern with a non-empty body. Shared between confidence()
    and read() so both see the same definition of "what counts as a hit".
    """
    paras = list(iter_body_paragraphs(path))
    for i, t in enumerate(paras):
        m = _NUM_RE.match(t)
        if m and m.group(2).strip():
            yield i, int(m.group(1)), m.group(2).strip()


def confidence(path):
    """Return a 0..1 score for how strongly this document looks like a
    bilingual numbered-list layout. The defining signal is **two separate
    runs of [1]..[N] paragraphs** -- one for the source block, one for
    the target block. Scoring rationale (kept deliberately simple):

    - 0 [N]-tagged paragraphs -> 0.0 (definitely not numbered layout)
    - >=2 hits but [1] appears only once -> 0.5 (the document uses [N]
      numbering, but it's a single block, not a bilingual pair -- could
      be a monolingual numbered list)
    - [1] appears exactly twice and >=4 hits total -> 0.95 (strong
      signal: classic bilingual two-block shape)
    - [1] appears exactly twice and 2-3 hits total -> 0.85 (right shape
      but small sample -- 1 pair source/target)
    - [1] appears 3+ times -> 0.7 (unusual -- could be a multi-section
      document with numbering restarts, treat as ambiguous)
    """
    hits = list(_numbered_hits(path))
    if not hits:
        return 0.0
    n_one = sum(1 for _, n, _ in hits if n == 1)
    if n_one == 0:
        return 0.0  # no [1] hit at all -> definitely not the layout
    if n_one == 1:
        return 0.5
    if n_one == 2:
        return 0.95 if len(hits) >= 4 else 0.85
    return 0.7


def read(path, **opts):
    hits = list(_numbered_hits(path))

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
