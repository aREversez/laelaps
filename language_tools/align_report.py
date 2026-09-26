"""Align a bilingual source file (docx/xlsx/csv/tsv) and return diagnostics,
without writing any output -- the alignment counterpart to
``tm/qa_report.py``'s "wire up an existing library function for standalone
use outside the pipeline" role.

``align_paragraph_pairs()`` itself was already usable standalone (it's just
a function over a unit list); what was missing was a "read the file, run
it, hand back something a GUI/CLI can summarize" entry point that doesn't
require going through ``api.convert()``, which always writes files. This
module is that entry point, plus QA -- see ``run()`` -- so a caller gets a
complete before-you-convert picture (alignment decisions AND standard
quality flags) in one pass, not two separate tools run back to back.
"""
import os

from language_tools import qa as qa_module
from language_tools.align.aligner import MOVE_LABELS, align_paragraph_pairs, move_label  # noqa: F401 -- re-exported for callers that used to import these from here
from language_tools.align.repair import NULL_REPAIRER, load_repairs
from language_tools.api import BILINGUAL_READERS


def run(input_path, src_lang, tgt_lang, repair_path=None, reader_opts=None):
    """Reads ``input_path`` (a bilingual source -- NOT a .tmx/.sdltm corpus;
    those are already sentence-level and have nothing to align, see
    ``tm/qa_report.py`` for diagnostics on those instead), aligns it, runs
    QA against the result, and returns the unit list. Each unit ends up
    with ``meta['align_move']``/``meta['align_gap']`` (from the aligner)
    and ``meta['qa_issues']``/``meta['qa_confidence']`` (from QA) all
    populated, same mutate-in-place contract ``qa.run()`` already has.

    Raises ``ValueError`` for a corpus-format or otherwise unrecognized
    extension -- same shape as ``tm/io.py``'s error, so a caller handling
    one already handles the other.
    """
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in BILINGUAL_READERS:
        raise ValueError(
            'unsupported bilingual source format %r (expected one of %s); '
            'a .tmx/.sdltm corpus has no alignment to diagnose -- see '
            'language_tools.tm.qa_report for that instead' %
            (ext, sorted(BILINGUAL_READERS)))

    repairer = load_repairs(repair_path) if repair_path else NULL_REPAIRER
    pairs = BILINGUAL_READERS[ext](input_path, **(reader_opts or {}))
    units, ratio = align_paragraph_pairs(
        pairs, src_lang, tgt_lang, repairer=repairer, source_file=input_path)
    qa_module.run(units, ratio)
    return units


def summarize(units):
    """Returns ``{'total': N, 'gap_count': N, 'move_counts': {code: N},
    'qa_flagged': N}``. ``move_counts`` only contains moves that actually
    occurred (same "no zero-count entries" convention as
    ``tm/qa_report.summarize()``'s ``by_type``).
    """
    total = len(units)
    gap_count = 0
    qa_flagged = 0
    move_counts = {}
    for u in units:
        move = u.meta.get('align_move', '1:1')
        move_counts[move] = move_counts.get(move, 0) + 1
        if u.meta.get('align_gap'):
            gap_count += 1
        if u.meta.get('qa_issues'):
            qa_flagged += 1
    return {'total': total, 'gap_count': gap_count, 'move_counts': move_counts,
            'qa_flagged': qa_flagged}
