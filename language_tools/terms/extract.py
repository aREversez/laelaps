"""Term-candidate extraction: statistical (not linguistic) suggestions
for a human to review before anything reaches the glossary, per DESIGN.md
15.2's 术语提取 item and the precision caveat recorded against it.

**Read this before trusting any output.** This is frequency + cohesion
statistics over the corpus you feed it -- there is no part-of-speech
tagging, no dictionary, no CJK word segmenter, and no real bilingual
alignment model anywhere in this module. It surfaces *candidates*:
strings that occur often enough and hang together tightly enough to be
worth a terminologist's ten seconds of judgment, nothing more. Concretely:

- **CJK candidates are character n-grams, not word-segmented terms.**
  There is no jieba/word-segmentation dependency in this codebase, so
  Chinese/Japanese/Korean candidates come from sliding a character window
  (``_cjk_ngrams()``) with an internal-cohesion filter (``_cjk_cohesive()``
  -- a cheap co-occurrence-ratio proxy, deliberately NOT called PMI here
  since it isn't corpus-probability-normalized like true PMI would be) to
  cut down on arbitrary substrings. It will produce genuine terms
  alongside plausible-looking non-term fragments. The fuller technique
  this is a simplified cousin of -- boundary-entropy-based "new word
  discovery" -- is NOT implemented; treat every CJK hit as lower-
  confidence than a Latin-script one, not equally trustworthy.
- **Matching is case-sensitive and has no lemmatization/stemming.**
  "Machine Learning" and "machine learning" are counted as two different
  candidates. Not a design choice worth defending, just an unaddressed
  gap -- normalize your input first if that matters for your corpus.
- **Bilingual pairing (``suggest_bilingual_candidates()``) is a
  co-occurrence heuristic, not term alignment.** It has no notion of
  grammar or word order -- it only asks "does this tgt-side candidate
  show up suspiciously often in the same units as this src-side
  candidate, and suspiciously rarely elsewhere". That catches real 1:1
  term pairs reasonably well given a large-enough corpus; a small corpus
  (fewer than a few dozen units containing a given candidate) simply
  won't have enough signal to say anything, and most of a small corpus's
  src candidates should end up with no tgt suggestion at all
  (``tgt_term=''``) rather than a low-confidence guess -- an empty
  suggestion is the expected, common outcome here, not a failure.
- **Not optimized for very large corpora.** The nested-candidate filter
  (``_drop_nested()``) is O(n^2) in the candidate count, and
  ``suggest_bilingual_candidates()`` re-scans the unit list once per
  src candidate. Fine for a single document or a modest TM; something
  that starts to hurt is a real possibility on a large corpus with
  ``--top-n`` set high -- narrow ``min_freq``/``top_n`` first if it does.
- **Every candidate is a suggestion, never a glossary entry on its own.**
  ``write_candidates_csv()``/``promote_reviewed_candidates()`` exist
  specifically to force one explicit human decision per row before
  anything reaches ``glossary.write()`` -- see their docstrings.

If a first run on real data comes back mostly noise, that is the expected
result of running a statistical extractor with no linguistic resources,
not a bug to file against this module -- narrowing ``min_freq``/
``max_ngram`` or supplying a longer ``stopwords`` list is the available
lever, not a promise of higher precision.
"""
import csv
import math
import re
from collections import Counter

from language_tools.align.splitters import is_cjk_lang
from language_tools.terms.model import TermEntry

_WHITESPACE_RE = re.compile(r'\s+')
# Letters only (any script), with an internal apostrophe allowed
# ("don't", "translator's") -- deliberately not splitting on that.
_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)*", re.UNICODE)

# Small built-in stopword lists used to filter candidates -- a bare
# stopword (length 1) is dropped outright, and a multi-token/multi-
# character candidate starting or ending on one is also dropped. Not a
# general-purpose stopword filter, and not remotely exhaustive. Pass
# `stopwords` to extract_candidates()/suggest_bilingual_candidates() for
# anything beyond this.
EN_STOPWORDS = frozenset(
    "a an the and or but of to in on at for with by from as is are was "
    "were be been being this that these those it its not no".split())

