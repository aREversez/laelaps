"""Turns each report-producing module's own summary shape into the generic
``render.Report`` structure. One function per source, named after the
module + function whose output it adapts, so it's obvious at a glance
which upstream shape each adapter depends on and needs updating alongside.
"""
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
