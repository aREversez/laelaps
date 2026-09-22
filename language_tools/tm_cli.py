"""``tmtool`` -- CLI for corpus-level TM maintenance (clean/merge/compare/
stats/qa/leverage/term-check) and bilingual-source alignment checking
(align).

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
from language_tools.reports import adapters as report_adapters
from language_tools.reports import render as report_render
from language_tools.terms import check as term_check_module
from language_tools.terms import extract as extract_module
from language_tools.terms import glossary as glossary_module
from language_tools.tm import clean as clean_module
from language_tools.tm import compare as compare_module
from language_tools.tm import io as tm_io
from language_tools.tm import leverage as leverage_module
from language_tools.tm import merge as merge_module
from language_tools.tm import near_dup as near_dup_module
from language_tools.tm import qa_report as qa_report_module
from language_tools.tm import quote as quote_module
from language_tools.tm import stats as stats_module
from language_tools.writers import csv_writer

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}


def _write_report(path, report):
    """Shared ``--report PATH`` handler for qa/leverage/compare/align/term-check: validates
    the extension up front (so the error names the flag, not a stack trace
    from inside ``report_render.write``) and prints the same "Wrote ..."
    line the existing ``--export`` handling already uses.
    """
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    if ext not in ('html', 'htm', 'pdf'):
        print('--report: unsupported extension %r (expected .html or .pdf)' % ext, file=sys.stderr)
        return 1
    try:
        report_render.write(path, report)
    except ImportError as e:
        # .pdf needs the optional reportlab extra; write_pdf() re-raises
        # it as an actionable install hint. main() only catches
        # ValueError/FileNotFoundError, so surface it here the same way
        # the extension check above does rather than as a stack trace.
        print('--report: %s' % e, file=sys.stderr)
        return 1
    print('Wrote %s' % path)
    return 0


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


def _cmd_near_dup(args):
    units = tm_io.read_corpus(args.input)
    clusters = near_dup_module.find_clusters(
        units, threshold=args.threshold, side=args.side, min_cluster_size=args.min_cluster_size)
    s = near_dup_module.summarize(clusters)
    print('Clusters=%d UnitsInClusters=%d (of %d total)' % (
        s['cluster_count'], s['total_units'], len(units)))
    if args.export:
        near_dup_module.write_clusters_csv(args.export, clusters)
        print('Wrote %s' % args.export)
    if args.report:
        rc = _write_report(args.report, report_adapters.from_near_dup_summary(s))
        if rc:
            return rc
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


def _cmd_compare(args):
    named = [(os.path.basename(p), tm_io.read_corpus(p)) for p in args.inputs]
    report = compare_module.compare(named)
    print('Inputs=%d' % len(named))
    for label in report['labels']:
        print('  %s: %d segments, %d unique to this TM' % (
            label, report['totals'][label], report['unique_segments'][label]))
    print('Shared=%d Conflicts=%d' % (report['shared_segments'], len(report['conflicts'])))
    if args.export:
        compare_module.write_conflicts_csv(args.export, report)
        print('Wrote %s' % args.export)
    if args.report:
        rc = _write_report(args.report, report_adapters.from_compare_report(report))
        if rc:
            return rc
    if args.fail_on_conflicts and report['conflicts']:
        return 2
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
    if args.report:
        rc = _write_report(args.report, report_adapters.from_qa_summary(s))
        if rc:
            return rc
    return 0


def _cmd_leverage(args):
    tm_units = tm_io.read_corpus(args.tm)
    candidate_units = tm_io.read_corpus(args.input)
    leverage_module.analyze(tm_units, candidate_units, fuzzy_floor=args.fuzzy_floor)
    s = leverage_module.summarize(candidate_units)
    print('Total=%d Words=%d' % (s['total'], s['total_words']))
    for band in leverage_module.BANDS:
        b = s['bands'][band]
        if b['count']:
            print('  %s: %d segments, %d words' % (band, b['count'], b['words']))
    if args.export:
        src_lang, tgt_lang = tm_io.infer_langs(candidate_units)
        csv_writer.write(args.export, candidate_units, src_lang or 'SRC', tgt_lang or 'TGT',
                          include_leverage=True)
        print('Wrote %s' % args.export)
    if args.report:
        rc = _write_report(args.report, report_adapters.from_leverage_summary(s))
        if rc:
            return rc
    return 0


def _cmd_term_check(args):
    units = tm_io.read_corpus(args.input)
    src_lang, tgt_lang = tm_io.infer_langs(units)
    entries = glossary_module.read(args.glossary, src_lang, tgt_lang)
    term_check_module.run(units, entries, check_approved=args.check_approved)
    s = term_check_module.summarize(units)
    print('Total=%d Flagged=%d (%.1f%%)' % (
        s['total'], s['flagged'], (s['flagged'] / s['total'] * 100) if s['total'] else 0.0))
    for status in ('forbidden', 'approved'):
        if s['by_status'].get(status):
            print('  %s: %d' % (status, s['by_status'][status]))
    if args.export:
        csv_writer.write(args.export, units, src_lang or 'SRC', tgt_lang or 'TGT', include_terms=True)
        print('Wrote %s' % args.export)
    if args.report:
        rc = _write_report(args.report, report_adapters.from_term_summary(s, units))
        if rc:
            return rc
    if args.fail_on_issues and s['flagged']:
        return 2
    return 0


def _read_batch_units(paths, src_lang, tgt_lang, args):
    """Reads a batch of mixed bilingual-source/corpus files into a
    ``{label: [TranslationUnit, ...]}`` dict, dispatching by extension the
    same way ``align`` does -- shared by ``quote`` and ``term-extract`` so
    the two commands can't quietly drift on what "a batch of files"
    accepts.
    """
    file_units = {}
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        label = os.path.basename(path)
        if ext in _BILINGUAL_EXTS:
            if not src_lang or not tgt_lang:
                raise ValueError(
                    '--src/--tgt are required to read bilingual source file %r; a .tmx/'
                    '.sdltm corpus input carries its own language codes, but this one '
                    'does not' % path)
            reader_opts = _build_reader_opts(args, ext)
            file_units[label] = align_report.run(
                path, src_lang, tgt_lang, repair_path=args.repair, reader_opts=reader_opts)
        elif ext in tm_io.SUPPORTED_EXTS:
            file_units[label] = tm_io.read_corpus(path)
        else:
            raise ValueError(
                'unsupported input format %r for %r (expected one of %s bilingual or %s '
                'corpus)' % (ext, path, sorted(_BILINGUAL_EXTS), list(tm_io.SUPPORTED_EXTS)))
    return file_units


def _cmd_quote(args):
    tm_units = tm_io.read_corpus(args.tm)
    weights = quote_module.load_weights(args.weights) if args.weights else None

    file_units = _read_batch_units(args.inputs, args.src, args.tgt, args)

    result = quote_module.quote_batch(
        file_units, tm_units, fuzzy_floor=args.fuzzy_floor, weights=weights)
    t = result['total']
    print('Files=%d Segments=%d Words=%d WeightedWords=%.1f' % (
        len(file_units), t['summary']['total'], t['summary']['total_words'], t['weighted_total']))
    for label, entry in result['files'].items():
        print('  %s: %d words -> %.1f weighted' % (
            label, entry['summary']['total_words'], entry['weighted_total']))

    if args.export:
        quote_module.write_quote_csv(args.export, result)
        print('Wrote %s' % args.export)
    if args.report:
        rc = _write_report(args.report, report_adapters.from_quote_result(result))
        if rc:
            return rc
    return 0


def _cmd_term_extract(args):
    file_units = _read_batch_units(args.inputs, args.src, args.tgt, args)
    units = [u for us in file_units.values() for u in us]
    candidates = extract_module.suggest_bilingual_candidates(
        units, args.src, args.tgt, min_freq=args.min_freq, max_ngram=args.max_ngram,
        top_n=args.top_n, min_pair_freq=args.min_pair_freq)
    paired = sum(1 for c in candidates if c['tgt_term'])
    print('Candidates=%d Paired=%d (%.1f%%) -- statistical suggestions only, every row still '
          'needs human review (see language_tools.terms.extract module docstring)' % (
              len(candidates), paired,
              (paired / len(candidates) * 100) if candidates else 0.0))
    extract_module.write_candidates_csv(args.out, candidates)
    print('Wrote %s' % args.out)
    return 0


def _cmd_term_extract_promote(args):
    promoted = extract_module.promote_reviewed_candidates(args.candidates, args.src, args.tgt)
    entries = promoted
    if args.append:
        entries = glossary_module.read(args.glossary, args.src, args.tgt) + promoted
    glossary_module.write(args.glossary, entries)
    print('Promoted=%d Total=%d' % (len(promoted), len(entries)))
    print('Wrote %s' % args.glossary)
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

    if args.report:
        rc = _write_report(args.report, report_adapters.from_align_summary(s))
        if rc:
            return rc

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

    near_dup_p = sub.add_parser(
        'near-dup', help='cluster near-duplicate (not byte-identical) TM entries for review -- '
                          'catches "changed one word/number" duplicates `clean`\'s exact dedup '
                          "can't see; see language_tools.tm.near_dup module docstring for the "
                          'clustering method and its limits')
    near_dup_p.add_argument('input', help='input .tmx or .sdltm file')
    near_dup_p.add_argument('--threshold', type=float, default=0.85,
                             help='minimum edit-distance similarity ratio (0-1] to group two '
                                  'entries together (default: 0.85)')
    near_dup_p.add_argument('--side', choices=['src', 'tgt'], default='src',
                             help='which side\'s text to cluster on (default: src)')
    near_dup_p.add_argument('--min-cluster-size', type=int, default=2,
                             help='minimum entries in a group to report it as a cluster '
                                  '(default: 2)')
    near_dup_p.add_argument('--export', metavar='PATH',
                             help='write a per-cluster CSV (cluster_id/cluster_size/src_text/'
                                  'tgt_text/source_file, one row per unit) to PATH')
    near_dup_p.add_argument('--report', metavar='PATH',
                             help='write a summary report (cluster/unit counts) to PATH as '
                                  'HTML or PDF, by extension')
    near_dup_p.set_defaults(func=_cmd_near_dup)

    merge_p = sub.add_parser('merge', help='merge multiple corpus files into one')
    merge_p.add_argument('inputs', nargs='+', help='one or more .tmx/.sdltm files to merge')
    merge_p.add_argument('-o', '--output', required=True, help='output .tmx or .sdltm path')
    merge_p.add_argument('--strategy', choices=['keep-all', 'prefer-first', 'prefer-last', 'prefer-newer'],
                          default='keep-all', help='conflict resolution strategy (default: keep-all)')
    merge_p.set_defaults(func=_cmd_merge)

    compare_p = sub.add_parser(
        'compare', help='compare 2+ corpus files and report which source segments are unique, '
                         'shared, or conflicting (different target) across them -- run this '
                         'before merge to see what a merge strategy would be resolving')
    compare_p.add_argument('inputs', nargs='+', help='2 or more .tmx/.sdltm files to compare')
    compare_p.add_argument('--export', metavar='PATH',
                            help='write a CSV of conflicting segments (one column per input) '
                                 'to PATH')
    compare_p.add_argument('--fail-on-conflicts', action='store_true',
                            help='exit with status 2 if any conflicting segment was found -- '
                                 'same convention as the other tmtool subcommands\' '
                                 '--fail-on-issues')
    compare_p.add_argument('--report', metavar='PATH',
                            help='write a summary report (inputs/unique/shared/conflicts, plus '
                                 'a conflicts table) to PATH as HTML or PDF, by extension')
    compare_p.set_defaults(func=_cmd_compare)

    stats_p = sub.add_parser('stats', help='print corpus statistics')
    stats_p.add_argument('input', help='input .tmx or .sdltm file')
    stats_p.set_defaults(func=_cmd_stats)

    qa_p = sub.add_parser('qa', help='run QA checks against a corpus file')
    qa_p.add_argument('input', help='input .tmx or .sdltm file')
    qa_p.add_argument('--export', metavar='PATH',
                       help='write a full CSV report (all units, with confidence/status/issues '
                            'columns) to PATH')
    qa_p.add_argument('--report', metavar='PATH',
                       help='write a summary report (totals plus a by-issue-type breakdown) to '
                            'PATH as HTML or PDF, by extension')
    qa_p.set_defaults(func=_cmd_qa)

    leverage_p = sub.add_parser(
        'leverage', help='analyze how much of a corpus can be leveraged from an existing TM '
                          '(Exact/Fuzzy/Repetition/No Match word-count breakdown)')
    leverage_p.add_argument('input', help='candidate .tmx or .sdltm file to analyze')
    leverage_p.add_argument('--tm', required=True,
                             help='reference .tmx or .sdltm file to match candidates against')
    leverage_p.add_argument('--fuzzy-floor', type=float, default=0.50,
                             help='lowest match ratio (0-1) still counted as a match; below it '
                                  'a segment is No Match (default: 0.50)')
    leverage_p.add_argument('--export', metavar='PATH',
                             help='write a full CSV report (all candidate units, with '
                                  'leverage_band/match_pct columns) to PATH')
    leverage_p.add_argument('--report', metavar='PATH',
                             help='write a summary report (totals plus a per-band breakdown) to '
                                  'PATH as HTML or PDF, by extension')
    leverage_p.set_defaults(func=_cmd_leverage)

    term_check_p = sub.add_parser(
        'term-check', help='check a corpus file against a glossary for forbidden translations')
    term_check_p.add_argument('input', help='input .tmx or .sdltm file')
    term_check_p.add_argument('--glossary', required=True,
                               help='glossary file (.csv or .xlsx) with src_term/tgt_term/status columns')
    term_check_p.add_argument('--check-approved', action='store_true',
                               help='also flag segments where a source term appears but its approved '
                                    'translation is missing from the target -- opt-in because a missing '
                                    'approved term is a to-verify hint (synonyms, rewording), not a defect; '
                                    'only rows whose status column explicitly says \'approved\' are '
                                    'covered (blank/unrecognized statuses are skipped), and untranslated '
                                    'segments are left to the qa EMPTY_TARGET check')
    term_check_p.add_argument('--export', metavar='PATH',
                               help='write a full CSV report (all units, with a term_issues '
                                    'column) to PATH')
    term_check_p.add_argument('--fail-on-issues', action='store_true',
                               help='exit with status 2 if any forbidden-term hit was found -- '
                                    'same convention as `align --fail-on-issues`, for scripting '
                                    'a batch check over many corpus files')
    term_check_p.add_argument('--report', metavar='PATH',
                              help='write a summary report (totals plus a by-term hit '
                                   'breakdown) to PATH as HTML or PDF, by extension')
    term_check_p.set_defaults(func=_cmd_term_check)

    quote_p = sub.add_parser(
        'quote', help='estimate a weighted word count for a batch of files against a reference '
                      'TM -- Exact/Fuzzy/Repetition/New words banded per `leverage`, then '
                      'discounted per a pricing weight table (see language_tools.tm.quote.'
                      'DEFAULT_WEIGHTS and --weights)')
    quote_p.add_argument('inputs', nargs='+',
                          help='one or more files to quote: bilingual sources (docx/xlsx/csv/tsv) '
                               'or already-converted .tmx/.sdltm corpora -- mixed batches allowed')
    quote_p.add_argument('--tm', required=True,
                          help='reference .tmx or .sdltm file to leverage every input against')
    quote_p.add_argument('--src', help='source language code, e.g. en-US -- required if any '
                                        'input is a bilingual source file')
    quote_p.add_argument('--tgt', help='target language code, e.g. zh-CN -- required if any '
                                        'input is a bilingual source file')
    quote_p.add_argument('--layout', choices=['auto', 'numbered', 'table', 'alternating'],
                          default='auto', help='docx layout for bilingual .docx inputs; '
                                                'ignored for other formats')
    quote_p.add_argument('--sheet', help='xlsx sheet name (default: first sheet)')
    quote_p.add_argument('--src-col', help='source column: Excel letter (xlsx) or 0-based '
                                            'index (docx table/csv)')
    quote_p.add_argument('--tgt-col', help='target column: Excel letter (xlsx) or 0-based '
                                            'index (docx table/csv)')
    quote_p.add_argument('--delimiter', help='csv/tsv delimiter override (default: auto-sniffed)')
    quote_header = quote_p.add_mutually_exclusive_group()
    quote_header.add_argument('--header', dest='header', action='store_true', default=None,
                               help='treat the first row as a header (xlsx/csv/docx table)')
    quote_header.add_argument('--no-header', dest='header', action='store_false',
                               help='treat the first row as data, not a header')
    quote_p.add_argument('--repair', metavar='PATH',
                          help='path to a repairs.json rule file (bilingual inputs only)')
    quote_p.add_argument('--fuzzy-floor', type=float, default=0.50,
                          help='lowest match ratio (0-1) still counted as a match; below it a '
                               'segment is No Match (default: 0.50)')
    quote_p.add_argument('--weights', metavar='PATH',
                          help='JSON {band: weight_pct} rate-card file overriding '
                               'language_tools.tm.quote.DEFAULT_WEIGHTS -- read that module\'s '
                               'docstring before trusting the built-in defaults for a real quote')
    quote_p.add_argument('--export', metavar='PATH',
                          help='write a per-file + total CSV (segments/words/weighted_words '
                               'plus a band breakdown) to PATH')
    quote_p.add_argument('--report', metavar='PATH',
                          help='write a summary report (per-file weighted-word table) to PATH '
                               'as HTML or PDF, by extension')
    quote_p.set_defaults(func=_cmd_quote)

    term_extract_p = sub.add_parser(
        'term-extract',
        help='suggest term candidates (src frequency + a best-effort tgt pairing) from a batch '
             'of files, for human review -- statistical only, no dictionary/segmenter/alignment '
             'model; read language_tools.terms.extract\'s module docstring for what this can '
             'and cannot do before trusting any of its output')
    term_extract_p.add_argument('inputs', nargs='+',
                                 help='one or more files to mine for term candidates: bilingual '
                                      'sources (docx/xlsx/csv/tsv) or already-converted .tmx/'
                                      '.sdltm corpora, mixed batches allowed')
    term_extract_p.add_argument('--src', required=True, help='source language code, e.g. en-US')
    term_extract_p.add_argument('--tgt', required=True, help='target language code, e.g. zh-CN')
    term_extract_p.add_argument('--layout', choices=['auto', 'numbered', 'table', 'alternating'],
                                 default='auto', help='docx layout for bilingual .docx inputs; '
                                                       'ignored for other formats')
    term_extract_p.add_argument('--sheet', help='xlsx sheet name (default: first sheet)')
    term_extract_p.add_argument('--src-col', help='source column: Excel letter (xlsx) or '
                                                   '0-based index (docx table/csv)')
    term_extract_p.add_argument('--tgt-col', help='target column: Excel letter (xlsx) or '
                                                   '0-based index (docx table/csv)')
    term_extract_p.add_argument('--delimiter', help='csv/tsv delimiter override (default: '
                                                      'auto-sniffed)')
    term_extract_header = term_extract_p.add_mutually_exclusive_group()
    term_extract_header.add_argument('--header', dest='header', action='store_true',
                                      default=None,
                                      help='treat the first row as a header (xlsx/csv/docx table)')
    term_extract_header.add_argument('--no-header', dest='header', action='store_false',
                                      help='treat the first row as data, not a header')
    term_extract_p.add_argument('--repair', metavar='PATH',
                                 help='path to a repairs.json rule file (bilingual inputs only)')
    term_extract_p.add_argument('--min-freq', type=int, default=2,
                                 help='minimum occurrences for a candidate to be considered '
                                      '(default: 2)')
    term_extract_p.add_argument('--max-ngram', type=int, default=4,
                                 help='longest candidate length in tokens (non-CJK) or '
                                      'characters (CJK) (default: 4)')
    term_extract_p.add_argument('--top-n', type=int, default=100,
                                 help='how many top-scoring src candidates to keep and attempt '
                                      'to pair with a tgt suggestion (default: 100)')
    term_extract_p.add_argument('--min-pair-freq', type=int, default=2,
                                 help='minimum co-occurrences before a tgt pairing is even '
                                      'considered (default: 2)')
    term_extract_p.add_argument('--out', required=True, metavar='PATH',
                                 help='write the candidate review sheet (src_term/tgt_term/'
                                      'decision/status/domain/note plus reference frequency '
                                      'columns) to PATH as CSV')
    term_extract_p.set_defaults(func=_cmd_term_extract)

    term_promote_p = sub.add_parser(
        'term-extract-promote',
        help='promote reviewed rows (decision=approve) from a `term-extract` review sheet into '
             'a real glossary file -- the one deliberate gate between a statistical suggestion '
             'and an actual glossary entry')
    term_promote_p.add_argument('candidates', help='the reviewed CSV written by `term-extract` '
                                                     '(edited by a human, decision column filled in)')
    term_promote_p.add_argument('--src', required=True, help='source language code, e.g. en-US')
    term_promote_p.add_argument('--tgt', required=True, help='target language code, e.g. zh-CN')
    term_promote_p.add_argument('--glossary', required=True, metavar='PATH',
                                 help='glossary file (.csv/.xlsx) to write the promoted entries to')
    term_promote_p.add_argument('--append', action='store_true',
                                 help='merge into an existing glossary at PATH instead of '
                                      'overwriting it (PATH must already exist)')
    term_promote_p.set_defaults(func=_cmd_term_extract_promote)

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
    align_p.add_argument('--report', metavar='PATH',
                         help='write a summary report (totals plus a per-move-type breakdown) '
                              'to PATH as HTML or PDF, by extension')
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
