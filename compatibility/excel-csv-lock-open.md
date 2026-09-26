# Excel / Locked-File Open Compatibility — Investigation Brief

## Status: open investigation, handed off for real-Windows diagnosis

This environment (where `language_tools/terms/filelock.py`'s design and the
last two rounds of fixes were done) has no Windows or Microsoft Office
install to test against — same class of limitation as
`compatibility/studio-readable.md`'s Trados Studio gap. Everything below is
reasoned from Windows API documentation plus the real-device test results
already reported; it needs to be confirmed (or refuted) on an actual Windows
machine with Excel before implementing anything further.

## Background — how we got here

1. **v1 (sidecar marker file):** proven ineffective against WPS by real-device
   testing — WPS doesn't respect or create the sidecar, so the toolbox
   couldn't detect a WPS session had the file open. Replaced with OS-level
   mandatory locking.
2. **v2 (exclusive `LockFileEx` on the real file):** fixed the WPS detection
   gap, but the exclusive lock also blocked *reads* by other processes —
   Excel showed `'test.csv' cannot be accessed. The file may be corrupted,
   located on a server that is not responding, or read-only.` even for a
   plain open.
3. **v3 (shared `LockFileEx` on the real file):** switched the lock type from
   exclusive to shared, since Windows mandatory locking permits other
   readers against a shared lock. Still didn't fix the Excel symptom above.
4. **v4 (current `dev` HEAD, real-file handle opened `'rb'` instead of
   `'r+b'`):** the real fix for v3's leftover problem turned out to be
   unrelated to the lock type — the real-file handle backing the lock was
   opened with `GENERIC_WRITE` access it never actually used (writes always
   go through a separate handle in `write_around()`/`glossary.write()`), and
   Windows' `CreateFile` sharing check is a *separate* mechanism from
   `LockFileEx` byte-range locking: it rejects a new opener whose requested
   share mode can't accommodate the access rights *already granted* to any
   existing open handle, independent of what that handle has locked.
   Dropping our handle's access to read-only removed that conflict source.

## Current confirmed behavior (real-Windows testing, 2026-09-12, after v4)

With the toolbox holding a glossary file open (shared `LockFileEx` lock on
the real file + a separate exclusive lock on a `.lock` sidecar, real-file
handle opened `'rb'`):

