"""Cross-TM comparison: how do two or more corpora disagree, before you
merge them.

The diagnostic counterpart to ``merge.py``: ``merge()`` resolves conflicts
(or doesn't, with ``keep-all``) without telling you *which* input disagreed
with which -- ``prefer-last`` silently keeps whichever input happened to
come last in the argument list, and that's a bad way to first find out a
disagreement existed. This module answers that question up front: for each
source segment across all the inputs being compared, is it unique to one
TM, does every TM that has it agree on the target, or do two or more TMs
give it different targets (a conflict a human should look at before
picking a merge strategy that would silently paper over it)?

Read-only, like ``stats.py`` -- no mutation, no writing. Matching uses the
same key ``merge.py``'s conflict detection uses (``src_text.strip()`` /
``tgt_text.strip()``, no additional normalization) so "does this module
say these two TMs conflict" and "would ``merge()`` treat this as a
conflict" stay the same question asked two different ways -- comparing
would be misleading if it used a looser or stricter match than the merge
it's meant to inform.
"""
import csv


def compare(named_unit_lists):
    """``named_unit_lists`` is an iterable of ``(label, units)`` pairs, one
    per TM file being compared -- at least 2. Returns a dict:

    ``labels``: the labels, in input order.
    ``totals``: ``{label: N}``, raw unit count per input (not deduplicated).
    ``unique_segments``: ``{label: N}``, count of source segments that
      appear in this TM and no other input being compared.
    ``shared_segments``: count of source segments present in 2+ inputs
      where every input that has it agrees on the target text.
    ``conflicts``: list of ``{'src': text, 'labels': {label: [tgt, ...]}}``,
      one entry per source segment where two or more inputs disagree on
      the target -- ``labels`` only lists the inputs that actually contain
      that source, each with the distinct target(s) that input has for it
      (almost always one; more than one means that single TM already has
      an internal disagreement on this source, surfaced here rather than
      hidden, though ``qa.SOURCE_CONFLICT`` is the tool for diagnosing
      that within one TM). Ordered by each source's first appearance
      across the inputs, for a deterministic report.
    """
    named_unit_lists = list(named_unit_lists)
    if len(named_unit_lists) < 2:
        raise ValueError('compare requires at least 2 inputs, got %d' % len(named_unit_lists))

    labels = [label for label, _ in named_unit_lists]
    totals = {label: len(units) for label, units in named_unit_lists}

    per_label = {label: {} for label in labels}  # label -> {src: {tgt, ...}}
    order = []
    seen = set()
    for label, units in named_unit_lists:
        bucket = per_label[label]
        for u in units:
            src, tgt = u.src_text.strip(), u.tgt_text.strip()
            bucket.setdefault(src, set()).add(tgt)
            if src not in seen:
                seen.add(src)
                order.append(src)

    unique_segments = {label: 0 for label in labels}
    shared_segments = 0
    conflicts = []
    for src in order:
        owners = [label for label in labels if src in per_label[label]]
        if len(owners) == 1:
            unique_segments[owners[0]] += 1
            continue
        union_tgts = set()
        for label in owners:
            union_tgts |= per_label[label][src]
        if len(union_tgts) <= 1:
            shared_segments += 1
        else:
            conflicts.append({
                'src': src,
                'labels': {label: sorted(per_label[label][src]) for label in owners},
            })

    return {
        'labels': labels,
        'totals': totals,
        'unique_segments': unique_segments,
        'shared_segments': shared_segments,
        'conflicts': conflicts,
    }


def write_conflicts_csv(path, report):
    """Writes ``report['conflicts']`` to a CSV review sheet: one row per
    conflicting source, one column per label in ``report['labels']``
    holding that label's target(s) (semicolon-joined when a label has more
    than one, blank when that label doesn't contain the source at all).

    Not in ``writers/csv_writer.py``: every writer there produces one row
    per ``TranslationUnit`` with a fixed src/tgt column pair -- this sheet
    has a variable number of columns (one per TM being compared) and no
    single unit backing each row, so it doesn't fit that shape.
    """
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['source'] + report['labels'])
        for entry in report['conflicts']:
            row = [entry['src']]
            for label in report['labels']:
                targets = entry['labels'].get(label, [])
                row.append(';'.join(targets))
            w.writerow(row)
