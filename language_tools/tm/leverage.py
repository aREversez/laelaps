"""Leverage (match-rate) analysis: how much of a set of segments can be
reused from an existing TM, before translation work starts.

This is the standalone counterpart to the "analyze" report every CAT tool
ships (Trados' Analyze, memoQ's Statistics, etc.): given a reference TM
and a set of candidate segments (an already-existing corpus file -- e.g.
one produced by ``align_report.run()`` on a bilingual source that hasn't
been translated into the TM yet), bucket each segment by how well its
source text already exists in the TM, so a PM/translator knows how much
of the work is Exact/Fuzzy/New before committing to it.

Banding follows the industry-standard convention (Exact/95-99/85-94/
75-84/50-74/No Match, plus Repetitions counted separately from TM
matches) rather than inventing a new scale -- anyone who has used a CAT
tool's analyze report already knows how to read this one. Deliberately
NOT computing a weighted/discounted word count (the "N effective words"
figure CAT tools get by multiplying each band by a pricing weight): those
weights are shop-specific and belong in whatever report-export layer
consumes this module's output, not baked into the analysis itself.

Matching is restricted to TM entries sharing the candidate's exact
(src_lang, tgt_lang) pair -- a fuzzy match against the wrong language
pair isn't leverage, it's noise.

Same mutate-in-place contract as ``qa.run()``/the aligner: ``analyze()``
populates ``meta['leverage_band']`` / ``meta['leverage_match_pct']`` /
``meta['leverage_repetition']`` on each candidate unit; ``summarize()``
turns that into the aggregate counts a CLI/GUI report wants.
"""
import difflib
import re
import unicodedata

from language_tools.align.splitters import is_cjk_lang

# Bands in the fixed order a report/GUI should render them in (best
# leverage first) -- not a severity or frequency ranking.
BANDS = ['repetition', 'exact', '95-99', '85-94', '75-84', '50-74', 'no_match']

_WHITESPACE_RE = re.compile(r'\s+')


def _normalize(text):
    """Comparison key only -- NOT a substitute for ``tm/clean.py``'s
    normalization (which also feeds writers and must be reversible-ish
    for round-tripping); this one additionally casefolds, since leverage
    matching should not be case-sensitive (Trados/memoQ analyze reports
    aren't either).
    """
    return _WHITESPACE_RE.sub(' ', unicodedata.normalize('NFC', text)).strip().casefold()


def _word_count(text, lang):
    """Character count (whitespace stripped) for CJK languages,
    whitespace-split token count otherwise -- same language-direction
    dispatch ``align/splitters.py`` uses for sentence splitting, reused
    here because the same reasoning applies: CJK has no whitespace
    between words, so a word (=token) count would be meaningless.
    """
    if is_cjk_lang(lang):
        return len(_WHITESPACE_RE.sub('', text))
    text = text.strip()
    return len(text.split()) if text else 0


def _band_for_pct(pct):
    if pct >= 100:
        return 'exact'
    if pct >= 95:
        return '95-99'
    if pct >= 85:
        return '85-94'
    if pct >= 75:
        return '75-84'
    if pct >= 50:
        return '50-74'
    return 'no_match'


def analyze(tm_units, candidate_units, *, fuzzy_floor=0.50):
    """Bands each of ``candidate_units`` against ``tm_units`` by
    source-text match quality, mutating ``meta`` on each candidate in
    place (same contract as ``qa.run()``). Returns nothing.

    ``fuzzy_floor`` (0-1) is the lowest match ratio still counted as a
    match at all; below it a candidate is ``'no_match'`` regardless of
    what ``BANDS`` would otherwise call that percentage. It exists as a
    knob mainly so a caller can raise it to prune more of ``tm_units``
    per candidate via ``difflib.get_close_matches``'s own cutoff (cheaper
    scan over a large TM); lowering it below 0.50 has no visible effect
    since ``_band_for_pct`` has no band below '50-74' to place the result
    in anyway.

    A candidate whose (normalized) source text repeats one seen earlier
    in ``candidate_units`` is banded ``'repetition'`` instead of being
    matched against the TM at all -- once the first occurrence has been
    checked, later identical ones don't need re-checking, matching how
    CAT tools report internal repetitions separately from TM leverage.
    """
    # Index TM source texts (normalized) per language pair, once, rather
    # than re-filtering tm_units for every candidate.
    by_pair = {}
    for u in tm_units:
        by_pair.setdefault((u.src_lang, u.tgt_lang), []).append(_normalize(u.src_text))

    seen = set()
    for u in candidate_units:
        norm = _normalize(u.src_text)

        if norm and norm in seen:
            u.meta['leverage_band'] = 'repetition'
            u.meta['leverage_match_pct'] = 100.0
            u.meta['leverage_repetition'] = True
            continue
        if norm:
            seen.add(norm)
        u.meta['leverage_repetition'] = False

        pool = by_pair.get((u.src_lang, u.tgt_lang), [])
        matches = difflib.get_close_matches(norm, pool, n=1, cutoff=fuzzy_floor) if norm and pool else []
        if not matches:
            u.meta['leverage_band'] = 'no_match'
            u.meta['leverage_match_pct'] = 0.0
            continue

        ratio = difflib.SequenceMatcher(None, norm, matches[0]).ratio()
        pct = round(ratio * 100, 1)
        u.meta['leverage_match_pct'] = pct
        u.meta['leverage_band'] = _band_for_pct(pct)


def summarize(candidate_units):
    """Returns ``{'total': N, 'total_words': N, 'bands': {band: {'count':
    n, 'words': w}}}``, ``bands`` covering every entry in ``BANDS`` (zero
    entries included -- unlike ``qa_report.summarize()``'s ``by_type``, a
    leverage report is read as a full breakdown against a fixed set of
    bands, not a sparse list of what happened to occur, so a GUI table
    doesn't need to know ``BANDS`` separately to render every row).

    Assumes ``analyze()`` has already populated ``meta['leverage_band']``
    on each unit; a unit missing it (candidate list was never analyzed)
    is counted as ``'no_match'``, same default ``analyze()`` itself would
    have assigned an unmatched segment.
    """
    bands = {b: {'count': 0, 'words': 0} for b in BANDS}
    total_words = 0
    for u in candidate_units:
        band = u.meta.get('leverage_band', 'no_match')
        words = _word_count(u.src_text, u.src_lang)
        bands[band]['count'] += 1
        bands[band]['words'] += words
        total_words += words
    return {'total': len(candidate_units), 'total_words': total_words, 'bands': bands}
