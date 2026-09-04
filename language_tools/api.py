"""Top-level pipeline glue.

Format auto-detection here is by extension only (.docx/.xlsx/.csv/.tsv);
DOCX layout (numbered-list vs table) is auto-detected inside
``readers.docx``. The full CLI (``biconvert``) is Phase 4 scope
(DESIGN.md section 10) and will wrap this function -- don't grow this into
a CLI ahead of that phase.
"""
import os

from language_tools import qa as qa_module
from language_tools.align.aligner import align_paragraph_pairs
from language_tools.align.repair import NULL_REPAIRER, load_repairs
from language_tools.readers import csv_bilingual, docx, xlsx_bilingual
from language_tools.writers import csv_writer, sdltm_writer, tmx_writer

_READERS = {
    '.docx': docx.read,
    '.xlsx': xlsx_bilingual.read,
    '.xlsm': xlsx_bilingual.read,
    '.csv': csv_bilingual.read,
    '.tsv': csv_bilingual.read,
}


def convert(input_path, output_base, src_lang='en-US', tgt_lang='zh-CN',
            repair_path=None, name=None, formats=('sdltm', 'tmx', 'csv'),
            reader_opts=None, qa=False):
    """Read ``input_path``, align, and write ``output_base.<fmt>`` for each
    format in ``formats``. Returns a dict with unit count and length ratio.

    ``reader_opts`` is passed through verbatim to the chosen reader (e.g.
    ``{'layout': 'table'}`` for docx, ``{'src_col': 'B', 'tgt_col': 'C'}``
    for xlsx). ``qa=True`` runs the QA layer and adds confidence/status/
    issues columns to the CSV output; defaults to False so existing callers
    (including the Phase 1 regression baseline) get the unchanged 3-column
    CSV unless they opt in.
    """
    ext = os.path.splitext(input_path)[1].lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise ValueError('no reader registered for %r files' % ext)

    repairer = load_repairs(repair_path) if repair_path else NULL_REPAIRER
    pairs = reader(input_path, **(reader_opts or {}))
    units, ratio = align_paragraph_pairs(
        pairs, src_lang, tgt_lang, repairer=repairer, source_file=input_path)

    if qa:
        qa_module.run(units, ratio)

    tm_name = (name or os.path.splitext(os.path.basename(input_path))[0])[:80]
    written = {}
    if 'sdltm' in formats:
        written['sdltm'] = sdltm_writer.write(output_base + '.sdltm', units, src_lang, tgt_lang, tm_name)
    if 'tmx' in formats:
        tmx_writer.write(output_base + '.tmx', units, src_lang, tgt_lang)
        written['tmx'] = len(units)
    if 'csv' in formats:
        csv_writer.write(output_base + '.csv', units, include_qa=qa)
        written['csv'] = len(units)

    return {'units': len(units), 'length_ratio': ratio, 'written': written}
