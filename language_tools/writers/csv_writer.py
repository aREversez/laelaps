"""Write a CSV alignment review sheet. The only writer with truly
deterministic byte-for-byte output (no guid/timestamp embedded), so it's the
one place a byte-identical regression comparison is valid.

Deliberately does NOT skip empty-src/tgt rows, unlike the sdltm/tmx
writers -- this preserves the seed script's exact behavior (its sdltm/tmx
writers filter empty pairs, its CSV loop does not). That inconsistency is
arguably a feature for a human-review sheet: it lets a reviewer see gaps
the TM writers silently dropped. Not changing it in Phase 1 without an
explicit decision; flagged in the design doc for follow-up if it turns out
to be unwanted.

Column headers default to the literal strings 'EN'/'ZH' regardless of the
actual --src/--tgt language codes, matching the seed script's behavior
exactly (it hardcoded the header text). This mislabels reversed-direction
conversions (a zh-CN->en-US run still gets an "EN,ZH" header) -- a
pre-existing quirk kept as-is for Phase 1 fidelity, not fixed silently.

``include_qa=True`` appends confidence/status/issues columns from
``qa.run()`` (Phase 2). Defaults to False so the Phase 1 regression
baseline's exact 3-column shape is untouched unless a caller opts in.

The ``issues`` column renders each code as "<Chinese label>(<CODE>)"
(e.g. "标签不匹配(TAG_MISMATCH)") rather than just the raw code -- this
sheet is read by a human reviewer (a translator/LSP QA person, not
another program), and a bare ``TAG_MISMATCH`` string means nothing to
someone who didn't write the QA checks. The raw code stays present in
parentheses rather than being dropped entirely: it keeps the column
grep/filter-friendly (Excel's "contains TAG_MISMATCH" still works) and
keeps it unambiguous which check actually fired, since two different
checks could plausibly get similar-sounding Chinese labels. Labels come
from ``qa.ISSUE_LABELS`` -- the single source of truth also used by the
QA-check GUI page, so the wording can't drift between the two.

``include_align=True`` appends paragraph/align_move columns from
``align_report.run()``. Same "<Chinese label>(<CODE>)" treatment as
``issues``, this time from ``aligner.MOVE_LABELS`` (not
``align_report.py``'s re-export of it -- importing from ``align_report``
here would create a cycle, since that module imports ``api.py``, which
imports this one). ``paragraph`` is ``source_key`` -- present so a
reviewer scanning the sheet can see which rows came from the same source
paragraph (several rows sharing a paragraph number means that paragraph
split into multiple sentences; useful context alongside align_move on
each individual row).

``include_terms=True`` appends a 术语问题 column from
``terms.check.run()``'s ``meta['term_issues']``. Unlike ``issues``
(``qa.ISSUE_LABELS``-backed fixed codes), a term hit has no enumerable
code to look up a label for -- each hit names its own glossary entry --
so the cell is rendered directly as "<src_term> -> <tgt_term>" pairs
(semicolon-joined for multiple hits on one row), with the entry's note
appended in parentheses when present.
"""
import csv

from language_tools import qa
from language_tools.align.aligner import MOVE_LABELS


def _format_issue(issue_code):
    label = qa.ISSUE_LABELS.get(issue_code)
    return '%s(%s)' % (label, issue_code) if label else issue_code


def _format_move(move_code):
    label = MOVE_LABELS.get(move_code)
    return '%s(%s)' % (label, move_code) if label else move_code


def _format_term_hit(hit):
    text = '%s->%s' % (hit['src_term'], hit['tgt_term'])
    return '%s(%s)' % (text, hit['note']) if hit.get('note') else text


def write(path, units, src_label='EN', tgt_label='ZH', include_qa=False, include_align=False,
          include_terms=False):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        header = ['No', src_label, tgt_label]
        if include_align:
            header += ['paragraph', 'align_move']
        if include_qa:
            header += ['confidence', 'status', 'issues']
        if include_terms:
            header += ['term_issues']
        w.writerow(header)
        for i, u in enumerate(units, 1):
            row = [i, u.src_text.strip(), u.tgt_text.strip()]
            if include_align:
                row += [u.source_key or '', _format_move(u.meta.get('align_move', ''))]
            if include_qa:
                issues = u.meta.get('qa_issues', [])
                conf = u.meta.get('qa_confidence', 1.0)
                status = 'HIGH' if not issues else ('LOW' if conf < 0.5 else 'MEDIUM')
                row += ['%.2f' % conf, status, ';'.join(_format_issue(i) for i in issues)]
            if include_terms:
                hits = u.meta.get('term_issues', [])
                row += [';'.join(_format_term_hit(h) for h in hits)]
            w.writerow(row)
