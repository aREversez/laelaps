"""Run the QA checks (``language_tools.qa``) against an already-existing
corpus file (tmx/sdltm), outside the convert pipeline.

``qa.run()`` itself has been usable standalone since it was written --
it's just a function over a unit list. What was missing was the "read an
existing corpus, derive the length ratio the same way the convert
pipeline does, run QA, hand back something a CLI/GUI can summarize and
export" wiring, which is what this module is. Kept in ``language_tools/tm/``
alongside ``clean.py``/``merge.py``/``stats.py`` since it's the same family
of operation: "do something useful to a corpus file you already have",
as opposed to producing one from a bilingual source.
"""
from language_tools import qa as qa_module
from language_tools.tm import io as tm_io

# Every issue string qa.run() can produce, in a fixed display order (rough
# severity/frequency grouping, not alphabetical) -- used by the CLI's
# --type validation and the GUI's filter dropdown so both stay in sync
# with qa.py without hand-copying the list a second time.
ISSUE_TYPES = [
    'EMPTY_SOURCE', 'EMPTY_TARGET', 'LENGTH_RATIO_OUTLIER',
    'NUMBER_MISMATCH', 'PLACEHOLDER_MISMATCH', 'URL_MISMATCH', 'TAG_MISMATCH',
    'SOURCE_CONFLICT', 'TARGET_CONFLICT',
]


def run(input_path):
    """Reads ``input_path``, runs every QA check against it, and returns
    the unit list with ``meta['qa_issues']``/``meta['qa_confidence']``
    populated on each unit (mutated in place by ``qa.run()``, same as the
    convert pipeline does) -- callers needing a report and/or a CSV export
    both start from this same list.
    """
    units = tm_io.read_corpus(input_path)
    ratio = qa_module.expected_length_ratio(units) if units else 1.0
    qa_module.run(units, ratio)
    return units


def summarize(units):
    """Returns ``{'total': N, 'flagged': N, 'by_type': {issue: count}}``.
    ``by_type`` only contains issue types that actually occurred (no
    zero-count entries) -- callers wanting the full ``ISSUE_TYPES`` list
    for a stable filter dropdown should iterate that constant directly
    rather than relying on this dict's key set.
    """
    total = len(units)
    flagged = 0
    by_type = {}
    for u in units:
        issues = u.meta.get('qa_issues', [])
        if issues:
            flagged += 1
        for issue in issues:
            by_type[issue] = by_type.get(issue, 0) + 1
    return {'total': total, 'flagged': flagged, 'by_type': by_type}
