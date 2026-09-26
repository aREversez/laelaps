"""Format-dispatch helpers for reading/writing a corpus file (.tmx/.sdltm)
by extension.

Factored out of ``tm_cli.py`` (which originally had its own private
``_CORPUS_READERS``/``_CORPUS_WRITERS`` dicts) so the desktop GUI's TM
maintenance page can reuse the exact same dispatch logic instead of
re-declaring it -- per VIBE_CODING_RULES.md's "shared validation logic:
never duplicate" pattern. Two independent copies of "which reader/writer
handles which extension" is exactly the kind of thing that quietly drifts
apart (e.g. one call site gains xliff support, the other doesn't, and
nothing fails loudly -- it just silently produces a "unsupported format"
error in one place and works in the other).
"""
import os

from language_tools.corpus_readers import sdltm_reader, tmx_reader
from language_tools.writers import sdltm_writer, tmx_writer

READERS = {'.tmx': tmx_reader.read, '.sdltm': sdltm_reader.read}
WRITERS = {'.tmx': tmx_writer.write, '.sdltm': sdltm_writer.write}
SUPPORTED_EXTS = tuple(READERS)


def read_corpus(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in READERS:
        raise ValueError('unsupported corpus format %r (expected .tmx or .sdltm)' % ext)
    return READERS[ext](path)


def make_labels(paths):
    """One short display label per path (the file's basename), with
    duplicates disambiguated as ``name.ext``/``name-2.ext``/...

    These labels are used as *dict keys* by quote/term-extract batch
    results and compare reports -- plain ``os.path.basename`` made two
    inputs named ``q1/same.tmx`` + ``q2/same.tmx`` collide, and the
    second file silently overwrote the first (``Files=1`` for two real
    inputs, one file's content unpriced and unreported with no warning,
    P0-3 of the 2026-09 fix list). Keep the returned list aligned
    one-to-one with ``paths`` (index-wise) at every call site.
    """
    labels = []
    taken = set()
    for path in paths:
        # Normalize separators first: os.path.basename on Linux does NOT
        # split on '\\', so a Windows-style path would otherwise yield
        # the whole path as one giant 'label'.
        base = os.path.basename(str(path).replace('\\', '/'))
        label = base
        n = 1
        while label in taken:  # also guards a real 'a-2.tmx' input colliding
            n += 1
            root, ext = os.path.splitext(base)
            label = '%s-%d%s' % (root, n, ext)
        taken.add(label)
        labels.append(label)
    return labels


def write_corpus(path, units, src_lang, tgt_lang, name=None):
    """``name`` (sdltm database display name) defaults to the output
    filename's stem, truncated to 80 chars -- irrelevant for .tmx.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in WRITERS:
        raise ValueError('unsupported corpus format %r (expected .tmx or .sdltm)' % ext)
    if ext == '.sdltm':
        sdltm_writer.write(path, units, src_lang, tgt_lang,
                            name or os.path.splitext(os.path.basename(path))[0][:80])
    else:
        tmx_writer.write(path, units, src_lang, tgt_lang)


def infer_langs(units):
    """Best-effort src/tgt language codes from the first unit, for callers
    (like a merge across multiple files) that don't already know them.
    Returns ('', '') for an empty unit list rather than raising -- an
    empty result is itself a valid (if useless) merge/clean output, and
    the writer functions accept empty-string language codes without
    complaint.
    """
    if not units:
        return '', ''
    return units[0].src_lang, units[0].tgt_lang
