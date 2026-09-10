"""Term-consistency check (DESIGN.md section 15.1, Phase G1): flags TUs in
a TM whose target text contains a *forbidden* translation for a term that
also appears in the source text.

v1 scope is deliberately just this one direction -- see ``model.py``'s
``STATUSES`` docstring for why the 'approved' (preferred-term-missing)
direction is deferred to a later phase. A forbidden-term hit needs both
sides to match (source has the term AND target has the specific forbidden
string for it), not just "this string appears in the target somewhere":
a bare target-only match would flag any target text that happens to
contain the forbidden string even when the source never mentioned the
term it's a bad translation of, which is exactly the kind of
false-positive-prone shortcut this check is trying to avoid by staying
narrow in the first place.

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


def run(units, glossary):
    """Mutates each unit's meta in place: 'term_issues', a list of
    {'src_term', 'tgt_term', 'note'} dicts, one per forbidden hit (usually
    empty). Kept as its own meta key rather than folded into
    ``qa.py``'s 'qa_issues' list -- see this module's docstring for why
    term checks are a distinct concern (glossary-driven, per-entry detail
    rather than a fixed enumerable code) from qa.py's structural checks.
    Returns ``units`` for chaining convenience, same shape as ``qa.run()``.
    """
    forbidden_entries = [e for e in glossary if e.status == 'forbidden']
    for u in units:
        hits = []
        for entry in forbidden_entries:
            if (_contains_term(u.src_text, entry.src_term, entry.src_lang)
                    and _contains_term(u.tgt_text, entry.tgt_term, entry.tgt_lang)):
                hits.append({
                    'src_term': entry.src_term,
                    'tgt_term': entry.tgt_term,
                    'note': entry.note or '',
                })
        u.meta['term_issues'] = hits
    return units


def summarize(units):
    """Returns {'total': N, 'flagged': N} -- mirrors ``qa_report.summarize()``'s
    shape (minus ``by_type``, since term issues aren't a fixed enumerable
    code the way qa_issues are -- each hit names its own term pair) for
    the CLI/GUI callers that print/display a one-line summary.
    """
    total = len(units)
    flagged = sum(1 for u in units if u.meta.get('term_issues'))
    return {'total': total, 'flagged': flagged}
