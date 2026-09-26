"""TM statistics: a read-only summary of a corpus, no mutation.

Deliberately separate from ``qa.run()`` -- QA flags *individual* units for
review; this module summarizes the *whole* corpus as aggregate numbers
(for a CLI report or a future GUI dashboard). Callers who want both just
call both; there's no shared state to coordinate.

``aging`` and ``lang_pair_by_domain`` (DESIGN.md 15.2, "语料资产盘点增强")
are corpus-inventory views rather than quality signals -- "how much of
this TM is old, and which language pairs/projects does it actually cover"
is a different question from "is this TM clean", which is what the rest
of this module and ``qa.py`` already answer.

``lang_pair_by_domain``'s domain dimension is honest about a real gap in
the current data model: ``TranslationUnit`` has no ``domain`` field (only
``terms.model.TermEntry`` -- glossary entries -- has one; see DESIGN.md
section on term management), and neither the TMX nor SDLTM reader
captures anything domain-like from the source file today (TMX ``<prop>``
elements aren't parsed at all; SDLTM's ``fields``/``context_groups``
tables aren't read either). Building that out for real would be a new
reader capability, not a "low-cost stats enhancement" -- so this checks
``meta['domain']`` first (the documented escape hatch for exactly this
kind of not-yet-common-across-formats data, per ``model.py``'s
docstring, so a future domain-tagging step -- manual or automated --
plugs in for free), and falls back to each unit's ``source_file``
basename, which every reader already populates and is close cousin to
"domain" in the merge-many-project-TMs-into-one-corpus workflow this
inventory view is actually for: in practice a corpus's project/domain
boundaries usually *are* its constituent files.
"""
import os
import re

_YEAR_RE = re.compile(r'(\d{4})')


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
        'aging': _aging_distribution(units),
        'lang_pair_by_domain': _lang_pair_by_domain_cross_tab(units),
    }


def _aging_distribution(units):
    """``{year: count}`` (plus an ``'unknown'`` bucket), derived from each
    unit's ``modified_at`` -- not ``created_at``: "how stale is this
    translation" is about when it was last touched, not when the segment
    first entered the TM (a segment created in 2019 and re-translated
    last month isn't stale). Year granularity, not finer: this is meant
    to answer "is this TM mostly old or mostly fresh" at a glance, and a
    corpus spanning years is the case this actually matters for -- a
    month-level breakdown would be noise for that question.

    ``modified_at``'s format isn't assumed beyond "starts with a 4-digit
    year" (regex, not ``datetime.strptime`` with one fixed format):
    ``sdltm_writer.py`` writes ``'%Y-%m-%d %H:%M:%S'``, but
    ``sdltm_reader.py``'s own docstring is explicit about also needing to
    open real Trados-native files, which could format timestamps
    differently. Missing/unparseable dates -- every unit from a plain TMX
    read (``tmx_reader.py`` doesn't populate ``modified_at`` at all
    today) included -- land in ``'unknown'`` rather than being dropped or
    raising, same graceful-degradation choice ``merge.py``'s
    ``prefer-newer`` strategy already made for the same field.
    """
    buckets = {}
    for u in units:
        m = _YEAR_RE.match(u.modified_at) if u.modified_at else None
        year = m.group(1) if m else 'unknown'
        buckets[year] = buckets.get(year, 0) + 1
    return buckets


def _lang_pair_by_domain_cross_tab(units):
    """``{lang_pair: {domain_label: count}}`` -- see the module docstring
    for what ``domain_label`` actually is (``meta['domain']`` if present,
    else the unit's ``source_file`` basename, else ``'unknown'``).
    """
    cross = {}
    for u in units:
        pair = '%s-%s' % (u.src_lang, u.tgt_lang)
        domain = u.meta.get('domain') or (
            os.path.basename(u.source_file) if u.source_file else None) or 'unknown'
        by_domain = cross.setdefault(pair, {})
        by_domain[domain] = by_domain.get(domain, 0) + 1
    return cross
