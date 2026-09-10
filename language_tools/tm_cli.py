"""``tmtool`` -- CLI for corpus-level TM maintenance (clean/merge/stats/qa/
term-check) and bilingual-source alignment checking (align).

Kept as a separate entry point from ``biconvert`` (see DESIGN.md section
12 for why ``biconvert`` itself stays a thin wrapper with no pipeline
logic of its own): this is a different concern -- operating on
already-corpus (tmx/sdltm) files (plus, for ``align``, on a bilingual
source that hasn't been converted into one yet -- see that subcommand's
own note below) rather than converting bilingual sources into corpora --
and giving it its own command avoids growing ``biconvert``'s argument
surface with flags unrelated to conversion.

Like ``biconvert``, no pipeline logic lives here: each subcommand is
argument parsing plus a call into ``language_tools.tm.<module>`` (or, for
``align``, ``language_tools.align_report``), so a future GUI tool page
can call the same functions directly. ``align`` was the one alignment-
diagnostics entry point that stayed GUI-only when ``toolbox/tools/
alignment_check`` shipped -- reasonable at the time (this is a "glance at
it" tool, most people checking one document's alignment just want to look
at the table), but it left no way to batch-check a folder of documents
short of clicking through each one by hand. Its ``--fail-on-issues`` flag
exists specifically for that: a non-zero exit code is the one thing a
shell loop can act on that "read the printed summary" can't give it.
``align``'s argument surface (``--layout``/``--sheet``/``--src-col``/
``--tgt-col``/``--delimiter``/``--header``) intentionally mirrors
``biconvert``'s bilingual-source options exactly (reusing
``language_tools.cli._build_reader_opts`` rather than a second copy of
the same flag-to-reader_opts translation) -- checking a document's
alignment needs to locate the same source/target columns and docx layout
that converting it would, so the flags for "which cells/columns are
source vs. target" shouldn't need to be relearned between the two
commands.
"""
import argparse
import os
import sys

from language_tools import align_report
from language_tools.cli import _build_reader_opts
from language_tools.terms import check as term_check_module
from language_tools.terms import glossary as glossary_module
from language_tools.tm import clean as clean_module
from language_tools.tm import io as tm_io
from language_tools.tm import merge as merge_module
from language_tools.tm import qa_report as qa_report_module
from language_tools.tm import stats as stats_module
from language_tools.writers import csv_writer

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}


def _cmd_clean(args):
    units = tm_io.read_corpus(args.input)
    src_lang, tgt_lang = tm_io.infer_langs(units)
    kept, report = clean_module.clean(
        units,
        normalize=not args.no_normalize,
        dedupe=not args.no_dedupe,
        remove_empty=not args.no_remove_empty,
        remove_identical=args.remove_identical,
    )
    output = args.output or args.input
    tm_io.write_corpus(output, kept, src_lang, tgt_lang)
    print('Input=%d Output=%d Duplicates=%d Empty=%d Identical=%d Normalized=%d' % (
        report['input'], report['output'], report['removed_duplicate'],
        report['removed_empty'], report['removed_identical'], report['normalized']))
    print('Wrote %s' % output)
    return 0


def _cmd_merge(args):
    unit_lists = [tm_io.read_corpus(p) for p in args.inputs]
    merged, report = merge_module.merge(unit_lists, strategy=args.strategy)
    src_lang, tgt_lang = tm_io.infer_langs(merged)
    tm_io.write_corpus(args.output, merged, src_lang, tgt_lang)
    print('Input=%d Output=%d ConflictsResolved=%d Strategy=%s' % (
        report['input'], report['output'], report['conflicts_resolved'], args.strategy))
    print('Wrote %s' % args.output)
    return 0


def _cmd_stats(args):
    units = tm_io.read_corpus(args.input)
    s = stats_module.compute(units)
    print('Total=%d Unique=%d Duplicates=%d (%.1f%%)' % (
        s['total'], s['unique_pairs'], s['duplicate_pairs'], s['duplicate_rate'] * 100))
    print('EmptySource=%d EmptyTarget=%d LengthRatio=%.3f' % (
        s['empty_source'], s['empty_target'], s['length_ratio']))
    for pair, count in sorted(s['lang_pairs'].items()):
        print('  %s: %d' % (pair, count))
    return 0


def _cmd_qa(args):
    units = qa_report_module.run(args.input)
    s = qa_report_module.summarize(units)
    print('Total=%d Flagged=%d (%.1f%%)' % (
        s['total'], s['flagged'], (s['flagged'] / s['total'] * 100) if s['total'] else 0.0))
    for issue_type in qa_report_module.ISSUE_TYPES:
        count = s['by_type'].get(issue_type)
        if count:
            print('  %s: %d' % (issue_type, count))
    if args.export:
        src_lang, tgt_lang = tm_io.infer_langs(units)
        csv_writer.write(args.export, units, src_lang or 'SRC', tgt_lang or 'TGT', include_qa=True)
        print('Wrote %s' % args.export)
    return 0


