"""Lightweight QA layer (DESIGN.md section 9). Runs after alignment, before
writing: flags likely-bad TUs for human review rather than blocking them.

v1 scope is deliberately four checks, no more: empty segment, length-ratio
outlier, duplicate TU, number mismatch. Tag/placeholder/URL checks are
deferred until a tagged input format actually exists to test them against
(see DESIGN.md section 9) -- adding them now would be untested surface
area with no real input to validate against.
"""
import re

_DIGIT_RE = re.compile(r'\d+(?:[.,]\d+)?')


def _numbers(text):
    return set(_DIGIT_RE.findall(text))


def run(units, length_ratio):
    """Mutates each unit's meta in place: 'qa_issues' (list[str]) and
    'qa_confidence' (float, 1.0 = no issues found). Returns units for
    chaining convenience.
    """
    seen = {}
    for u in units:
        seen.setdefault((u.src_text, u.tgt_text), []).append(u)

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
            if _numbers(src) != _numbers(tgt):
                issues.append('NUMBER_MISMATCH')
        if len(seen[(u.src_text, u.tgt_text)]) > 1:
            issues.append('DUPLICATE_TU')

        u.meta['qa_issues'] = issues
        u.meta['qa_confidence'] = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return units
