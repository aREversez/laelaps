"""Top-level pipeline glue.

This is deliberately minimal for Phase 1 -- just enough to run the
numbered-docx -> sdltm/tmx/csv pipeline end to end for regression testing.
Format auto-detection, ``--layout`` overrides, and the full CLI are Phase 4
scope (DESIGN.md section 10); don't expand this ahead of that phase.
"""
import os

from language_tools.align.aligner import align_paragraph_pairs
from language_tools.align.repair import NULL_REPAIRER, load_repairs
from language_tools.readers import docx_numbered
from language_tools.writers import csv_writer, sdltm_writer, tmx_writer

_READERS = {
    '.docx': docx_numbered.read,
}


def convert(input_path, output_base, src_lang='en-US', tgt_lang='zh-CN',
            repair_path=None, name=None, formats=('sdltm', 'tmx', 'csv')):
    """Read ``input_path``, align, and write ``output_base.<fmt>`` for each
    format in ``formats``. Returns a dict with unit count and length ratio.
    """
    ext = os.path.splitext(input_path)[1].lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise ValueError('no reader registered for %r files' % ext)

    repairer = load_repairs(repair_path) if repair_path else NULL_REPAIRER
    pairs = reader(input_path)
    units, ratio = align_paragraph_pairs(
        pairs, src_lang, tgt_lang, repairer=repairer, source_file=input_path)

    tm_name = (name or os.path.splitext(os.path.basename(input_path))[0])[:80]
    written = {}
    if 'sdltm' in formats:
        written['sdltm'] = sdltm_writer.write(output_base + '.sdltm', units, src_lang, tgt_lang, tm_name)
    if 'tmx' in formats:
        tmx_writer.write(output_base + '.tmx', units, src_lang, tgt_lang)
        written['tmx'] = len(units)
    if 'csv' in formats:
        csv_writer.write(output_base + '.csv', units)
        written['csv'] = len(units)

    return {'units': len(units), 'length_ratio': ratio, 'written': written}
