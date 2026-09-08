"""``tmtool`` -- CLI for corpus-level TM maintenance (clean/merge/stats).

Kept as a separate entry point from ``biconvert`` (see DESIGN.md section
12 for why ``biconvert`` itself stays a thin wrapper with no pipeline
logic of its own): this is a different concern -- operating on
already-corpus (tmx/sdltm) files rather than converting bilingual sources
into corpora -- and giving it its own command avoids growing
``biconvert``'s argument surface with flags unrelated to conversion.

Like ``biconvert``, no pipeline logic lives here: each subcommand is
argument parsing plus a call into ``language_tools.tm.<module>``, so a
future GUI tool page can call the same functions directly.
"""
import argparse
import os
import sys

from language_tools.corpus_readers import sdltm_reader, tmx_reader
from language_tools.tm import clean as clean_module
from language_tools.tm import merge as merge_module
from language_tools.tm import stats as stats_module
from language_tools.writers import sdltm_writer, tmx_writer

_CORPUS_READERS = {'.tmx': tmx_reader.read, '.sdltm': sdltm_reader.read}
_CORPUS_WRITERS = {'.tmx': tmx_writer.write, '.sdltm': sdltm_writer.write}


def _read_corpus(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in _CORPUS_READERS:
        raise ValueError('unsupported corpus format %r (expected .tmx or .sdltm)' % ext)
    return _CORPUS_READERS[ext](path)


def _write_corpus(path, units, src_lang, tgt_lang, name):
    ext = os.path.splitext(path)[1].lower()
    if ext not in _CORPUS_WRITERS:
        raise ValueError('unsupported corpus format %r (expected .tmx or .sdltm)' % ext)
    if ext == '.sdltm':
        sdltm_writer.write(path, units, src_lang, tgt_lang, name)
    else:
        tmx_writer.write(path, units, src_lang, tgt_lang)


def _infer_langs(units):
    if not units:
        return '', ''
    return units[0].src_lang, units[0].tgt_lang


def _cmd_clean(args):
    units = _read_corpus(args.input)
    src_lang, tgt_lang = _infer_langs(units)
    kept, report = clean_module.clean(
        units,
        normalize=not args.no_normalize,
        dedupe=not args.no_dedupe,
        remove_empty=not args.no_remove_empty,
        remove_identical=args.remove_identical,
    )
    output = args.output or args.input
    name = os.path.splitext(os.path.basename(output))[0][:80]
    _write_corpus(output, kept, src_lang, tgt_lang, name)
    print('Input=%d Output=%d Duplicates=%d Empty=%d Identical=%d Normalized=%d' % (
        report['input'], report['output'], report['removed_duplicate'],
        report['removed_empty'], report['removed_identical'], report['normalized']))
    print('Wrote %s' % output)
    return 0


def _cmd_merge(args):
    unit_lists = [_read_corpus(p) for p in args.inputs]
    merged, report = merge_module.merge(unit_lists, strategy=args.strategy)
    src_lang, tgt_lang = _infer_langs(merged)
    name = os.path.splitext(os.path.basename(args.output))[0][:80]
    _write_corpus(args.output, merged, src_lang, tgt_lang, name)
    print('Input=%d Output=%d ConflictsResolved=%d Strategy=%s' % (
        report['input'], report['output'], report['conflicts_resolved'], args.strategy))
    print('Wrote %s' % args.output)
    return 0


def _cmd_stats(args):
    units = _read_corpus(args.input)
    s = stats_module.compute(units)
    print('Total=%d Unique=%d Duplicates=%d (%.1f%%)' % (
        s['total'], s['unique_pairs'], s['duplicate_pairs'], s['duplicate_rate'] * 100))
    print('EmptySource=%d EmptyTarget=%d LengthRatio=%.3f' % (
        s['empty_source'], s['empty_target'], s['length_ratio']))
    for pair, count in sorted(s['lang_pairs'].items()):
        print('  %s: %d' % (pair, count))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog='tmtool', description='Translation-memory maintenance: clean, merge, and '
                                    'summarize .tmx/.sdltm corpus files.')
    sub = p.add_subparsers(dest='command', required=True)

    clean_p = sub.add_parser('clean', help='normalize and remove duplicate/empty segments')
    clean_p.add_argument('input', help='input .tmx or .sdltm file')
    clean_p.add_argument('-o', '--output', help='output path (default: overwrite input)')
    clean_p.add_argument('--no-normalize', action='store_true',
                          help='skip unicode/whitespace normalization')
    clean_p.add_argument('--no-dedupe', action='store_true', help='keep exact-duplicate pairs')
    clean_p.add_argument('--no-remove-empty', action='store_true',
                          help='keep segments with an empty source or target')
    clean_p.add_argument('--remove-identical', action='store_true',
                          help='also remove segments where source == target')
    clean_p.set_defaults(func=_cmd_clean)

    merge_p = sub.add_parser('merge', help='merge multiple corpus files into one')
    merge_p.add_argument('inputs', nargs='+', help='one or more .tmx/.sdltm files to merge')
    merge_p.add_argument('-o', '--output', required=True, help='output .tmx or .sdltm path')
    merge_p.add_argument('--strategy', choices=['keep-all', 'prefer-first', 'prefer-last', 'prefer-newer'],
                          default='keep-all', help='conflict resolution strategy (default: keep-all)')
    merge_p.set_defaults(func=_cmd_merge)

    stats_p = sub.add_parser('stats', help='print corpus statistics')
    stats_p.add_argument('input', help='input .tmx or .sdltm file')
    stats_p.set_defaults(func=_cmd_stats)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
