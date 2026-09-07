"""Lightweight QA layer (DESIGN.md section 9). Runs after alignment, before
writing: flags likely-bad TUs for human review rather than blocking them.

v1 scope is deliberately four checks, no more: empty segment, length-ratio
outlier, translation-consistency conflict, number mismatch. Tag/
placeholder/URL checks are deferred until a tagged input format actually
exists to test them against (see DESIGN.md section 9) -- adding them now
would be untested surface area with no real input to validate against.
"""
import re

_DIGIT_RE = re.compile(r'\d+(?:[.,]\d+)?')


def _numbers(text):
    return set(_DIGIT_RE.findall(text))


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
            if _numbers(src) != _numbers(tgt):
                issues.append('NUMBER_MISMATCH')
        if len(src_to_targets.get(src, ())) > 1:
            issues.append('SOURCE_CONFLICT')
        if len(tgt_to_sources.get(tgt, ())) > 1:
            issues.append('TARGET_CONFLICT')

        u.meta['qa_issues'] = issues
        u.meta['qa_confidence'] = 1.0 if not issues else max(0.0, 1.0 - 0.25 * len(issues))
    return units