def _cmd_term_check(args):
    units = tm_io.read_corpus(args.input)
    src_lang, tgt_lang = tm_io.infer_langs(units)
    entries = glossary_module.read(args.glossary, src_lang, tgt_lang)
    term_check_module.run(units, entries)
    s = term_check_module.summarize(units)
    print('Total=%d Flagged=%d (%.1f%%)' % (
        s['total'], s['flagged'], (s['flagged'] / s['total'] * 100) if s['total'] else 0.0))
    if args.export:
        csv_writer.write(args.export, units, src_lang or 'SRC', tgt_lang or 'TGT', include_terms=True)
        print('Wrote %s' % args.export)
    if args.fail_on_issues and s['flagged']:
        return 2
    return 0


def _cmd_align(args):
    ext = os.path.splitext(args.input)[1].lower()
    if ext not in _BILINGUAL_EXTS:
        print('error: unsupported bilingual source format %r (expected one of %s); '
              'a .tmx/.sdltm corpus has no alignment to diagnose -- see the `qa` '
              'subcommand for that instead' % (ext, sorted(_BILINGUAL_EXTS)),
              file=sys.stderr)
        return 1

    reader_opts = _build_reader_opts(args, ext)
    units = align_report.run(
        args.input, args.src, args.tgt, repair_path=args.repair, reader_opts=reader_opts)
    s = align_report.summarize(units)
    print('Units=%d Gaps=%d Flagged=%d' % (s['total'], s['gap_count'], s['qa_flagged']))
    for move_code in sorted(s['move_counts']):
        print('  %s (%s): %d' % (
            move_code, align_report.move_label(move_code), s['move_counts'][move_code]))

    if args.export:
        csv_writer.write(args.export, units, args.src, args.tgt, include_qa=True, include_align=True)
        print('Wrote %s' % args.export)

    if args.fail_on_issues and (s['gap_count'] or s['qa_flagged']):
        return 2
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog='tmtool', description='Translation-memory maintenance: clean, merge, '
                                    'summarize, and check alignment quality for '
                                    '.tmx/.sdltm corpus files and bilingual sources.')
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

    qa_p = sub.add_parser('qa', help='run QA checks against a corpus file')
    qa_p.add_argument('input', help='input .tmx or .sdltm file')
    qa_p.add_argument('--export', metavar='PATH',
                       help='write a full CSV report (all units, with confidence/status/issues '
                            'columns) to PATH')
    qa_p.set_defaults(func=_cmd_qa)

    term_check_p = sub.add_parser(
        'term-check', help='check a corpus file against a glossary for forbidden translations')
    term_check_p.add_argument('input', help='input .tmx or .sdltm file')
    term_check_p.add_argument('--glossary', required=True,
                               help='glossary file (.csv or .xlsx) with src_term/tgt_term/status columns')
    term_check_p.add_argument('--export', metavar='PATH',
                               help='write a full CSV report (all units, with a term_issues '
                                    'column) to PATH')
    term_check_p.add_argument('--fail-on-issues', action='store_true',
                               help='exit with status 2 if any forbidden-term hit was found -- '
                                    'same convention as `align --fail-on-issues`, for scripting '
                                    'a batch check over many corpus files')
    term_check_p.set_defaults(func=_cmd_term_check)

    align_p = sub.add_parser(
        'align', help='check sentence-alignment quality for a bilingual source file '
                       '(docx/xlsx/csv/tsv), without writing a corpus')
    align_p.add_argument('input', help='bilingual source file (docx/xlsx/csv/tsv) -- NOT a '
                                        '.tmx/.sdltm corpus, those are already sentence-level '
                                        'and have nothing to align')
    align_p.add_argument('--src', required=True, help='source language code, e.g. en-US')
    align_p.add_argument('--tgt', required=True, help='target language code, e.g. zh-CN')
    align_p.add_argument('--layout', choices=['auto', 'numbered', 'table', 'alternating'],
                          default='auto', help='docx layout; ignored for non-docx input. '
                                                'Default: auto-detect.')
    align_p.add_argument('--sheet', help='xlsx sheet name (default: first sheet)')
    align_p.add_argument('--src-col', help='source column: Excel letter (xlsx) or 0-based '
                                            'index (docx table/csv)')
    align_p.add_argument('--tgt-col', help='target column: Excel letter (xlsx) or 0-based '
                                            'index (docx table/csv)')
    align_p.add_argument('--delimiter', help='csv/tsv delimiter override (default: auto-sniffed)')
    align_header = align_p.add_mutually_exclusive_group()
    align_header.add_argument('--header', dest='header', action='store_true', default=None,
                               help='treat the first row as a header (xlsx/csv/docx table)')
    align_header.add_argument('--no-header', dest='header', action='store_false',
                               help='treat the first row as data, not a header')
    align_p.add_argument('--repair', metavar='PATH', help='path to a repairs.json rule file')
    align_p.add_argument('--export', metavar='PATH',
                          help='write a full CSV report (all units incl. clean ones, with '
                               'align_move/align_gap/qa columns) to PATH')
    align_p.add_argument('--fail-on-issues', action='store_true',
                          help='exit with status 2 if any GAP or QA-flagged unit was found -- '
                               'off by default (a successful run always exits 0 otherwise, '
                               'same as every other tmtool subcommand); turn this on when '
                               'scripting a batch check over many files, so a non-zero exit '
                               'marks which ones need a look, e.g.: '
                               'for f in *.docx; do tmtool align "$f" --src en-US --tgt zh-CN '
                               '--fail-on-issues || echo "check: $f"; done')
    align_p.set_defaults(func=_cmd_align)

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
