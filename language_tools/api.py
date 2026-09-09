"""Top-level pipeline glue.

Format auto-detection here is by extension only (.docx/.xlsx/.csv/.tsv for
bilingual sources; .tmx/.sdltm for corpus-to-corpus conversion). DOCX layout
(numbered-list vs table) is auto-detected inside ``readers.docx``. The full
CLI (``biconvert``) is Phase 4 scope (DESIGN.md section 10) and will wrap
this function -- don't grow this into a CLI ahead of that phase.
"""
import os

from language_tools import qa as qa_module
from language_tools.align.aligner import align_paragraph_pairs
from language_tools.align.repair import NULL_REPAIRER, load_repairs
from language_tools.corpus_readers import sdltm_reader, tmx_reader
from language_tools.readers import csv_bilingual, docx, xlsx_bilingual
from language_tools.writers import csv_writer, sdltm_writer, tmx_writer

# Public (not _-prefixed) since align_report.py's independent "align
# without writing files" entry point needs the exact same "which reader
# handles which extension" dispatch -- one dict, not two hand-kept-in-sync
# copies. _CORPUS_READERS below stays private: nothing outside convert()
# needs it yet (corpus files skip alignment entirely, so align_report.py
# has no reason to touch it).
BILINGUAL_READERS = {
    '.docx': docx.read,
    '.xlsx': xlsx_bilingual.read,
    '.xlsm': xlsx_bilingual.read,
    '.csv': csv_bilingual.read,
    '.tsv': csv_bilingual.read,
}

_CORPUS_READERS = {
    '.tmx': tmx_reader.read,
    '.sdltm': sdltm_reader.read,
}


def convert(input_path, output_base, src_lang=None, tgt_lang=None,
            repair_path=None, name=None, formats=('sdltm', 'tmx', 'csv'),
            reader_opts=None, qa=False, min_confidence=0.0):
    """Read ``input_path``, align (if needed), and write ``output_base.<fmt>``
    for each format in ``formats``. Returns a dict with unit count and
    length ratio.

    ``input_path`` can be a bilingual source file (docx/xlsx/csv/tsv --
    goes through sentence splitting + DP alignment) or a corpus file
    (tmx/sdltm -- already sentence-level, read straight into TranslationUnit
    with no alignment step; see DESIGN.md section 1 for why those two input
    kinds take different paths through this function).

    ``src_lang``/``tgt_lang`` are required for bilingual sources (the reader
    has no language info of its own) and optional for corpus sources
    (inferred from the first unit read if not given, so ``tmx→sdltm``
    doesn't force the caller to already know the TM's language pair).

    ``reader_opts`` is passed through verbatim to the chosen reader (e.g.
    ``{'layout': 'table'}`` for docx, ``{'src_col': 'B', 'tgt_col': 'C'}``
    for xlsx). ``qa=True`` runs the QA layer and adds confidence/status/
    issues columns to the CSV output; defaults to False so existing callers
    (including the Phase 1 regression baseline) get the unchanged 3-column
    CSV unless they opt in.

    ``min_confidence`` (implies ``qa=True``) excludes units whose QA
    confidence falls below the threshold from the sdltm/tmx output -- the
    CSV always gets the full, unfiltered list regardless, so it still works
    as a QA report showing what got left out and why. This logic lives here
    rather than in the CLI so a future GUI gets the same behavior for free
    (DESIGN.md section 12: CLI and GUI both call this one Pipeline API).
    """
    ext = os.path.splitext(input_path)[1].lower()

    if ext in _CORPUS_READERS:
        corpus_reader_opts = dict(reader_opts or {})
        if src_lang and tgt_lang:
            # Lets tmx_reader match tuv-by-language instead of blindly
            # taking the first two (matters for >2-language TMX, or where
            # tuv order doesn't match the wanted direction) -- only kicks
            # in when the caller actually knows the pair; sdltm_reader
            # ignores these via its **opts catch-all.
            corpus_reader_opts.setdefault('src_lang', src_lang)
            corpus_reader_opts.setdefault('tgt_lang', tgt_lang)
        units = _CORPUS_READERS[ext](input_path, **corpus_reader_opts)
        if src_lang is None:
            src_lang = units[0].src_lang if units else ''
        if tgt_lang is None:
            tgt_lang = units[0].tgt_lang if units else ''
        ratio = qa_module.expected_length_ratio(units) if units else 1.0
    elif ext in BILINGUAL_READERS:
        if not src_lang or not tgt_lang:
            raise ValueError('src_lang and tgt_lang are required for bilingual '
                              'source files (%r has no language info of its own)' % ext)
        repairer = load_repairs(repair_path) if repair_path else NULL_REPAIRER
        pairs = BILINGUAL_READERS[ext](input_path, **(reader_opts or {}))
        units, ratio = align_paragraph_pairs(
            pairs, src_lang, tgt_lang, repairer=repairer, source_file=input_path)
    else:
        raise ValueError('no reader registered for %r files' % ext)

    run_qa = qa or min_confidence > 0
    if run_qa:
        qa_module.run(units, ratio)

    corpus_units = units
    if min_confidence > 0:
        corpus_units = [u for u in units if u.meta.get('qa_confidence', 1.0) >= min_confidence]

    tm_name = (name or os.path.splitext(os.path.basename(input_path))[0])[:80]
    written = {}
    if 'sdltm' in formats:
        written['sdltm'] = sdltm_writer.write(output_base + '.sdltm', corpus_units, src_lang, tgt_lang, tm_name)
    if 'tmx' in formats:
        tmx_writer.write(output_base + '.tmx', corpus_units, src_lang, tgt_lang)
        written['tmx'] = len(corpus_units)
    if 'csv' in formats:
        csv_writer.write(output_base + '.csv', units, include_qa=run_qa)
        written['csv'] = len(units)

    return {'units': len(units), 'exported': len(corpus_units), 'length_ratio': ratio, 'written': written}
