"""Write a CSV alignment review sheet. The only writer with truly
deterministic byte-for-byte output (no guid/timestamp embedded), so it's the
one place a byte-identical regression comparison is valid.

Deliberately does NOT skip empty-src/tgt rows, unlike the sdltm/tmx
writers -- this preserves the seed script's exact behavior (its sdltm/tmx
writers filter empty pairs, its CSV loop does not). That inconsistency is
arguably a feature for a human-review sheet: it lets a reviewer see gaps
the TM writers silently dropped. Not changing it in Phase 1 without an
explicit decision; flagged in the design doc for follow-up if it turns out
to be unwanted.

Column headers default to the literal strings 'EN'/'ZH' regardless of the
actual --src/--tgt language codes, matching the seed script's behavior
exactly (it hardcoded the header text). This mislabels reversed-direction
conversions (a zh-CN->en-US run still gets an "EN,ZH" header) -- a
pre-existing quirk kept as-is for Phase 1 fidelity, not fixed silently.
"""
import csv


def write(path, units, src_label='EN', tgt_label='ZH'):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['No', src_label, tgt_label])
        for i, u in enumerate(units, 1):
            w.writerow([i, u.src_text.strip(), u.tgt_text.strip()])