CJK_EDGE_CHARS = frozenset('的了是在和与及其之也就都还又要将把被让给对从到于并且但而如若')

CANDIDATE_COLUMNS = ['src_term', 'tgt_term', 'decision', 'status', 'domain', 'note',
                      'src_freq', 'pair_freq', 'concentration']


def _token_ngrams(text, n):
    tokens = _TOKEN_RE.findall(text)
    return [' '.join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _cjk_ngrams(text, n):
    chars = _WHITESPACE_RE.sub('', text)
    return [chars[i:i + n] for i in range(len(chars) - n + 1)]


def _cjk_cohesive(gram, freq):
    """True PMI would need corpus-wide unigram probabilities, which this
    module doesn't track; this is a cheaper proxy that filters out most
    arbitrary character runs without it. For every way to split ``gram``
    into two non-empty halves, requires the whole n-gram's frequency to
    be at least a fixed fraction of the *rarer* half's frequency: a run
    that only ever appears with both halves already glued together has
    ``gram_freq`` close to ``min(left_freq, right_freq)``; two characters
    that just happen to sit next to each other sometimes will have
    ``gram_freq`` far below that minimum. All split points must pass --
    a chain is as cohesive as its weakest link.
    """
    for i in range(1, len(gram)):
        left_freq = freq.get(gram[:i], 0)
        right_freq = freq.get(gram[i:], 0)
        if left_freq == 0 or right_freq == 0:
            return False
        if freq[gram] < 0.15 * min(left_freq, right_freq):
            return False
    return True


def _contains_token_ngram(text, needle):
    """Whitespace-bounded substring check for a token-ngram candidate
    against a (non-CJK) unit's text -- padding with spaces so "cat"
    doesn't match inside "category".
    """
    tokens = _TOKEN_RE.findall(text)
    joined = ' ' + ' '.join(tokens) + ' '
    return (' ' + needle + ' ') in joined


def _drop_nested(candidates):
    """Drops a candidate that is wholly contained in an already-kept,
    comparable-or-higher-frequency longer candidate -- once "机器翻译" is
    kept, "机器"/"翻译" turning up at a similar frequency are noise, not
    independent findings, so they're dropped rather than cluttering the
    list at the same rank. ``candidates`` is assumed pre-sorted by score
    (descending), so a later, lower-ranked entry is checked against
    earlier, higher-ranked ones only.
    """
    kept = []
    for c in candidates:
        nested = False
        for k in kept:
            if c['freq'] > k['freq'] * 1.2:
                continue
            contained = (c['text'] in k['text'] if c['cjk'] else
                         (' ' + c['text'] + ' ') in (' ' + k['text'] + ' '))
            if contained:
                nested = True
                break
        if not nested:
            kept.append(c)
    return kept


def extract_candidates(units, lang, *, side='src', min_freq=2, min_ngram=1, max_ngram=4,
                        stopwords=None, top_n=None):
    """Frequency-ranked term candidates from ``units``'s ``src_text``
    (``side='src'``) or ``tgt_text`` (``side='tgt'``), restricted to units
    whose corresponding language field equals ``lang``. See the module
    docstring for what this can and cannot do.

    Returns a list of dicts ``{'text', 'freq', 'length', 'score'}``,
    highest-scoring first (``score`` favors higher frequency, with a mild
    boost for longer candidates at comparable frequency -- not a claim to
    any named academic term-extraction metric, just a simple monotonic
    ranking). A candidate wholly nested inside a longer, comparably-
    frequent kept candidate is dropped -- see ``_drop_nested()``.
    """
    texts = [(u.tgt_text if side == 'tgt' else u.src_text) for u in units
             if (u.tgt_lang if side == 'tgt' else u.src_lang) == lang]
    cjk = is_cjk_lang(lang)
    edge = stopwords if stopwords is not None else (CJK_EDGE_CHARS if cjk else EN_STOPWORDS)

    # Frequencies are always built across the full 1..max_ngram range
    # (not just [min_ngram, max_ngram]) because the CJK cohesion filter
    # needs unigram/shorter-gram frequencies to score longer candidates,
    # even when the caller only wants length>=2 candidates back.
    freq = Counter()
    for text in texts:
        for n in range(1, max_ngram + 1):
            for gram in (_cjk_ngrams(text, n) if cjk else _token_ngrams(text, n)):
                freq[gram] += 1

    candidates = []
    for gram, f in freq.items():
        length = len(gram) if cjk else gram.count(' ') + 1
        if length < min_ngram or length > max_ngram or f < min_freq:
            continue
        if length == 1:
            if gram in edge:
                continue
        else:
            parts = gram if cjk else gram.split(' ')
            if parts[0] in edge or parts[-1] in edge:
                continue
            if cjk and not _cjk_cohesive(gram, freq):
                continue
        candidates.append({'text': gram, 'freq': f, 'length': length,
                            'score': f * math.log2(length + 1), 'cjk': cjk})

    candidates.sort(key=lambda c: (-c['score'], -c['freq'], -c['length']))
    candidates = _drop_nested(candidates)
    candidates = [{k: v for k, v in c.items() if k != 'cjk'} for c in candidates]
    # ``is not None`` (not a bare truthiness check): top_n=0 is a legitimate
    # request for "no candidates", but `if top_n` treats 0 as falsy and
    # returns the full list instead.
    return candidates[:top_n] if top_n is not None else candidates


def suggest_bilingual_candidates(units, src_lang, tgt_lang, *, min_freq=2, max_ngram=4,
                                  top_n=50, src_stopwords=None, tgt_stopwords=None,
                                  min_pair_freq=2, concentration_floor=3.0):
    """For the top ``top_n`` src-side candidates (``extract_candidates()``
    on ``src_text``), suggests a ``tgt_term`` translation guess by a
    co-occurrence heuristic -- see the module docstring's "Bilingual
    pairing" caveat before trusting any of these.

    Returns a list of dicts ``{'src_term', 'src_freq', 'src_score',
    'tgt_term', 'pair_freq', 'concentration'}``. ``tgt_term``/
    ``pair_freq``/``concentration`` are ``''``/``0``/``0.0`` when no
    tgt-side candidate cleared both ``min_pair_freq`` co-occurrences and
    ``concentration_floor`` -- an empty suggestion is the expected,
    common outcome, not a failure.

    Method: for each src candidate, splits the (src_lang, tgt_lang) units
    into those whose ``src_text`` contains it (``local``) and the rest.
    Extracts tgt candidates from ``local`` only and, for each, compares
    how often it shows up per-unit in ``local`` against how often it
    shows up per-unit across every (src_lang, tgt_lang) unit
    (``concentration = local_rate / global_rate``) -- "how concentrated is
    this tgt string near this src string, relative to how often it shows
    up everywhere". The candidate with the highest concentration (ties
    broken by co-occurrence count) is the suggestion, gated on both
    ``pair_freq >= min_pair_freq`` and ``concentration >=
    concentration_floor`` -- either threshold failing means "not enough
    or not clean enough signal", not "second-best guess", so the row is
    left blank rather than filled with a low-confidence guess dressed up
    as a suggestion.
    """
    src_candidates = extract_candidates(
        units, src_lang, side='src', min_freq=min_freq, max_ngram=max_ngram,
        stopwords=src_stopwords, top_n=top_n)

    pair_units = [u for u in units if u.src_lang == src_lang and u.tgt_lang == tgt_lang]
    n_total = len(pair_units)
    cjk_src = is_cjk_lang(src_lang)

    global_candidates = {
        c['text']: c['freq'] for c in
        extract_candidates(pair_units, tgt_lang, side='tgt', min_freq=1,
                            max_ngram=max_ngram, stopwords=tgt_stopwords)
    }

    results = []
    for sc in src_candidates:
        needle = sc['text']
        local_units = [u for u in pair_units
                       if (needle in u.src_text if cjk_src else
                           _contains_token_ngram(u.src_text, needle))]
        n_local = len(local_units)
        entry = {'src_term': sc['text'], 'src_freq': sc['freq'], 'src_score': sc['score'],
                 'tgt_term': '', 'pair_freq': 0, 'concentration': 0.0}
        if n_local >= min_pair_freq and n_total:
            local_candidates = extract_candidates(
                local_units, tgt_lang, side='tgt', min_freq=1, max_ngram=max_ngram,
                stopwords=tgt_stopwords)
            best = None
            for tc in local_candidates:
                pair_freq = tc['freq']
                if pair_freq < min_pair_freq:
                    continue
                global_freq = global_candidates.get(tc['text'], pair_freq)
                local_rate = pair_freq / n_local
                global_rate = global_freq / n_total
                concentration = local_rate / max(global_rate, 1e-6)
                if (best is None or concentration > best[1] or
                        (concentration == best[1] and pair_freq > best[2])):
                    best = (tc, concentration, pair_freq)
            if best is not None and best[1] >= concentration_floor:
                tc, concentration, pair_freq = best
                entry.update(tgt_term=tc['text'], pair_freq=pair_freq,
                              concentration=round(concentration, 2))
        results.append(entry)
    return results


def write_candidates_csv(path, candidates):
    """Writes a review sheet for a human to work through before anything
    reaches a real glossary -- deliberately NOT the same column shape as
    ``glossary.write()``'s output (see ``promote_reviewed_candidates()``):
    ``decision`` starts blank on every row, and only a row a reviewer
    marks ``decision='approve'`` (after editing ``tgt_term``/``status``/
    ``domain``/``note``, or leaving them as extracted) is ever promoted.
    ``src_freq``/``pair_freq``/``concentration`` are read-only reference
    numbers for the reviewer's judgment call, never written back by
    ``promote_reviewed_candidates()``.
    """
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(CANDIDATE_COLUMNS)
        for c in candidates:
            w.writerow([c['src_term'], c.get('tgt_term', ''), '', '', '', '',
                        c.get('src_freq', ''), c.get('pair_freq', ''),
                        c.get('concentration', '')])


def promote_reviewed_candidates(path, src_lang, tgt_lang):
    """Reads a review sheet written by ``write_candidates_csv()`` (and
    then edited by a human) and returns the ``TermEntry`` list for rows
    the reviewer marked ``decision='approve'`` (case-insensitive, cell
    trimmed) -- every other row (blank, ``'reject'``, or anything else)
    is silently dropped. This is the one deliberate gate between
    "statistical suggestion" and "glossary entry": nothing promotes
    without an explicit per-row decision.

    ``status`` defaults to ``'approved'`` when the reviewer left it blank
    on an approved row (matching ``glossary.read()``'s own undeclared-
    status default). A blank ``tgt_term`` on an approved row raises
    ``ValueError`` -- approving a src-only extraction hit with no
    translation filled in is almost always a reviewer oversight, not an
    entry meant to round-trip into the glossary empty.
    """
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    idx = {name: header.index(name) for name in CANDIDATE_COLUMNS if name in header}
    missing = [c for c in ('src_term', 'tgt_term', 'decision') if c not in idx]
    if missing:
        raise ValueError('candidate review sheet %r is missing required column(s) %s' %
                          (path, missing))

    def cell(cells, name):
        i = idx.get(name)
        return cells[i].strip() if i is not None and i < len(cells) else ''

    entries = []
    for row_number, cells in enumerate(rows[1:], 2):
        if not any((c or '').strip() for c in cells):
            continue
        if cell(cells, 'decision').lower() != 'approve':
            continue
        src_term = cell(cells, 'src_term')
        tgt_term = cell(cells, 'tgt_term')
        if not tgt_term:
            raise ValueError(
                'row %d in %r is approved but has no tgt_term -- fill in a translation '
                'before approving, or change decision away from \'approve\'' %
                (row_number, path))
        status_cell = cell(cells, 'status').lower()
        status = status_cell if status_cell in ('approved', 'forbidden') else 'approved'
        entries.append(TermEntry(
            src_lang=src_lang, tgt_lang=tgt_lang, src_term=src_term, tgt_term=tgt_term,
            status=status, domain=cell(cells, 'domain') or None,
            note=cell(cells, 'note') or None))
    return entries
