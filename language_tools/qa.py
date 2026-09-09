"""Lightweight QA layer (DESIGN.md section 9). Runs after alignment, before
writing: flags likely-bad TUs for human review rather than blocking them.

v1 scope was deliberately four checks: empty segment, length-ratio outlier,
translation-consistency conflict, number mismatch. Tag/placeholder/URL
checks were deferred until a tagged input format actually existed to test
them against (see DESIGN.md section 9) -- adding them earlier would have
been untested surface area with no real input to validate against.

v2 (this commit) adds those three now that ``tmx_reader`` populates
``src_markup``/``tgt_markup`` for TMX ``<seg>`` elements containing inline
tags (bpt/ept/ph/hi/...), so there is real tagged input to test against:

- TAG_MISMATCH: compares inline-tag *type counts* between src_markup and
  tgt_markup (e.g. one ``<bpt>``/``<ept>`` pair on each side). Deliberately
  narrow, matching the project's existing caution about not over-building
  (see NUMBER_MISMATCH notes below): this does NOT verify tag *order*,
  *id*-pairing (TMX ``bpt i="1"``/``ept i="1"``), or nesting -- only that
  the same tag types appear the same number of times on both sides. A
  translator who drops a formatting tag, or a tool that mangles one, still
  gets caught; a translator who legitimately reorders "<b>bold</b> text"
  to "text <b>bold</b>" does not get flagged for reordering, which is
  correct (reordering inline formatting to fit target-language word order
  is normal, not a defect). Units with no markup on either side (the
  common case -- plain-text TUs from docx/xlsx/csv, or TMX <seg> with no
  child elements) are skipped entirely, same as before this check existed.
- PLACEHOLDER_MISMATCH: compares the *set* of placeholder tokens (``{name}``,
  ``{0}``, ``%s``, ``%d``, ``%(name)s``) found in the visible src/tgt text.
  Placeholders are code, not prose -- a translation must reproduce them
  exactly, unlike numbers (which can be reformatted) or tags (which can be
  reordered). Case-sensitive, exact-string comparison for that reason.
- URL_MISMATCH: compares the set of ``http(s)://`` URLs found in src/tgt
  text. A URL dropped or altered in translation is almost always a defect
  (broken/missing link), so this stays a straight set-equality check with
  no fuzzy tolerance.

Number normalization: the original NUMBER_MISMATCH
check compared raw digit-with-optional-decimal-separator matches between
src and tgt -- which false-fires on common legitimate formatting variation
like ``$1,000`` vs ``1000 dollars`` (the thousands-separator comma makes
the regex see "1,000" vs "1000" as different numbers). We now normalize
before comparison:

- Strip thousands separators (`,` and `.` between groups of 3 digits when
  both sides are 4+ digits; CJK fullwidth comma `，` too)
- Treat `.` and `,` decimal separators as equivalent
- Drop trailing-zero decimals (``1.20`` == ``1.2``)
- Strip currency symbols and the surrounding letters ``$``, ``€``, ``¥``,
  ``USD``, ``RMB``, ``CNY`` -- the check is about *numeric* content, not
  currency formatting, and a translation that writes "1000 dollars" for
  "$1,000" is correct, not a mismatch

Caveats kept deliberately narrow (DESIGN.md says don't over-build):
we do NOT collapse ranges (``1-3`` vs ``1 to 3``), do NOT match spelled-out
numbers (``two`` vs ``2``), do NOT track units (``5 km`` vs ``3 miles``).
Real translation mismatches in those cases are a different check.
"""
import re

from language_tools.align.splitters import nolen

# Raw number matcher -- same as before, used internally by the normalizer.
_RAW_DIGIT_RE = re.compile(r'\d+(?:[.,]\d+)?')

# Currency-prefix stripper: matched greedily, kept narrow on purpose.
# Adding every ISO currency code would balloon this list without a real
# false-positive reduction -- the most common offenders ($, €, ¥, USD,
# RMB, CNY) cover the vast majority of real-world bilingual TMs.
_CURRENCY_RE = re.compile(
    r'(?:USD|EUR|CNY|RMB|GBP|JPY|\$|€|¥|£)\s*', re.IGNORECASE)

