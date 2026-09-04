"""Gale-Church-style sentence aligner.

Architectural invariant (see DESIGN.md section 2): the DP alignment MUST
NOT cross ``ParagraphPair`` boundaries. Each pair's source/target sentence
lists are aligned independently; ``_align_sentences`` never sees sentences
from more than one pair in a single call. The one thing shared across pairs
is the global length ratio ``R`` used to normalize the cost function -- that
is a single scalar computed once, not shared DP state, and does not let the
DP path jump between pairs. ``tests/test_align_boundary.py`` asserts this
directly by constructing a case where crossing the boundary would produce a
cheaper (but wrong) alignment, and confirming the aligner doesn't take it.
"""
import math

from language_tools.align.repair import NULL_REPAIRER
from language_tools.align.splitters import nolen, pick_splitter
from language_tools.model import ParagraphPair, TranslationUnit

MATCHES = [(1, 1), (2, 1), (1, 2), (2, 2), (3, 2), (2, 3), (1, 3), (3, 1), (3, 3)]
INF = float('inf')


def _align_sentences(e, z, join_src, join_tgt, R, S2, MP, MP0, GAP):
    """DP-align one pair's sentence lists. Never called across pair boundaries."""
    n, m = len(e), len(z)

    def cost(en_g, zh_g):
        if not en_g or not zh_g:
            return GAP
        le = sum(nolen(s) for s in en_g)
        lc = sum(nolen(s) for s in zh_g)
        if le == 0 or lc == 0:
            return GAP
        exp = le / R
        zscore = (lc - exp) / math.sqrt(max(exp * S2, 1.0))
        pen = 0.5 * zscore * zscore
        pen += MP * ((len(en_g) - 1) + (len(zh_g) - 1))
        if (len(en_g), len(zh_g)) != (1, 1):
            pen += MP0
        return pen

    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            for di, dj in MATCHES:
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                c = cost(e[i:ni], z[j:nj])
                if c != INF and dp[i][j] + c < dp[ni][nj]:
                    dp[ni][nj] = dp[i][j] + c
                    bt[ni][nj] = (i, j)
    if dp[n][m] == INF:
        return []
    res, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj = bt[i][j]
        res.append((join_src.join(e[pi:i]), join_tgt.join(z[pj:j])))
        i, j = pi, pj
    res.reverse()
    return res


def align_paragraph_pairs(pairs, src_lang, tgt_lang, repairer=NULL_REPAIRER,
                           S2=0.8, MP=2.5, MP0=2.0, GAP=60.0, source_file=None):
    """list[ParagraphPair] -> (list[TranslationUnit], length_ratio).

    ``repairer`` is a ``align.repair.Repairer`` (defaults to a no-op one).
    """
    sample_src = next((p.src_text for p in pairs if p.src_text), '')
    sample_tgt = next((p.tgt_text for p in pairs if p.tgt_text), '')
    split_src, join_src, lang_tag_src = pick_splitter(src_lang, sample_src, 'src')
    split_tgt, join_tgt, lang_tag_tgt = pick_splitter(tgt_lang, sample_tgt, 'tgt')
    repair_src = repairer.for_lang(lang_tag_src)
    repair_tgt = repairer.for_lang(lang_tag_tgt)

    split = {p.key: (split_src(p.src_text, repair_src), split_tgt(p.tgt_text, repair_tgt))
             for p in pairs}
    src_len = sum(nolen(s) for k in split for s in split[k][0])
    tgt_len = sum(nolen(s) for k in split for s in split[k][1])
    R = src_len / max(tgt_len, 1)

    units = []
    for pair in pairs:
        e, z = split[pair.key]
        for src_text, tgt_text in _align_sentences(e, z, join_src, join_tgt, R, S2, MP, MP0, GAP):
            units.append(TranslationUnit(
                src_lang=src_lang, tgt_lang=tgt_lang,
                src_text=src_text, tgt_text=tgt_text,
                source_file=source_file, source_key=pair.key,
            ))
    return units, R
