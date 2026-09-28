"""Monolingual source files -> candidate ``TranslationUnit`` lists.

Leverage analysis asks "how much of *this new document* can be reused from a
TM", so its natural input is an ordinary single-language file, not a
translated corpus. This module is the one place that turns such a file into
the same ``TranslationUnit`` list the rest of ``language_tools.tm`` already
consumes (empty ``tgt_text``, source side only), and the one place that
decides, by extension, whether a leverage input is a corpus or a monolingual
source -- the CLI (``tmtool leverage``) and the GUI both call
``read_candidates`` so the two cannot drift on what an input may be.

Segmentation reuses ``align.splitters`` (same language dispatch, same
``repairs.json`` rules) so a document is cut the way the corpus in the TM was
cut when it went through ``align``; matching a sentence-level TM against
paragraph-level candidates would be meaningless. ``granularity='paragraph'``
is there for a TM that was built paragraph-by-paragraph.
"""
import os
from collections import Counter

from language_tools.align.repair import NULL_REPAIRER, load_repairs
from language_tools.align.splitters import pick_splitter
from language_tools.model import TranslationUnit
from language_tools.readers_mono import docx as docx_mono
from language_tools.tm import io as tm_io

MONOLINGUAL_READERS = {'.docx': docx_mono.read}
SUPPORTED_EXTS = tuple(MONOLINGUAL_READERS)
GRANULARITIES = ('sentence', 'paragraph')

# Bilingual-source extensions that have no monolingual reader yet: named in
# the error so "unsupported" is distinguishable from "supported, but only as
# a bilingual file here".
_BILINGUAL_ONLY_EXTS = ('.xlsx', '.xlsm', '.csv', '.tsv')


def read_source(path, src_lang, tgt_lang, *, granularity='sentence', repair_path=None):
    """Reads one monolingual source file into candidate units.

    Every unit has ``src_text`` set and ``tgt_text == ''``;
    ``source_file`` is ``path`` and ``source_key`` the 1-based number of the
    non-empty paragraph it came from (several sentences of one paragraph
    share a key). Raises ``ValueError`` for an unsupported extension or an
    unknown granularity, never a silent empty result for either.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in MONOLINGUAL_READERS:
        raise ValueError(_unsupported_message(path, ext))
    if granularity not in GRANULARITIES:
        raise ValueError('unknown granularity %r (expected one of %s)' % (granularity, list(GRANULARITIES)))
    if not src_lang or not tgt_lang:
        raise ValueError('src_lang and tgt_lang are required for a monolingual source file '
                          '(%r carries no language info of its own)' % path)

    paragraphs = MONOLINGUAL_READERS[ext](path)

    if granularity == 'paragraph':
        segmented = [(str(i), [text]) for i, text in enumerate(paragraphs, 1)]
    else:
        split, _join, lang_tag = pick_splitter(src_lang, paragraphs[0] if paragraphs else '', 'src')
        repairer = load_repairs(repair_path) if repair_path else NULL_REPAIRER
        repair_fn = repairer.for_lang(lang_tag)
        segmented = [(str(i), split(text, repair_fn)) for i, text in enumerate(paragraphs, 1)]

    return [
        TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=sentence, tgt_text='',
                        source_file=path, source_key=key)
        for key, sentences in segmented for sentence in sentences
    ]


def read_candidates(path, src_lang=None, tgt_lang=None, *, granularity='sentence', repair_path=None):
    """Leverage-analysis input dispatch: a .tmx/.sdltm corpus is read as it
    always was (its units carry their own language pair; ``src_lang`` /
    ``tgt_lang`` are ignored); a monolingual source goes through
    ``read_source``. Anything else raises ``ValueError``.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in tm_io.SUPPORTED_EXTS:
        return tm_io.read_corpus(path)
    if ext in MONOLINGUAL_READERS:
        return read_source(path, src_lang, tgt_lang, granularity=granularity, repair_path=repair_path)
    raise ValueError(_unsupported_message(path, ext))


def _unsupported_message(path, ext):
    if ext in _BILINGUAL_ONLY_EXTS:
        return ('%r: %s is only readable as a bilingual source here; monolingual %s input is '
                'not supported yet (supported monolingual formats: %s)'
                % (path, ext, ext, ', '.join(SUPPORTED_EXTS)))
    return ('unsupported input format %r for %r (expected a corpus %s or a monolingual source %s)'
            % (ext, path, ', '.join(tm_io.SUPPORTED_EXTS), ', '.join(SUPPORTED_EXTS)))


def resolve_language_pair(tm_units, src_lang, tgt_lang=None):
    """Pins the (src, tgt) pair a monolingual candidate is analyzed under
    against what the TM actually holds, and returns ``(src_lang, tgt_lang)``.

    ``leverage.analyze`` only matches TM entries with the *exact same* pair
    string, so ``--src en --tgt zh`` against a TM stored as ``en-US``/``zh-CN``
    would come back as 100% No Match -- a plausible-looking but wrong report.
    Here that case is an error that lists the pairs the TM really contains.

    ``tgt_lang`` may be omitted when the TM holds exactly one target for
    ``src_lang``; with several, it must be given.
    """
    pairs = Counter((u.src_lang, u.tgt_lang) for u in tm_units)
    if not src_lang:
        raise ValueError('a source language is required for a monolingual input')
    available = ', '.join('%s->%s (%d entries)' % (s, t, n) for (s, t), n in sorted(pairs.items())) or 'none (empty TM)'
    if tgt_lang:
        if (src_lang, tgt_lang) not in pairs:
            raise ValueError('the TM has no entries for language pair %s->%s; it contains: %s'
                              % (src_lang, tgt_lang, available))
        return src_lang, tgt_lang
    targets = sorted(t for (s, t) in pairs if s == src_lang)
    if not targets:
        raise ValueError('the TM has no entries with source language %s; it contains: %s'
                          % (src_lang, available))
    if len(targets) > 1:
        raise ValueError('the TM has several target languages for source %s (%s); '
                          'pass the target language explicitly' % (src_lang, ', '.join(targets)))
    return src_lang, targets[0]
