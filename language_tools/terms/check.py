"""Term-consistency check (DESIGN.md section 15.1, Phase G1/G3): flags TUs
in a TM whose target text contains a *forbidden* translation for a term
that also appears in the source text -- and, opt-in, TUs whose target text
does NOT use the *approved* translation for a source term that appears.

The forbidden direction is on by default: a hit needs both sides to match
(source has the term AND target has the specific forbidden string for it),
not just "this string appears in the target somewhere": a bare target-only
match would flag any target text that happens to contain the forbidden
string even when the source never mentioned the term it's a bad
translation of, which is exactly the kind of false-positive-prone shortcut
this check is trying to avoid. The approved direction is opt-in via
``check_approved=True`` because the deferred-design note in DESIGN.md 15.1
still stands: synonyms, pronoun back-references, and legitimate rewording
all make "the preferred string didn't literally appear" a weak signal on
its own, so its hits are presented as a to-verify hint list (labeled as
such downstream), not a defect verdict. Two gates keep that weak signal
from turning into guaranteed noise: segments with an empty target are
skipped (an untranslated segment trivially "doesn't use" any term, but
that's ``qa.py``'s EMPTY_TARGET finding, not evidence of rewording), and
only glossary rows whose ``status`` explicitly declared 'approved' are
covered -- rows read from a blank/unrecognized status cell merely *display*
as approved (``glossary.py``'s fallback), so sweeping a whole legacy
status-less glossary into the check on one opt-in tick would bury the
rows someone actually marked in a wall of false hits.

Matching: CJK-language terms match as a plain substring (no word
boundaries -- CJK text has no whitespace between words, same reasoning as
``align/splitters.py``'s ``is_cjk_lang``-gated splitter choice, reused
here rather than re-derived); Latin-script terms match case-insensitively
at a word boundary, so a forbidden term "AI" doesn't fire on "said" or
"main". Which side of a given entry decides CJK-vs-Latin matching is that
entry's own declared ``src_lang``/``tgt_lang`` -- a glossary entry's langs
are expected to already match the corpus it's being checked against;
mismatched pairs just won't find any hits (an all-zero result is a
signal for the *caller* to notice they picked the wrong glossary, not
something this module validates).
"""
import re

from language_tools.align.splitters import is_cjk_lang


def _term_pattern(term, lang):
    escaped = re.escape(term)
    if is_cjk_lang(lang):
        return re.compile(escaped)
    return re.compile(r'\b%s\b' % escaped, re.IGNORECASE)


def _contains_term(text, term, lang):
    if not term or not text:
        return False
    return _term_pattern(term, lang).search(text) is not None


def run(units, glossary, check_approved=False):
    """Mutates each unit's meta in place: 'term_issues', a list of
    {'src_term', 'tgt_term', 'note', 'status'} dicts, one per hit
    (usually empty). ``status`` names the check direction that produced
    the hit ('forbidden' -- the wrong string IS there; 'approved' -- the
    preferred string is NOT there, only produced when ``check_approved``)
    so downstream renderers (CSV/GUI/report) can label hits without
    guessing. Kept as its own meta key rather than folded into
    ``qa.py``'s 'qa_issues' list -- see this module's docstring for why
    term checks are a distinct concern (glossary-driven, per-entry detail
    rather than a fixed enumerable code) from qa.py's structural checks.
    Returns ``units`` for chaining convenience, same shape as ``qa.run()``.
    """
    forbidden_entries = [e for e in glossary if e.status == 'forbidden']
    # ``status_declared`` separates "row explicitly says approved" from
    # "status cell was blank/unrecognized and read() defaulted it" -- the
    # opt-in check only acts on the former (see module docstring).
    approved_entries = ([e for e in glossary
                         if e.status == 'approved' and e.status_declared]
                        if check_approved else [])
    for u in units:
        hits = []
        for entry in forbidden_entries:
            if (_contains_term(u.src_text, entry.src_term, entry.src_lang)
                    and _contains_term(u.tgt_text, entry.tgt_term, entry.tgt_lang)):
                hits.append({
                    'src_term': entry.src_term,
                    'tgt_term': entry.tgt_term,
                    'note': entry.note or '',
                    'status': 'forbidden',
                })
        for entry in approved_entries:
            if not entry.tgt_term or not (u.tgt_text or '').strip():
                # Empty target/term can't evidence "reworded around the
                # approved term": an empty <seg> always "misses" every
                # term, and an entry with no target term to look for
                # would hit unconditionally. Leave those to EMPTY_TARGET.
                continue
            if (_contains_term(u.src_text, entry.src_term, entry.src_lang)
                    and not _contains_term(u.tgt_text, entry.tgt_term, entry.tgt_lang)):
                hits.append({
                    'src_term': entry.src_term,
                    'tgt_term': entry.tgt_term,
                    'note': entry.note or '',
                    'status': 'approved',
                })
        u.meta['term_issues'] = hits
    return units


def summarize(units):
    """Returns {'total': N, 'flagged': N, 'by_status': {status: N}} --
    mirrors ``qa_report.summarize()``'s shape (``by_status`` instead of
    ``by_type``: term hits enumerate by check direction, the only fixed
    categories hits fall into; the per-term detail lives on the hits
    themselves) for the CLI/GUI callers that print/display a summary.
    ``by_status`` only contains directions that actually hit (same
    "no zero-count entries" convention as ``qa_report``).
    """
    total = len(units)
    flagged = 0
    by_status = {}
    for u in units:
        # tolerate units that never went through run() (no key yet) and
        # pre-G3 hits (no 'status' key -- those can only be forbidden)
        hits = u.meta.get('term_issues') or []
        if hits:
            flagged += 1
        for hit in hits:
            status = hit.get('status', 'forbidden')
            by_status[status] = by_status.get(status, 0) + 1
    return {'total': total, 'flagged': flagged, 'by_status': by_status}
