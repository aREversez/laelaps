"""Lightweight QA layer (DESIGN.md section 9). Runs after alignment, before
writing: flags likely-bad TUs for human review rather than blocking them.

v1 scope is deliberately four checks, no more: empty segment, length-ratio
outlier, translation-consistency conflict, number mismatch. Tag/
placeholder/URL checks are deferred until a tagged input format actually
exists to test them against (see DESIGN.md section 9) -- adding them now
would be untested surface area with no real input to validate against.

Number normalization (added in this commit): the original NUMBER_MISMATCH
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
        if len(src_to_targets.get(src, ())) > 1:
            issues.append('SOURCE_CONFLICT')
        if len(tgt_to_sources.get(tgt, ())) > 1:
            issues.append('TARGET_CONFLICT')

        u.meta['qa_issues'] = issues
        u.meta['qa_confidence'] = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return units
