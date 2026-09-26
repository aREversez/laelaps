"""Fuzzy near-duplicate clustering: groups TM entries that are *almost*
the same segment (one word/number/half-sentence changed) rather than
byte-identical, so a reviewer can decide which of each cluster to keep.

``tm.clean.clean()``'s ``dedupe`` step only removes exact (post-
normalization) duplicates -- the far more common case in a real TM is a
handful of near-duplicates that drifted apart over time (a price updated,
a placeholder renumbered, a typo fixed in one copy but not the other).
This module is the "did we basically translate this twice" check that
sits next to, not instead of, ``clean()``'s exact dedup: run ``clean()``
first if you also want exact duplicates gone, since this module doesn't
touch those (see ``find_clusters()``'s docstring on empty/already-exact
entries).

**Not minhash.** DESIGN.md 15.2 named "编辑距离或 minhash 分簇" as the
candidate approach; this module implements the former (``difflib``
edit-distance ratio, the same metric and normalization ``tm.leverage``
already uses for its own fuzzy-match bands, reused here for a consistent
notion of "how similar" across the codebase) with a length-bound pruning
step instead of full pairwise comparison. The pruning is exact for that
metric's own definition (see ``_max_length_ratio()``'s docstring, including
a narrow caveat about the metric's own tie-breaking) -- it never discards a
pair that could reach ``threshold`` -- so this trades minhash/LSH's better
asymptotic scaling on very large corpora for an implementation with no
approximation risk from the pruning step, on a single-TM-sized corpus. If a
production-scale TM (hundreds of thousands of entries,
especially ones with many same-length near-duplicates clustered together)
turns out to make this too slow in practice, minhash/LSH banding is the
documented upgrade path, not a redesign of this module's clustering
semantics.

**Clustering is by connected components, not exhaustive pairwise
membership.** If A~B and B~C both clear ``threshold`` but A~C does not,
A/B/C still land in one cluster together (transitive closure of the
pairwise match graph) -- standard behavior for this kind of clustering,
but it does mean a cluster can contain a pair that, compared directly,
looks less similar than ``threshold`` would suggest. A human reviewer
deciding which entries in a cluster to keep should look at the actual
text, not assume every pair within a cluster is equally close.
"""
import csv
import re
import unicodedata
from difflib import SequenceMatcher

_WHITESPACE_RE = re.compile(r'\s+')


def _normalize(text):
    """Same normalization ``tm.leverage._normalize()`` uses (NFC +
    whitespace-collapse + casefold) -- kept as a separate copy rather than
    importing that module-private helper, matching how ``tm.clean`` and
    ``tm.leverage`` each already keep their own local normalize function
    instead of sharing one across modules.
    """
    return _WHITESPACE_RE.sub(' ', unicodedata.normalize('NFC', text)).strip().casefold()


def _max_length_ratio(threshold):
    """For ``SequenceMatcher.ratio() = 2*M / (len(a) + len(b))`` with
    ``M <= min(len(a), len(b))`` -- true regardless of which sequence is
    passed first, so this bound holds either way -- a ratio of at least
    ``threshold`` forces ``max(len(a), len(b)) <= min(len(a), len(b)) *
    (2 - threshold) / threshold``. That bound is exact (derived from the
    metric's own definition, not estimated), so filtering out any pair
    whose lengths fall outside it cannot discard a pair that could reach
    ``threshold`` in either comparison order -- only comparisons that
    could not possibly reach it are skipped.

    One caveat this bound does NOT paper over: ``difflib.SequenceMatcher``
    itself can very rarely return a slightly different ratio depending on
    which sequence is passed first, when the two sequences contain
    equal-length matching blocks and its tie-breaking has to pick one --
    a documented property of the underlying algorithm, not something
    unique to this module (``tm.leverage`` calls the same metric, in a
    fixed argument order, with the same property). In practice this only
    matters for a pair sitting almost exactly on ``threshold``, and
    ``find_clusters()`` always compares the shorter text first (see its
    loop) for a fixed, reproducible order -- it does not attempt to
    "fix" the asymmetry by comparing both orders and taking a max, which
    would double the comparison cost for a caveat this narrow.
    """
    return (2 - threshold) / threshold


def find_clusters(units, *, threshold=0.85, side='src', min_cluster_size=2):
    """Groups ``units`` whose ``side`` text (``'src'`` or ``'tgt'``) is a
    near-duplicate of another's (edit-distance ratio >= ``threshold``,
    after normalization -- see module docstring). Units with an empty
    ``side`` text after normalization are excluded entirely (run
    ``tm.clean.clean(..., remove_empty=True)`` first if those should be
    gone rather than silently skipped here).

    Returns a list of ``{'units': [TranslationUnit, ...], 'size': N}``
    dicts, largest cluster first, containing only clusters that reached
    ``min_cluster_size`` (default 2 -- a "cluster" of one entry isn't a
    near-duplicate of anything). Unit order within a cluster follows
    ``units``' original order, not similarity rank.
    """
    if not (0.0 < threshold <= 1.0):
        raise ValueError('threshold must be in (0, 1], got %r' % threshold)

    texts = [_normalize(u.tgt_text if side == 'tgt' else u.src_text) for u in units]
    candidate_idx = [i for i, t in enumerate(texts) if t]
    order = sorted(candidate_idx, key=lambda i: len(texts[i]))

    parent = {i: i for i in candidate_idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    max_ratio = _max_length_ratio(threshold)
    for pos, i in enumerate(order):
        li = len(texts[i])
        for pos2 in range(pos + 1, len(order)):
            j = order[pos2]
            lj = len(texts[j])
            if lj > li * max_ratio:
                break  # `order` is length-sorted -- no further j can reach threshold
            if SequenceMatcher(None, texts[i], texts[j]).ratio() >= threshold:
                union(i, j)

    groups = {}
    for i in candidate_idx:
        groups.setdefault(find(i), []).append(i)

    clusters = [{'units': [units[i] for i in sorted(idxs)], 'size': len(idxs)}
                for idxs in groups.values() if len(idxs) >= min_cluster_size]
    clusters.sort(key=lambda c: -c['size'])
    return clusters


def summarize(clusters):
    """Returns ``{'cluster_count': N, 'total_units': N}`` -- ``total_units``
    is how many TM entries sit inside *some* cluster (i.e. have at least
    one near-duplicate), not the corpus size passed to ``find_clusters()``.
    """
    return {'cluster_count': len(clusters), 'total_units': sum(c['size'] for c in clusters)}


def write_clusters_csv(path, clusters):
    """Writes one row per unit, grouped by cluster (``cluster_id`` column,
    1-based in cluster-size order -- the same order ``find_clusters()``
    returns) so a reviewer sorting/filtering the sheet by that column sees
    each cluster's entries together. Includes ``source_file`` (when a unit
    has one -- populated for units read from a bilingual source via
    ``align_report.run()``, ``None``/blank for most corpus-read units)
    since "which file did each near-duplicate come from" is often exactly
    what a reviewer needs to decide which copy to keep.
    """
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['cluster_id', 'cluster_size', 'src_text', 'tgt_text', 'source_file'])
        for cluster_id, cluster in enumerate(clusters, 1):
            for u in cluster['units']:
                w.writerow([cluster_id, cluster['size'], u.src_text, u.tgt_text,
                            u.source_file or ''])
