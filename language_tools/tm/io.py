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
