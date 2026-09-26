"""Weighted "quote" word-count estimator: turns ``tm.leverage``'s per-band
word counts into the discounted "effective word count" a PM prices a
translation job against (Trados Studio's Analyze / memoQ's Statistics
"weighted words" column), rolled up across a batch of input files.

Deliberately layered on top of ``tm.leverage`` rather than folded into it
-- ``leverage.py``'s own module docstring says a weighted/discounted word
count is "shop-specific and belongs in whatever report-export layer
consumes this module's output, not baked into the analysis itself." This
module is that layer: it owns the weight table (``DEFAULT_WEIGHTS``,
overridable via ``load_weights()``) and the per-file/grand-total rollup;
``tm.leverage`` keeps owning match banding, which this module never
re-implements or re-analyzes.

Each input file is expected to already be a list of ``TranslationUnit``,
read by whichever of the two existing entry points fits its format --
``align_report.run()`` for a bilingual source (docx/xlsx/csv/tsv) not yet
converted into a corpus, or ``tm.io.read_corpus()`` for an already-
converted .tmx/.sdltm candidate corpus. This module doesn't care which:
it only needs the unit lists, so a batch can freely mix both kinds of
input (``tm_cli._cmd_quote`` dispatches by extension the same way
``_cmd_align`` already does).

**The default weight table is one common industry convention, not a
standard.** CAT tools ship broadly similar band -> discount tables, but
the exact cutoffs and percentages are shop-specific pricing policy this
codebase cannot know on a caller's behalf -- see DESIGN.md 15.2's
"报价算法的复杂度" caveat. Before this feeds a real quote, replace
``DEFAULT_WEIGHTS`` with an actual rate card via ``--weights``/
``load_weights()``; treating the built-in numbers as a finished price
list is exactly the mistake that caveat warns against.
"""
import csv as csv_module
import json

from language_tools.tm import leverage as leverage_module

# One common industry convention (see module docstring): Repetitions and
# Exact (100%) matches are typically billed at a token "review" rate --
# here, 0% of the new-word rate baked into total_words -- fuzzy bands get
# a partial discount that shrinks as match quality drops, and anything
# below the 75% band, where most shops' rate cards no longer bother with
# a partial discount, is billed at full (100%) rate.
DEFAULT_WEIGHTS = {
    'repetition': 0.0,
    'exact': 0.0,
    '95-99': 30.0,
    '85-94': 60.0,
    '75-84': 100.0,
    '50-74': 100.0,
    'no_match': 100.0,
}


def load_weights(path):
    """Reads a JSON ``{band: weight_pct}`` rate-card file (``weight_pct``
    0-100). Bands from ``leverage.BANDS`` missing in the file fall back to
    ``DEFAULT_WEIGHTS`` rather than being treated as 0 -- a rate card only
    needs to list the bands it wants to override. A top-level JSON value
    that isn't an object, an unrecognized band key, or an out-of-range
    weight raises ``ValueError``: fail loudly on a rate card typo rather
    than silently mispricing a job.
    """
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('weights file %r must contain a JSON object {band: weight_pct}, '
                          'got %s' % (path, type(data).__name__))
    unknown = set(data) - set(leverage_module.BANDS)
    if unknown:
        raise ValueError('unknown band(s) in weights file %r: %s (expected one of %s)' %
                          (path, sorted(unknown), leverage_module.BANDS))
    weights = dict(DEFAULT_WEIGHTS)
    for band, pct in data.items():
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not (0 <= pct <= 100):
            raise ValueError('weight for band %r in %r must be a number 0-100, got %r' %
                              (band, path, pct))
        weights[band] = float(pct)
    return weights


def weighted_words(leverage_summary, weights=None):
    """Given ``tm.leverage.summarize()``'s ``{'bands': {band: {'words':
    n}}}``, returns ``(weighted_total, per_band_weighted)`` where
    ``per_band_weighted`` is ``{band: weighted_words}`` for every band in
    ``leverage.BANDS`` (zero entries included, same "full breakdown, not a
    sparse list" convention ``leverage.summarize()`` itself uses).
    ``weighted_total`` is a float -- fractional weighted words are
    expected and meaningful, the same way a CAT tool's own weighted-word
    column isn't rounded to an integer; round only at display/export time,
    not here.
    """
    weights = weights or DEFAULT_WEIGHTS
    per_band = {}
    total = 0.0
    for band in leverage_module.BANDS:
        words = leverage_summary['bands'][band]['words']
        w = words * weights.get(band, DEFAULT_WEIGHTS[band]) / 100.0
        per_band[band] = w
        total += w
    return total, per_band


def quote_batch(file_units, tm_units, *, fuzzy_floor=0.50, weights=None):
    """``file_units``: ``{label: [TranslationUnit, ...]}``, one entry per
    input file, already read by whichever reader entry point fits its
    format (see module docstring). ``tm_units``: the reference TM every
    file is leveraged against -- shared across the whole batch, matching
    how a PM prices a multi-file job against one project TM, not a
    separate TM per file.

    Runs ``leverage.analyze()`` per file (mutating that file's units in
    place, same contract ``leverage.analyze()`` itself has) then rolls the
    per-file summaries up into a grand total. Returns::

        {'files': {label: {'summary': <leverage.summarize() shape>,
                            'weighted_total': float,
                            'weighted_bands': {band: float}}},
         'total': {same three keys, across every file's units combined}}

    ``'total'`` is computed by re-summarizing the concatenation of every
    file's units, not by summing the per-file weighted totals -- one
    counting code path for both, and it sidesteps any float-sum drift
    across a batch of many files.
    """
    weights = weights or DEFAULT_WEIGHTS
    files_out = {}
    all_units = []
    for label, units in file_units.items():
        leverage_module.analyze(tm_units, units, fuzzy_floor=fuzzy_floor)
        s = leverage_module.summarize(units)
        wt, wb = weighted_words(s, weights)
        files_out[label] = {'summary': s, 'weighted_total': wt, 'weighted_bands': wb}
        all_units.extend(units)

    total_summary = leverage_module.summarize(all_units)
    total_wt, total_wb = weighted_words(total_summary, weights)
    return {
        'files': files_out,
        'total': {'summary': total_summary, 'weighted_total': total_wt, 'weighted_bands': total_wb},
    }


def write_quote_csv(path, result):
    """Writes one row per input file plus a trailing ``TOTAL`` row: file,
    segments, words, weighted_words, then one column per band's raw word
    count. A quote is read as a per-file/grand-total summary table, not a
    segment-level dump -- for that level of detail on any one file,
    ``leverage``'s own ``--export`` (or ``csv_writer.write(...,
    include_leverage=True)``) already covers it, per that file's units.
    """
    bands = leverage_module.BANDS
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv_module.writer(f)
        w.writerow(['file', 'segments', 'words', 'weighted_words'] + list(bands))
        for label, entry in result['files'].items():
            s = entry['summary']
            w.writerow([label, s['total'], s['total_words'], round(entry['weighted_total'], 1)] +
                       [s['bands'][b]['words'] for b in bands])
        t = result['total']
        w.writerow(['TOTAL', t['summary']['total'], t['summary']['total_words'],
                    round(t['weighted_total'], 1)] +
                   [t['summary']['bands'][b]['words'] for b in bands])
