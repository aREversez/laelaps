import pytest

from language_tools.reports.render import Report, ReportTable, render_html, write, write_html, write_pdf


def test_render_html_includes_title_and_summary_lines():
    report = Report(title='My Report', summary_lines=['Total: 5', 'Flagged: 2'])
    out = render_html(report)
    assert '<title>My Report</title>' in out
    assert '<h1>My Report</h1>' in out
    assert '<li>Total: 5</li>' in out
    assert '<li>Flagged: 2</li>' in out


def test_render_html_escapes_content():
    report = Report(title='<script>alert(1)</script>', summary_lines=['A & B < C'])
    out = render_html(report)
    assert '<script>alert(1)</script>' not in out
    assert '&lt;script&gt;' in out
    assert 'A &amp; B &lt; C' in out


def test_render_html_omits_table_when_no_rows():
    report = Report(title='Empty', summary_lines=['nothing here'],
                     table=ReportTable(columns=['a', 'b'], rows=[]))
    out = render_html(report)
    assert '<table>' not in out


def test_render_html_includes_table_rows():
    report = Report(title='With table', table=ReportTable(
        columns=['Band', 'Count'], rows=[['exact', '3'], ['no_match', '1']]))
    out = render_html(report)
    assert '<th>Band</th>' in out
    assert '<td>exact</td>' in out
    assert '<td>3</td>' in out


def test_write_html_writes_file(tmp_path):
    report = Report(title='T', summary_lines=['x'])
    out = tmp_path / 'r.html'
    write_html(str(out), report)
    assert '<title>T</title>' in out.read_text(encoding='utf-8')


def test_write_dispatches_by_extension_html(tmp_path):
    report = Report(title='T', summary_lines=['x'])
    out = tmp_path / 'r.html'
    write(str(out), report)
    assert out.exists()


def test_write_dispatches_by_extension_pdf(tmp_path):
    pytest.importorskip('reportlab')
    report = Report(title='T', summary_lines=['x'])
    out = tmp_path / 'r.pdf'
    write(str(out), report)
    assert out.exists()
    assert out.read_bytes().startswith(b'%PDF')


def test_write_unsupported_extension_raises(tmp_path):
    report = Report(title='T')
    out = tmp_path / 'r.txt'
    with pytest.raises(ValueError, match='unsupported report extension'):
        write(str(out), report)


def test_write_pdf_produces_valid_pdf_with_table(tmp_path):
    pytest.importorskip('reportlab')
    report = Report(title='Leverage Analysis', summary_lines=['Total segments: 3'],
                     table=ReportTable(columns=['Band', 'Segments'], rows=[['exact', '1']]))
    out = tmp_path / 'r.pdf'
    write_pdf(str(out), report)
    data = out.read_bytes()
    assert data.startswith(b'%PDF')
    assert b'%%EOF' in data
