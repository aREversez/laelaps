"""TM cleaning: normalize, then remove low-value/bad segments.

Operates on an already-loaded ``list[TranslationUnit]`` -- callers are
responsible for reading the corpus file first (via ``corpus_readers``) and
writing the result back out (via ``writers``). Keeping this format-agnostic
means it works identically for tmx- and sdltm-sourced units, and for
in-memory units produced by the align pipeline.

Order matters and is fixed, not configurable, because each step's semantics
depend on the previous one having already run:

1. normalize (unicode NFC, whitespace collapse) -- so "duplicate" detection
   in step 2 isn't fooled by two segments that are visually identical but
   byte-different (e.g. one has NBSP, the other a normal space).
2. dedupe (exact src+tgt match, post-normalization)
3. remove empty (either side blank after normalization/stripping)
4. remove identical (src == tgt after normalization) -- optional, off by
   default: for some language pairs (e.g. two segments that are both a
   product name or a number-only segment) src==tgt is legitimate content,
   not a translation defect, so this is opt-in rather than assumed.

Every step is independently toggleable so a caller who only wants dedup
(no normalization side effects on the surviving text) can ask for that.
"""
import re
import unicodedata

_WHITESPACE_RE = re.compile(r'\s+')


def _normalize_text(text):
    """NFC-normalize and collapse internal whitespace runs to a single
    space, then strip leading/trailing whitespace. This is the same
    normalization applied to both src and tgt, independent of language --
    NFC is a no-op for text that's already in composed form (the common
    case for both English and Chinese), so this is safe to apply
    unconditionally rather than trying to detect which side needs it.
    """
    normalized = unicodedata.normalize('NFC', text)
    return _WHITESPACE_RE.sub(' ', normalized).strip()


def clean(units, *, normalize=True, dedupe=True, remove_empty=True,
          remove_identical=False):
    """Returns ``(kept_units, report)``.

    ``report`` is a dict of counts so this can serve as an audit trail
    (e.g. printed by the CLI or shown in a future GUI), not just a silent
    filter: ``{'input': N, 'normalized': N, 'removed_duplicate': N,
    'removed_empty': N, 'removed_identical': N, 'output': N}``.

    Units are never mutated in place -- ``normalize`` (when on) rewrites
    ``src_text``/``tgt_text`` on a shallow-copied unit via
    ``dataclasses.replace``-equivalent field reassignment is avoided in
    favor of just mutating the text fields on the unit objects themselves,
    since TranslationUnit instances here are transient (freshly read from
    a corpus file for this one cleaning pass) rather than shared state the
    caller still holds a reference to elsewhere.
    """
    report = {
        'input': len(units),
        'normalized': 0,
        'removed_duplicate': 0,
        'removed_empty': 0,
        'removed_identical': 0,
        'output': 0,
    }

    working = list(units)

    if normalize:
        for u in working:
            new_src, new_tgt = _normalize_text(u.src_text), _normalize_text(u.tgt_text)
            if new_src != u.src_text or new_tgt != u.tgt_text:
                report['normalized'] += 1
            u.src_text, u.tgt_text = new_src, new_tgt

    kept = []
    seen_pairs = set()
    for u in working:
        src, tgt = u.src_text.strip(), u.tgt_text.strip()

        if remove_empty and (not src or not tgt):
            report['removed_empty'] += 1
            continue

        if remove_identical and src and tgt and src == tgt:
            report['removed_identical'] += 1
            continue

        if dedupe:
            key = (src, tgt)
            if key in seen_pairs:
                report['removed_duplicate'] += 1
                continue
            seen_pairs.add(key)

        kept.append(u)

    report['output'] = len(kept)
    return kept, report
