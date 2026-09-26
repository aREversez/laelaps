"""TM merging: combine multiple corpora into one, with conflict handling.

A "conflict" here is the same normalized source text appearing with more
than one distinct target across the inputs being merged -- the same
condition ``qa.SOURCE_CONFLICT`` flags, just resolved here at merge time
instead of only reported. This module does not itself call the QA layer;
callers who want a conflict report on the merged output should run
``qa.run()`` afterward, which is the existing, already-tested mechanism
for surfacing SOURCE_CONFLICT/TARGET_CONFLICT.

Strategies:

- ``keep-all`` (default): every unit from every input is kept, verbatim,
  in input order. No conflict resolution happens -- this is the safe
  default for "just concatenate these TMs and let a human/QA pass sort
  it out later" rather than silently discarding data.
- ``prefer-first``: when the same source text appears with different
  target text across inputs, keep only the first-seen (src, tgt) pair for
  that source; later conflicting pairs for the same source are dropped.
  Non-conflicting duplicates (same src AND same tgt) are still kept once,
  not treated as a conflict.
- ``prefer-last``: same as prefer-first but the last-seen pair wins.
  Useful when merging in chronological order (oldest TM first, newest
  last) and the newest translation should override older ones.
- ``prefer-newer``: like prefer-last, but ordering is driven by each
  unit's ``modified_at`` field (ISO 8601 string, lexicographically
  comparable) instead of input order. Units with no ``modified_at`` sort
  as older than any unit that has one, so a mix of dated and undated
  input still produces a deterministic result rather than raising.
"""

_STRATEGIES = ('keep-all', 'prefer-first', 'prefer-last', 'prefer-newer')


def merge(unit_lists, *, strategy='keep-all'):
    """``unit_lists`` is an iterable of ``list[TranslationUnit]`` (e.g. one
    per input file, already read via a corpus reader). Returns
    ``(merged_units, report)`` where ``report`` has ``{'input': N,
    'conflicts_resolved': N, 'output': N}``.
    """
    if strategy not in _STRATEGIES:
        raise ValueError('unknown merge strategy %r, expected one of %s' %
                          (strategy, _STRATEGIES))

    flat = [u for units in unit_lists for u in units]
    report = {'input': len(flat), 'conflicts_resolved': 0, 'output': 0}

    if strategy == 'keep-all':
        report['output'] = len(flat)
        return flat, report

    # For prefer-* strategies: walk in the order that should win last,
    # keeping one (src, tgt) winner per normalized source. A later unit
    # with the *same* (src, tgt) as the current winner doesn't count as a
    # conflict (it's the same translation reappearing); only a later unit
    # with a *different* tgt for the same src overwrites and counts.
    ordered = flat if strategy in ('keep-all', 'prefer-last') else list(flat)
    if strategy == 'prefer-first':
        # Walking in reverse and keeping "last seen in this reversed walk"
        # is equivalent to "first seen in original order wins" without a
        # second pass to detect and skip later duplicates.
        ordered = list(reversed(flat))
    elif strategy == 'prefer-newer':
        # Stable sort by modified_at ascending (missing -> treated as the
        # empty string, which sorts before any real timestamp) so the
        # last-wins logic below picks the most-recently-modified unit for
        # each source.
        ordered = sorted(flat, key=lambda u: u.modified_at or '')

    winners = {}  # normalized src -> (tgt, unit)
    for u in ordered:
        src, tgt = u.src_text.strip(), u.tgt_text.strip()
        prev = winners.get(src)
        if prev is not None and prev[0] != tgt:
            report['conflicts_resolved'] += 1
        winners[src] = (tgt, u)

    merged = [entry[1] for entry in winners.values()]
    report['output'] = len(merged)
    return merged, report
