"""TM statistics: a read-only summary of a corpus, no mutation.

Deliberately separate from ``qa.run()`` -- QA flags *individual* units for
review; this module summarizes the *whole* corpus as aggregate numbers
(for a CLI report or a future GUI dashboard). Callers who want both just
call both; there's no shared state to coordinate.
"""


def compute(units):
    """Returns a dict of corpus-level statistics.

    ``lang_pairs`` maps ``"src-tgt"`` -> count, since a corpus file is not
    guaranteed to be a single language pair throughout (mixed-language
    TMs happen in practice, especially after a merge with ``keep-all``).
    """
    total = len(units)
    seen_pairs = set()
    duplicate_pairs = 0
    empty_source = 0
    empty_target = 0
    lang_pairs = {}
    src_chars = 0
    tgt_chars = 0

    for u in units:
        src, tgt = u.src_text.strip(), u.tgt_text.strip()
        if not src:
            empty_source += 1
        if not tgt:
            empty_target += 1

        key = (src, tgt)
        if key in seen_pairs:
            duplicate_pairs += 1
        else:
            seen_pairs.add(key)

        pair_label = '%s-%s' % (u.src_lang, u.tgt_lang)
        lang_pairs[pair_label] = lang_pairs.get(pair_label, 0) + 1

        src_chars += len(src)
        tgt_chars += len(tgt)

    unique_pairs = len(seen_pairs)
    return {
        'total': total,
        'unique_pairs': unique_pairs,
        'duplicate_pairs': duplicate_pairs,
        'duplicate_rate': duplicate_pairs / total if total else 0.0,
        'empty_source': empty_source,
        'empty_target': empty_target,
        'lang_pairs': lang_pairs,
        'src_chars': src_chars,
        'tgt_chars': tgt_chars,
        'length_ratio': src_chars / tgt_chars if tgt_chars else 0.0,
    }
