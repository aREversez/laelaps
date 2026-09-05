"""``biconvert`` -- thin CLI wrapper over ``language_tools.api.convert()``.

Per DESIGN.md section 12: the CLI contains no pipeline logic of its own,
only argument parsing and translating flags into a ``convert()`` call, so
a future GUI can reuse exactly the same behavior (including the
``min_confidence`` export filter, which deliberately lives in ``api.py``
rather than here for that reason).
"""
import argparse
import os
import sys

from language_tools import api

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}
_ALL_FORMATS = ('sdltm', 'tmx', 'csv')


def build_parser():
    p = argparse.ArgumentParser(
        prog='biconvert',
        description='Convert bilingual files (docx/xlsx/csv/tsv) to translation-memory '
                    'corpus formats (sdltm/tmx/csv), or convert between corpus formats '
                    '(tmx<->sdltm).')
    p.add_argument('input', help='input file path')
    p.add_argument('-o', '--output',
                    help='output path or basename. A bare basename writes every requested '
                         'format under it (e.g. "out" -> out.sdltm, out.tmx, out.csv); a '
                         'path ending in .sdltm/.tmx/.csv writes only that one format unless '
                         '--to is also given. Default: derived from the input filename.')
    p.add_argument('--to', action='append', choices=list(_ALL_FORMATS),
                    help='output format to write; repeatable (e.g. --to tmx --to csv). '
                         'Default: sdltm, tmx, and csv all together.')
    p.add_argument('--src', help='source language code, e.g. en-US. Required for docx/xlsx/'
                                  'csv/tsv input; inferred from the file for tmx/sdltm input.')
    p.add_argument('--tgt', help='target language code, e.g. zh-CN. Same rules as --src.')
    p.add_argument('--layout', choices=['auto', 'numbered', 'table', 'alternating'], default='auto',
                    help='docx layout; ignored for non-docx input. Default: auto-detect.')
    p.add_argument('--sheet', help='xlsx sheet name (default: first sheet)')
    p.add_argument('--src-col', help='source column: Excel letter (xlsx) or 0-based index (docx table/csv)')
    p.add_argument('--tgt-col', help='target column: Excel letter (xlsx) or 0-based index (docx table/csv)')
    p.add_argument('--delimiter', help='csv/tsv delimiter override (default: auto-sniffed)')
    header = p.add_mutually_exclusive_group()
    header.add_argument('--header', dest='header', action='store_true', default=None,
                        help='treat the first row as a header (xlsx/csv/docx table)')
    header.add_argument('--no-header', dest='header', action='store_false',
                        help='treat the first row as data, not a header')
    p.add_argument('--repair', metavar='PATH', help='path to a repairs.json rule file')
    p.add_argument('--name', help='translation memory name for sdltm output '
                                  '(default: derived from the input filename)')
    p.add_argument('--qa', action='store_true',
                    help='run the QA layer and add confidence/status/issues columns to the CSV')
    p.add_argument('--min-confidence', type=float, default=0.0, metavar='0..1',
                    help='exclude units below this QA confidence from sdltm/tmx output '
                         '(the CSV always lists everything, filtered or not); implies --qa')
    return p


def _build_reader_opts(args, ext):
    opts = {}
    if ext == '.docx' and args.layout != 'auto':
        opts['layout'] = args.layout
    if args.sheet:
        opts['sheet'] = args.sheet
    is_xlsx = ext in ('.xlsx', '.xlsm')
    if args.src_col is not None:
        opts['src_col' if is_xlsx else 'src_col_index'] = args.src_col if is_xlsx else int(args.src_col)
    if args.tgt_col is not None:
        opts['tgt_col' if is_xlsx else 'tgt_col_index'] = args.tgt_col if is_xlsx else int(args.tgt_col)
    if args.delimiter:
        opts['delimiter'] = args.delimiter
    if args.header is not None:
        opts['header'] = args.header
    return opts


def _resolve_output(input_path, output, to_formats):
    """Returns (output_base, formats). A single-format extension on -o
    (e.g. -o out.tmx) selects that one format unless --to already did."""
    if not output:
        return os.path.splitext(input_path)[0], to_formats or _ALL_FORMATS
    root, ext = os.path.splitext(output)
    fmt = ext.lstrip('.').lower()
    if fmt in _ALL_FORMATS and not to_formats:
        return root, (fmt,)
    return output, to_formats or _ALL_FORMATS


def main(argv=None):
    args = build_parser().parse_args(argv)
    ext = os.path.splitext(args.input)[1].lower()

    if ext in _BILINGUAL_EXTS and (not args.src or not args.tgt):
        build_parser().error('--src and --tgt are required for %s input' % ext)

    output_base, formats = _resolve_output(args.input, args.output, tuple(args.to) if args.to else None)
    reader_opts = _build_reader_opts(args, ext)

    try:
        result = api.convert(
            args.input, output_base, src_lang=args.src, tgt_lang=args.tgt,
            repair_path=args.repair, name=args.name, formats=formats,
            reader_opts=reader_opts, qa=args.qa, min_confidence=args.min_confidence,
        )
    except (ValueError, FileNotFoundError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 1

    print('Units=%d Exported=%d LengthRatio=%.3f' %
          (result['units'], result['exported'], result['length_ratio']))
    for fmt, count in result['written'].items():
        print('Wrote %s.%s (%d units)' % (output_base, fmt, count))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