| Format  | Excel: Open                                                                                          | Excel: Save (toolbox still holding the file open)                                                                                                                             |
|---------|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `.csv`  | **Fails** — `'test.csv' cannot be accessed. The file may be corrupted, located on a server that is not responding, or read-only.` | not reached                                                                                                                                                                  |
| `.xlsx` | **Succeeds** (opens fine)                                                                              | **Fails, as intended** — `Your changes could not be saved to 'sample_terms.xlsx' because of a sharing violation. Try saving to a different file.`, followed by Excel's own leftover-temp-file dialog: `The file format and extension of '5F0EB100' don't match...` |

**The xlsx save failure is expected, correct behavior — not a bug.** The
lock's entire purpose is to stop something else from silently overwriting the
file while the toolbox has it open; that's exactly what just happened. The
follow-up "5F0EB100" dialog is Excel's own write-via-temp-file-then-rename
mechanism failing partway through (it wrote its pending changes to a random-
named temp file in the same folder, then couldn't rename that temp file over
the original because we still hold it open, and is now offering to open the
orphaned temp file instead). The original file is untouched. Nothing to fix
here beyond possibly a line of in-app documentation so end users aren't
alarmed by it.

**The open question is only:** why does Excel fail to even *open* (read-only)
a locked `.csv`, when the identical locking code lets it open a locked
`.xlsx` fine?

## Working hypothesis — needs Process Monitor confirmation, not yet verified

`.xlsx` is a zip/OPC package; Excel most likely reads the whole archive and
releases its handle quickly, which tolerates our read-only + shared-lock
handle without friction. `.csv` historically goes through Excel's older
plain-text import codepath (lineage: the Jet/ACE "Text" installable ISAM
driver), which — unlike the zip reader — may request a much more restrictive
share mode (`share=0`, fully exclusive) even just to *open* a file for
reading. If that's what's happening, it would fail **regardless of what
access mode or lock type our own handle uses**: Windows' sharing-violation
check requires every already-open handle's granted access to be compatible
with a *new* opener's requested share mode, and a request for `share=0`
(deny-all) is incompatible with any other handle already being open, no
matter how read-only that other handle is.

If confirmed, this is **an Excel-side limitation specific to `.csv`, not
something fixable by further tuning `FileLock`'s access mode or lock type** —
see "Decision: architecture options" below for what's actually left to do
about it.

## Task

### Step 1 — confirm or refute the hypothesis empirically

Using Process Monitor (Sysinternals) on a real Windows machine with Excel:

1. Start the toolbox, open a `.csv` glossary through the term management
   page so `FileLock.acquire()` is holding the lock.
2. In Process Monitor, filter on `Process Name is EXCEL.EXE` and
   `Path contains <that filename>.csv`.
3. File → Open that csv in Excel. Capture the resulting `CreateFile`
   operation(s): record `Desired Access`, `Share Mode`, `Disposition`, and
   `Result` (expect `SHARING VIOLATION` if this is the cause).
4. Repeat 1-3 with a `.xlsx` file under an identical lock, for comparison.
   Note whether Excel's `CreateFile` for `.xlsx` requests a different (more
   permissive) `Share Mode` / `Desired Access` than it does for `.csv`.
5. Also capture what **our own** `FileLock` real-file handle requested
   (expect `Desired Access: Read` given the `'rb'` open in v4 — record the
   actual `Share Mode` Python's `open()` sets on this machine rather than
   assuming, since that's the other half of the sharing-violation equation).
6. Append the raw findings to this file under a new "## Process Monitor
   findings" section (numbers, not just conclusions — a screenshot is fine
   too) before moving to Step 2.

### Step 2 — act on the findings

- **If Excel's `.csv` open genuinely requests `share=0`/exclusive access**
  (hypothesis confirmed): this isn't fixable by further tuning `FileLock`'s
  own access mode — go to "Decision: architecture options" below. Don't
  implement any of those options unilaterally; the trade-off needs Eliot's
  call first (see that section).
- **If Excel's `.csv` open requests the same access/share as its `.xlsx`
  open, but still fails:** something else is going on — possibly a second,
  conflicting handle opened somewhere else in this codebase during the
  glossary-open flow (grep `toolbox/tools/term_management/` and
  `language_tools/terms/` for any other `open(path, ...)` call on the
  glossary path that could run concurrently with the held lock), a stale
  handle from a previous session that `FileLock.release()`/`cleanup()`
  didn't actually run for, or something external (AV, sync client). Report
  back with what's actually different between the two formats before
  proposing a fix — don't guess at a patch without knowing which of these it
  is.

## Decision: architecture options (only relevant if Step 1 confirms the hypothesis)

These are genuine trade-offs, not a single obviously-correct fix — present
them to Eliot rather than picking one:

1. **Accept the limitation.** Leave locking as-is. Add a line to the term
   management page's file-in-use messaging noting `.csv` files specifically
   can't be viewed in Excel while open in the toolbox (`.xlsx` doesn't have
   this restriction). Lowest effort; gives up nothing on the protection side.
2. **Downgrade `.csv` locking to point-in-time checks.** Acquire/check the
   lock only immediately around a write (`write_around()` already does
   something close to this) and briefly at open (to warn about a
   *pre-existing* external lock), releasing in between rather than holding
   it for the whole editing session. Keeps Excel able to view `.csv`
   throughout, but reopens close to the exact race window the original
   sidecar-lock effort existed to close — another app could start writing in
   the gap between our check and our own write. Would need its own
   regression tests for that narrowed window, and the module docstring
   updated to document the accepted risk explicitly.
3. **Format-specific strategy.** Keep the current always-held lock for
   `.xlsx`/`.xlsm` (it works well there — Excel degrades gracefully on
   conflict) and switch only `.csv` to option 2's point-in-time approach.
   Two locking strategies to maintain in one module instead of one, but
   preserves the strongest protection exactly where it doesn't cost Excel
   compatibility, and improves the one format where it currently does.

Whichever gets picked: fetch `origin/dev` HEAD before starting, one semantic
change per commit, run the suite 3x locally, and — since this touches a
Windows-only code path that's already burned two rounds on unverified
assumptions — get real-device confirmation before considering it done, not
just a clean local test run.

## Explicitly out of scope for this task

- The `.xlsx` save-conflict dialog chain (sharing violation → "5F0EB100"
  mismatch warning) is Excel's own behavior working as intended; not a bug
  to fix.
- The shared-vs-exclusive lock type and the real-file handle's read-only
  open mode (v3 and v4 above) are both confirmed correct by the `.xlsx`
  result and by the regression tests already in `tests/test_terms_filelock.py`
  — don't re-litigate those without new evidence they're wrong.
