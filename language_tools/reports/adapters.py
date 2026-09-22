"""Turns each report-producing module's own summary shape into the generic
``render.Report`` structure. One function per source, named after the
module + function whose output it adapts, so it's obvious at a glance
which upstream shape each adapter depends on and needs updating alongside.
"""
from language_tools import align_report as align_report_module
from language_tools.reports.render import Report, ReportTable
from language_tools.tm import leverage as leverage_module
from language_tools.tm import qa_report as qa_report_module


def from_qa_summary(summary):
    """Adapts ``qa_report.summarize()``'s ``{'total', 'flagged', 'by_type'}``."""
    total, flagged = summary['total'], summary['flagged']
    pct = (flagged / total * 100) if total else 0.0
    lines = ['Total segments: %d' % total, 'Flagged: %d (%.1f%%)' % (flagged, pct)]
    rows = [[t, str(summary['by_type'][t])] for t in qa_report_module.ISSUE_TYPES
             if summary['by_type'].get(t)]
    table = ReportTable(columns=['Issue type', 'Count'], rows=rows) if rows else None
    return Report(title='QA Report', summary_lines=lines, table=table)


def from_leverage_summary(summary):
    """Adapts ``tm.leverage.summarize()``'s ``{'total', 'total_words', 'bands'}``."""
    lines = ['Total segments: %d' % summary['total'], 'Total words: %d' % summary['total_words']]
    rows = [[band, str(summary['bands'][band]['count']), str(summary['bands'][band]['words'])]
            for band in leverage_module.BANDS]
    table = ReportTable(columns=['Band', 'Segments', 'Words'], rows=rows)
    return Report(title='Leverage Analysis', summary_lines=lines, table=table)


def from_near_dup_summary(summary):
    """Adapts ``tm.near_dup.summarize()``'s ``{'cluster_count',
    'total_units'}``. No detail table -- the per-cluster content belongs
    in the CSV export (``near_dup.write_clusters_csv()``), which a
    reviewer needs to actually act on, not a summary report.
    """
    lines = ['Clusters found: %d' % summary['cluster_count'],
              'Units in a cluster: %d' % summary['total_units']]
    return Report(title='Near-Duplicate Clusters', summary_lines=lines, table=None)


def from_quote_result(result):
    """Adapts ``tm.quote.quote_batch()``'s ``{'files', 'total'}``. Unlike
    the other adapters here, the detail table is per *file* (Words /
    Weighted words), not per band -- a quote is read as "what does each
    file cost", with the band breakdown available in the CSV export
    (``quote.write_quote_csv()``) for whoever wants to audit the pricing.
    """
    t = result['total']
    lines = ['Files: %d' % len(result['files']),
              'Total segments: %d' % t['summary']['total'],
              'Total words: %d' % t['summary']['total_words'],
              'Weighted words: %.1f' % t['weighted_total']]
    rows = [[label, str(entry['summary']['total_words']), '%.1f' % entry['weighted_total']]
            for label, entry in result['files'].items()]
    table = ReportTable(columns=['File', 'Words', 'Weighted words'], rows=rows) if rows else None
    return Report(title='Quote Estimate', summary_lines=lines, table=table)


def from_align_summary(summary):
    """Adapts ``align_report.summarize()``'s ``{'total', 'gap_count',
    'move_counts', 'qa_flagged'}``. ``move_counts`` is labeled via
    ``align_report.move_label()`` so the report reads in the reviewer's
    terms, not raw move codes -- same presentation choice as the GUI
    alignment-check table's 对齐方式 column.
    """
    lines = ['Total segments: %d' % summary['total'],
             'Gaps (no corresponding sentence): %d' % summary['gap_count'],
             'QA-flagged: %d' % summary['qa_flagged']]
    rows = [['%s（%s）' % (code, align_report_module.move_label(code)), str(count)]
            for code, count in sorted(summary['move_counts'].items())]
    table = ReportTable(columns=['Move type', 'Segments'], rows=rows) if rows else None
    return Report(title='Alignment Check', summary_lines=lines, table=table)


def from_term_summary(summary, units):
    """Adapts ``terms.check.summarize()``'s ``{'total', 'flagged',
    'by_status'}`` plus the checked units themselves -- unlike QA's fixed
    issue codes, a term hit names its own glossary entry, so the per-term
    breakdown can only be aggregated from ``meta['term_issues']`` after
    the fact, not from the summary dict alone. Rows are keyed per hit
    *direction* too ('Forbidden' = wrong string present, 'Approved
    missing' = preferred string absent) -- the same term pair checked in
    both directions must not merge into one row. Hits without a ``status``
    key (written before the approved direction existed) can only be
    forbidden-direction hits, hence the ``.get`` default.
    """
    total, flagged = summary['total'], summary['flagged']
    pct = (flagged / total * 100) if total else 0.0
    lines = ['Total segments: %d' % total, 'Flagged: %d (%.1f%%)' % (flagged, pct)]
    counts = {}
    for u in units:
        for hit in u.meta.get('term_issues', []):
            key = (hit['src_term'], hit['tgt_term'], hit.get('status', 'forbidden'))
            counts[key] = counts.get(key, 0) + 1
    status_labels = {'forbidden': 'Forbidden', 'approved': 'Approved missing'}
    rows = [[src, tgt, status_labels.get(status, status), str(n)]
            for (src, tgt, status), n in
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    table = ReportTable(columns=['Source term', 'Target term', 'Status', 'Hits'],
                        rows=rows) if rows else None
    return Report(title='Term-Consistency Check', summary_lines=lines, table=table)


def from_compare_report(report):
    """Adapts ``tm.compare.compare()``'s ``{'labels', 'totals',
    'unique_segments', 'shared_segments', 'conflicts'}``.
    """
    labels = report['labels']
    lines = ['Inputs: %d' % len(labels)]
    lines += ['%s: %d segments, %d unique to this TM' %
              (label, report['totals'][label], report['unique_segments'][label])
              for label in labels]
    lines.append('Shared: %d' % report['shared_segments'])
    lines.append('Conflicts: %d' % len(report['conflicts']))
    rows = [[entry['src']] + [';'.join(entry['labels'].get(label, [])) for label in labels]
            for entry in report['conflicts']]
    table = ReportTable(columns=['Source'] + labels, rows=rows) if rows else None
    return Report(title='TM Comparison', summary_lines=lines, table=table)