# Thousands-separator: a comma or period (or CJK fullwidth comma) between
# two groups of exactly 3 digits, where the left group has at least one
# more digit ahead of it. Anchored so it doesn't misfire inside "1,234"
# style dates or versions that aren't actually thousands separators.
_THOUSANDS_RE = re.compile(
    r'(?<=\d)[.,，](?=\d{3}(?:\D|$))')

# Decimal-separator normalizer: turns both "1.5" and "1,5" into "1.5" so
# the rest of the comparison can treat them as the same number. Doesn't
# distinguish locale (some locales use , for decimal and . for thousands)
# -- we already stripped thousands separators above, so a single
# remaining separator is the decimal one.
_DECIMAL_RE = re.compile(r'(\d),(\d)')

# Placeholder tokens: Python-style ``{name}``/``{0}``, printf-style
# ``%s``/``%d``/``%(name)s``. Curly-brace token body excludes braces/
# whitespace and is capped at 50 chars so a stray unmatched "{" in prose
# text can't run the match on for the rest of the string.
_PLACEHOLDER_RE = re.compile(r'\{[^{}\s]{1,50}\}|%\(\w+\)[sdfgxX]|%[sdfgxX]')

# URL matcher: greedy up to whitespace, then trailing punctuation commonly
# adjacent to a URL in prose (closing parens/quotes, sentence-ending
# punctuation incl. CJK) is stripped off in _extract_urls rather than
# excluded from the character class here, since excluding them from the
# class would also wrongly truncate URLs that legitimately contain them
# (e.g. a query string with a literal ')').
_URL_RE = re.compile(r'https?://\S+')
_URL_TRAILING_PUNCT = '.,;:!?)\'"\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f\uff09'

# Inline-tag element-name extractor: pulls "bpt" out of a raw XML fragment
# like ``<bpt i="1">&lt;b&gt;</bpt>`` (an InlineNode 'tag' node's content).
_TAG_NAME_RE = re.compile(r'<\s*([a-zA-Z][\w:-]*)')


def _normalize_numbers(text):
    """Return the set of normalized numeric values found in ``text``.

    Normalization order matters: strip currency first (so "$1,000" becomes
    "1,000"), then thousands separators ("1,000" -> "1000"), then unify
    decimal separators ("1,5" -> "1.5"), then drop trailing-zero decimals
    ("1.20" -> "1.2") so the final set comparison is on a canonical form.

    Kept as a single function rather than a chain of compiled regexes
    invoked inline so the normalization logic is in one place to read,
    audit, and extend (e.g. if we later want to fold spelled-out numbers
    in, this is the only function that changes).
    """
    s = _CURRENCY_RE.sub('', text)
    s = _THOUSANDS_RE.sub('', s)
    s = _DECIMAL_RE.sub(r'\1.\2', s)
    out = set()
    for m in _RAW_DIGIT_RE.findall(s):
        # Drop trailing-zero decimals: "1.20" -> "1.2", "1.00" -> "1".
        # Plain ints ("42") are unaffected.
        if '.' in m:
            int_part, frac = m.split('.', 1)
            frac = frac.rstrip('0')
            norm = int_part + ('.' + frac if frac else '')
        else:
            norm = m
        out.add(norm)
    return out


def _extract_placeholders(text):
    return set(_PLACEHOLDER_RE.findall(text))


def _extract_urls(text):
    urls = set()
    for m in _URL_RE.findall(text):
        urls.add(m.rstrip(_URL_TRAILING_PUNCT))
    return urls


def _tag_type_counts(markup):
    """Returns {tag_name: count} for the 'tag' nodes in an InlineNode list.
    ``markup`` of None or [] returns {} -- callers treat two empty dicts
    as "no markup on either side, nothing to check" rather than a mismatch.
    """
    if not markup:
        return {}
    counts = {}
    for node in markup:
        if node.kind != 'tag':
            continue
        m = _TAG_NAME_RE.match(node.content)
        name = m.group(1) if m else '?'
        counts[name] = counts.get(name, 0) + 1
    return counts


