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


def test_render_html_does_not_double_escape_raw_html_table():
    report = Report(title='Review', table=ReportTable(
        columns=['Source'], rows=[['plain &amp; <span class="hl">bit</span>']], raw_html=True))
    out = render_html(report)
    assert '<td>plain &amp; <span class="hl">bit</span></td>' in out


def test_render_html_escapes_normal_table_even_with_html_looking_content():
    report = Report(title='Review', table=ReportTable(
        columns=['Source'], rows=[['<b>not markup</b>']]))
    out = render_html(report)
    assert '&lt;b&gt;not markup&lt;/b&gt;' in out


def test_write_pdf_rejects_raw_html_table(tmp_path):
    pytest.importorskip('reportlab')
    report = Report(title='Review', table=ReportTable(
        columns=['Source'], rows=[['<span class="hl">x</span>']], raw_html=True))
    out = tmp_path / 'r.pdf'
    with pytest.raises(ValueError, match='raw_html'):
        write_pdf(str(out), report)


def test_write_pdf_produces_valid_pdf_with_table(tmp_path):
    pytest.importorskip('reportlab')
    report = Report(title='Leverage Analysis', summary_lines=['Total segments: 3'],
                     table=ReportTable(columns=['Band', 'Segments'], rows=[['exact', '1']]))
    out = tmp_path / 'r.pdf'
    write_pdf(str(out), report)
    data = out.read_bytes()
    assert data.startswith(b'%PDF')
    assert b'%%EOF' in data


def test_write_pdf_registers_cjk_font_for_chinese_content(tmp_path):
    # The align/term adapters put Chinese labels and term text into
    # summary lines/table rows -- default Helvetica (WinAnsi-only) would
    # render those as blanks, so write_pdf() must use a CJK-capable font.
    pytest.importorskip('reportlab')
    report = Report(title='对齐检查', summary_lines=['1:1（一一对应）: 2'],
                     table=ReportTable(columns=['Source term', 'Target term'],
                                       rows=[['big data', '大资料']]))
    out = tmp_path / 'cjk.pdf'
    write_pdf(str(out), report)
    data = out.read_bytes()
    assert data.startswith(b'%PDF')
    assert b'%%EOF' in data
    assert b'STSong-Light' in data
