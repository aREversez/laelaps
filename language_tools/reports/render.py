"""Renders a generic summary report to HTML or PDF.

Deliberately format-agnostic and knows nothing about QA/leverage/compare/
stats specifically -- ``adapters.py`` is what turns each of those modules'
``summarize()``/``compare()`` output into the ``Report`` shape this module
renders. That split means a fifth report-producing module later only needs
a new adapter function, not a new renderer.

``Report`` mirrors what every ``tmtool`` subcommand already prints to
stdout: a short list of headline facts (``summary_lines``, e.g. "Total: 120"
/ "Flagged: 8 (6.7%)") plus an optional detail table (e.g. the per-band or
per-issue-type breakdown). This is a summary document for a PM/reviewer to
skim or hand to a client -- not a row-per-segment data dump; that's what
the existing ``--export`` CSVs (``writers/csv_writer.py``,
``compare.write_conflicts_csv``) are for, and this module doesn't
duplicate them.

HTML rendering is stdlib-only. PDF rendering needs the optional
``reportlab`` dependency (``pip install language-tools[reports]``) --
``write_pdf()`` imports it lazily so importing this module, or using
``write_html()``, never requires it.
"""
import html as _html
from dataclasses import dataclass, field


@dataclass
class ReportTable:
    columns: list
    rows: list


@dataclass
class Report:
    title: str
    summary_lines: list = field(default_factory=list)
    table: ReportTable = None


def render_html(report):
    """Returns a complete, self-contained HTML document as a string."""
    parts = [
        '<!doctype html>',
        '<html><head><meta charset="utf-8">',
        '<title>%s</title>' % _html.escape(report.title),
        '<style>',
        'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;'
        'max-width:52rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}',
        'h1{font-size:1.4rem;margin-bottom:0.75rem}',
        'ul{padding-left:1.2rem;line-height:1.5}',
        'table{border-collapse:collapse;width:100%;margin-top:1.25rem}',
        'th,td{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left;font-size:0.9rem}',
        'th{background:#f5f5f5}',
        '</style></head><body>',
        '<h1>%s</h1>' % _html.escape(report.title),
    ]
    if report.summary_lines:
        parts.append('<ul>')
        parts.extend('<li>%s</li>' % _html.escape(line) for line in report.summary_lines)
        parts.append('</ul>')
    if report.table is not None and report.table.rows:
        parts.append('<table><thead><tr>')
        parts.extend('<th>%s</th>' % _html.escape(str(c)) for c in report.table.columns)
        parts.append('</tr></thead><tbody>')
        for row in report.table.rows:
            parts.append('<tr>')
            parts.extend('<td>%s</td>' % _html.escape(str(cell)) for cell in row)
            parts.append('</tr>')
        parts.append('</tbody></table>')
    parts.append('</body></html>')
    return ''.join(parts)


def write_html(path, report):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(render_html(report))


def write_pdf(path, report):
    """Writes ``report`` as a one-page-flowing PDF via reportlab. Raises
    ``ImportError`` with an actionable install instruction if reportlab
    isn't installed, rather than letting the raw import error surface.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                         Spacer, Table, TableStyle)
    except ImportError as e:
        raise ImportError(
            'PDF report export requires the optional "reportlab" package -- install it with '
            '`pip install language-tools[reports]` (or `pip install reportlab` directly) to '
            'use write_pdf() / `--report *.pdf`.'
        ) from e

    styles = getSampleStyleSheet()
    story = [Paragraph(_html.escape(report.title), styles['Title']), Spacer(1, 12)]
    if report.summary_lines:
        story.append(ListFlowable(
            [ListItem(Paragraph(_html.escape(line), styles['Normal'])) for line in report.summary_lines],
            bulletType='bullet'))
        story.append(Spacer(1, 12))
    if report.table is not None and report.table.rows:
        data = [[str(c) for c in report.table.columns]]
        data += [[str(cell) for cell in row] for row in report.table.rows]
        table = Table(data, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(table)
    SimpleDocTemplate(path, pagesize=A4).build(story)


def write(path, report):
    """Dispatches to ``write_html``/``write_pdf`` by ``path``'s extension.
    Raises ``ValueError`` for any other extension -- callers (the CLI)
    should validate the extension up front so this is a backstop, not the
    primary error message a user sees.
    """
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    if ext in ('html', 'htm'):
        write_html(path, report)
    elif ext == 'pdf':
        write_pdf(path, report)
    else:
        raise ValueError('unsupported report extension %r (expected .html or .pdf)' % ext)