def expected_length_ratio(units):
    """Corpus-wide src/tgt character-length ratio, used as the expected
    ratio ``run()`` compares each individual unit against for
    LENGTH_RATIO_OUTLIER. Named distinctly from ``run()``'s own
    ``length_ratio`` parameter (this function *computes* the value that
    parameter expects to be handed) to avoid a confusing same-name
    function/parameter pair in one module.

    Moved here from ``api.py`` (was a private ``_length_ratio()`` used
    only inline in the convert pipeline) so ``tm/qa_report.py`` -- which
    runs QA against an *already-existing* corpus file, outside the convert
    pipeline -- can compute the same ratio the same way, rather than
    re-deriving or hardcoding one. A per-language-pair constant (e.g.
    "English to Chinese is usually ~0.5x the character count") was
    considered and rejected: the actual ratio varies enough by
    domain/register that a corpus-derived empirical ratio is more
    reliable than a fixed table, and it's free to compute from data we
    already have in hand.
    """
    src_len = sum(nolen(u.src_text) for u in units)
    tgt_len = sum(nolen(u.tgt_text) for u in units)
    return src_len / max(tgt_len, 1)


def run(units, length_ratio):
    """Mutates each unit's meta in place: 'qa_issues' (list[str]) and
    'qa_confidence' (float, 1.0 = no issues found). Returns units for
    chaining convenience.

    Consistency check flags SOURCE_CONFLICT/TARGET_CONFLICT -- the same
    source text mapping to more than one distinct target (or vice versa)
    across the document, a real sign of inconsistent translation. An
    *exact* duplicate pair (same source AND same target, appearing more
    than once) is NOT flagged: repeated boilerplate/UI strings translated
    the same way every time is normal, expected TM content, not a quality
    problem -- flagging it would just be noise in the QA report.
    """
    src_to_targets, tgt_to_sources = {}, {}
    for u in units:
        src, tgt = u.src_text.strip(), u.tgt_text.strip()
        if src and tgt:  # empty src/tgt is EMPTY_SOURCE/EMPTY_TARGET's job, not a conflict
            src_to_targets.setdefault(src, set()).add(tgt)
            tgt_to_sources.setdefault(tgt, set()).add(src)

    for u in units:
        issues = []
        src, tgt = u.src_text.strip(), u.tgt_text.strip()
        if not src:
            issues.append('EMPTY_SOURCE')
        if not tgt:
            issues.append('EMPTY_TARGET')
        if src and tgt:
            src_len = len(re.sub(r'\s+', '', src))
            tgt_len = len(re.sub(r'\s+', '', tgt))
            if src_len and tgt_len and length_ratio > 0:
                expected = src_len / length_ratio
                # Ratio-based, not difference-based: a difference-based
                # check (|tgt_len - expected| / expected) is asymmetric --
                # it can never exceed 1.0 on the "too short" side (tgt_len
                # can't go below 0), so a threshold above 1.0 can only ever
                # fire for "too long", never "too short". Caught by the
                # length-ratio-outlier test itself before this fix.
                ratio = tgt_len / max(expected, 1e-6)
                if ratio < 0.3 or ratio > 3.0:
                    issues.append('LENGTH_RATIO_OUTLIER')
            if _normalize_numbers(src) != _normalize_numbers(tgt):
                issues.append('NUMBER_MISMATCH')
            if _extract_placeholders(src) != _extract_placeholders(tgt):
                issues.append('PLACEHOLDER_MISMATCH')
            if _extract_urls(src) != _extract_urls(tgt):
                issues.append('URL_MISMATCH')
            if _tag_type_counts(u.src_markup) != _tag_type_counts(u.tgt_markup):
                issues.append('TAG_MISMATCH')
        if len(src_to_targets.get(src, ())) > 1:
            issues.append('SOURCE_CONFLICT')
        if len(tgt_to_sources.get(tgt, ())) > 1:
            issues.append('TARGET_CONFLICT')

        u.meta['qa_issues'] = issues
        u.meta['qa_confidence'] = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return units
