import os
import subprocess
import sys

import pytest

from language_tools.corpus_readers import tmx_reader
from language_tools.model import TranslationUnit
from language_tools.writers import tmx_writer

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args):
    env = dict(os.environ, PYTHONPATH=_REPO_ROOT)
    return subprocess.run(
        [sys.executable, '-m', 'language_tools.tm_cli'] + args,
        capture_output=True, text=True, env=env,
    )


def _write_tmx(path, units, src_lang='en-US', tgt_lang='zh-CN'):
    tmx_writer.write(str(path), units, src_lang, tgt_lang)


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def test_clean_removes_duplicates_and_writes_output(tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好'), _u('Bye', '再见')])
    out = tmp_path / 'out.tmx'
    result = _run(['clean', str(src), '-o', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Duplicates=1' in result.stdout
    assert out.exists()
    units = tmx_reader.read(str(out))
    assert len(units) == 2


def test_clean_defaults_to_overwriting_input(tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好')])
    result = _run(['clean', str(src)])
    assert result.returncode == 0, result.stderr
    units = tmx_reader.read(str(src))
    assert len(units) == 1


def test_merge_two_files_keep_all(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Bye', '再见')])
    out = tmp_path / 'merged.tmx'
    result = _run(['merge', str(a), str(b), '-o', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Output=2' in result.stdout
    units = tmx_reader.read(str(out))
    assert len(units) == 2


def test_merge_prefer_last_resolves_conflict(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Ready', '已就绪')])
    _write_tmx(b, [_u('Ready', '准备好了')])
    out = tmp_path / 'merged.tmx'
    result = _run(['merge', str(a), str(b), '-o', str(out), '--strategy', 'prefer-last'])
    assert result.returncode == 0, result.stderr
    assert 'ConflictsResolved=1' in result.stdout
    units = tmx_reader.read(str(out))
    assert len(units) == 1
    assert units[0].tgt_text == '准备好了'


def test_stats_prints_summary(tmp_path):
    # Note: the tmx writer itself drops empty-source/empty-target units
    # (see writers/tmx_writer.py), so a written-then-read-back corpus can
    # never contain one -- empty-segment counting is covered directly
    # against in-memory units in test_tm_stats.py instead.
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好'), _u('Bye', '再见')])
    result = _run(['stats', str(src)])
    assert result.returncode == 0, result.stderr
    assert 'Total=3' in result.stdout
    assert 'Unique=2' in result.stdout
    assert 'EmptySource=0' in result.stdout
    assert 'en-US-zh-CN' in result.stdout


def test_unsupported_format_errors_cleanly(tmp_path):
    bad = tmp_path / 'in.txt'
    bad.write_text('not a corpus file')
    result = _run(['stats', str(bad)])
    assert result.returncode != 0
    assert 'unsupported corpus format' in result.stderr


def test_qa_prints_summary_and_flagged_breakdown(tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Found %d results.', '找到了结果。')])
    result = _run(['qa', str(src)])
    assert result.returncode == 0, result.stderr
    assert 'Total=2' in result.stdout
    assert 'Flagged=1' in result.stdout
    assert 'PLACEHOLDER_MISMATCH: 1' in result.stdout


def test_qa_export_writes_full_csv_report(tmp_path):
    src = tmp_path / 'in.tmx'
    out = tmp_path / 'report.csv'
    _write_tmx(src, [_u('Hello', '你好'), _u('Found %d results.', '找到了结果。')])
    result = _run(['qa', str(src), '--export', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert 'confidence' in content
    assert 'PLACEHOLDER_MISMATCH' in content
    # both rows present, not just the flagged one -- export is the full
    # corpus with QA columns, not a filtered "problems only" subset.
    assert content.count('\n') >= 3  # header + 2 data rows (+ trailing newline)


# --------------------------------------------------------------- term-check

def _write_glossary_csv(path, rows):
    lines = ['src_term,tgt_term,status'] + ['%s,%s,%s' % row for row in rows]
    path.write_text('\n'.join(lines), encoding='utf-8')


def test_term_check_prints_summary(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('big data.', '大资料。'), _u('clean sentence.', '干净的句子。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    result = _run(['term-check', str(src), '--glossary', str(gloss)])
    assert result.returncode == 0, result.stderr
    assert 'Total=2' in result.stdout
    assert 'Flagged=1' in result.stdout
    assert '  forbidden: 1' in result.stdout


def test_term_check_check_approved_flag_fires_approved_direction(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('about big data.', '关于海量数据。')])
    _write_glossary_csv(gloss, [('big data', '大数据', 'approved')])
    # Without the flag: approved direction stays unchecked, nothing fires.
    off = _run(['term-check', str(src), '--glossary', str(gloss)])
    assert off.returncode == 0, off.stderr
    assert 'Flagged=0' in off.stdout
    # With the flag: missing preferred translation is a to-verify hit.
    on = _run(['term-check', str(src), '--glossary', str(gloss), '--check-approved'])
    assert on.returncode == 0, on.stderr
    assert 'Flagged=1' in on.stdout
    assert '  approved: 1' in on.stdout


def test_term_check_check_approved_export_labels_hint(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    out = tmp_path / 'report.csv'
    _write_tmx(src, [_u('about big data.', '关于海量数据。')])
    _write_glossary_csv(gloss, [('big data', '大数据', 'approved')])
    result = _run(['term-check', str(src), '--glossary', str(gloss),
                   '--check-approved', '--export', str(out)])
    assert result.returncode == 0, result.stderr
    content = out.read_text(encoding='utf-8-sig')
    assert '未用推荐译法 big data->大数据' in content


def test_term_check_export_writes_full_csv_report(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    out = tmp_path / 'report.csv'
    _write_tmx(src, [_u('big data.', '大资料。'), _u('clean sentence.', '干净的句子。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--export', str(out)])
    assert result.returncode == 0, result.stderr
    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert 'term_issues' in content
    assert 'big data->大资料' in content
    # both rows present, same "full corpus, not filtered" convention as `qa --export`
    assert content.count('\n') >= 3


def test_term_check_fail_on_issues_is_off_by_default(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('big data.', '大资料。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    result = _run(['term-check', str(src), '--glossary', str(gloss)])
    assert result.returncode == 0, result.stderr


def test_term_check_fail_on_issues_exits_2_when_flagged(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('big data.', '大资料。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--fail-on-issues'])
    assert result.returncode == 2


def test_term_check_fail_on_issues_exits_0_when_clean(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('clean sentence.', '干净的句子。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--fail-on-issues'])
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------- align
# `align` is the CLI counterpart to the GUI's 对齐检查 page -- both wrap
# language_tools.align_report.run()/summarize(). No mocking here (unlike
# the page's own tests): this drives the real reader + aligner + QA
# pipeline through a subprocess, same as every other tmtool test in this
# file, using small hand-built bilingual CSVs to land on deterministic
# outcomes (a real docx's exact GAP/merge shape depends on the DP
# aligner's cost model and isn't practical to target on demand -- see
# tests/test_aligner_gap_moves.py's docstring for that same tradeoff).

def _write_bilingual_csv(path, rows):
    # No header, plain "src,tgt" rows -- --no-header below tells the
    # reader not to treat row 0 as a header.
    path.write_text('\n'.join('%s,%s' % row for row in rows), encoding='utf-8')


def test_align_prints_summary_for_a_clean_bilingual_csv(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [('Hello there.', '你好。'), ('Bye now.', '再见。')])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header'])
    assert result.returncode == 0, result.stderr
    assert 'Units=2 Gaps=0 Flagged=0' in result.stdout
    assert '1:1 (一一对应): 2' in result.stdout


def test_align_reports_qa_flagged_units(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [
        ('Hello there.', '你好。'),
        ('Found %d results.', '找到了结果。'),  # placeholder mismatch
    ])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header'])
    assert result.returncode == 0, result.stderr
    assert 'Units=2 Gaps=0 Flagged=1' in result.stdout


def test_align_fail_on_issues_is_off_by_default(tmp_path):
    # A successful run always exits 0 unless --fail-on-issues is given,
    # same convention as every other tmtool subcommand -- the summary
    # line is informational, it doesn't change the exit code on its own.
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [('Found %d results.', '找到了结果。')])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header'])
    assert result.returncode == 0, result.stderr


def test_align_fail_on_issues_exits_2_when_flagged(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [('Found %d results.', '找到了结果。')])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header',
                   '--fail-on-issues'])
    assert result.returncode == 2, result.stderr


def test_align_fail_on_issues_exits_0_when_clean(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [('Hello there.', '你好。')])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header',
                   '--fail-on-issues'])
    assert result.returncode == 0, result.stderr


def test_align_export_writes_full_csv_with_align_and_qa_columns(tmp_path):
    src = tmp_path / 'in.csv'
    out = tmp_path / 'report.csv'
    _write_bilingual_csv(src, [
        ('Hello there.', '你好。'),
        ('Found %d results.', '找到了结果。'),
    ])
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN', '--no-header',
                   '--export', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    assert out.exists()
    content = out.read_text(encoding='utf-8-sig')
    assert 'align_move' in content
    assert 'PLACEHOLDER_MISMATCH' in content
    # both rows present, not filtered to problems only -- same convention
    # as `qa --export`.
    assert content.count('\n') >= 3


def test_align_requires_src_and_tgt(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [('Hello there.', '你好。')])
    result = _run(['align', str(src)])
    assert result.returncode != 0
    assert 'required' in result.stderr.lower()


def test_align_unsupported_format_errors_cleanly(tmp_path):
    bad = tmp_path / 'in.tmx'
    bad.write_text('<tmx/>')
    result = _run(['align', str(bad), '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode != 0
    assert 'unsupported bilingual source format' in result.stderr


def test_leverage_reports_exact_and_no_match_word_counts(tmp_path):
    tm = tmp_path / 'tm.tmx'
    _write_tmx(tm, [_u('Click OK to continue.', '点击确定以继续。')])
    candidate = tmp_path / 'in.tmx'
    _write_tmx(candidate, [
        _u('Click OK to continue.', '点击确定继续。'),
        _u('Totally unrelated content here.', '这里是完全无关的内容。'),
    ])
    result = _run(['leverage', str(candidate), '--tm', str(tm)])
    assert result.returncode == 0, result.stderr
    assert 'Total=2 Words=8' in result.stdout
    assert 'exact: 1 segments, 4 words' in result.stdout
    assert 'no_match: 1 segments, 4 words' in result.stdout


def test_leverage_export_writes_full_csv_with_leverage_columns(tmp_path):
    tm = tmp_path / 'tm.tmx'
    _write_tmx(tm, [_u('Click OK to continue.', '点击确定以继续。')])
    candidate = tmp_path / 'in.tmx'
    _write_tmx(candidate, [_u('Click OK to continue.', '点击确定继续。')])
    out = tmp_path / 'report.csv'
    result = _run(['leverage', str(candidate), '--tm', str(tm), '--export', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    content = out.read_text(encoding='utf-8-sig')
    assert 'leverage_band' in content
    assert 'exact' in content


def test_leverage_requires_tm_argument(tmp_path):
    candidate = tmp_path / 'in.tmx'
    _write_tmx(candidate, [_u('Hello', '你好')])
    result = _run(['leverage', str(candidate)])
    assert result.returncode != 0
    assert 'required' in result.stderr.lower()


def test_compare_reports_unique_shared_and_conflicts(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好'), _u('Only in a', '只在a')])
    _write_tmx(b, [_u('Hello', '您好')])
    result = _run(['compare', str(a), str(b)])
    assert result.returncode == 0, result.stderr
    assert 'Inputs=2' in result.stdout
    assert 'a.tmx: 2 segments, 1 unique to this TM' in result.stdout
    assert 'b.tmx: 1 segments, 0 unique to this TM' in result.stdout
    assert 'Shared=0 Conflicts=1' in result.stdout


def test_compare_export_writes_conflicts_csv(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Hello', '您好')])
    out = tmp_path / 'conflicts.csv'
    result = _run(['compare', str(a), str(b), '--export', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    content = out.read_text(encoding='utf-8-sig')
    assert 'source,a.tmx,b.tmx' in content
    assert '你好' in content and '您好' in content


def test_compare_fail_on_conflicts_exits_nonzero(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Hello', '您好')])
    result = _run(['compare', str(a), str(b), '--fail-on-conflicts'])
    assert result.returncode == 2


def test_compare_no_conflicts_does_not_fail_even_with_flag(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Hello', '你好')])
    result = _run(['compare', str(a), str(b), '--fail-on-conflicts'])
    assert result.returncode == 0, result.stderr


def test_compare_requires_at_least_two_inputs(tmp_path):
    a = tmp_path / 'a.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    result = _run(['compare', str(a)])
    assert result.returncode != 0
    assert 'at least 2' in result.stderr


def test_qa_report_writes_html(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_u('Hello', ''), _u('Bye', '再见')])
    out = tmp_path / 'report.html'
    result = _run(['qa', str(input_), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    content = out.read_text(encoding='utf-8')
    assert '<title>QA Report</title>' in content


def test_leverage_report_writes_html(tmp_path):
    tm = tmp_path / 'tm.tmx'
    _write_tmx(tm, [_u('Click OK to continue.', '点击确定继续。')])
    candidate = tmp_path / 'in.tmx'
    _write_tmx(candidate, [_u('Click OK to continue.', '')])
    out = tmp_path / 'report.html'
    result = _run(['leverage', str(candidate), '--tm', str(tm), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    content = out.read_text(encoding='utf-8')
    assert '<title>Leverage Analysis</title>' in content
    assert 'exact' in content


def test_compare_report_writes_html(tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Hello', '您好')])
    out = tmp_path / 'report.html'
    result = _run(['compare', str(a), str(b), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    content = out.read_text(encoding='utf-8')
    assert '<title>TM Comparison</title>' in content


def test_align_report_writes_html(tmp_path):
    src = tmp_path / 'in.csv'
    _write_bilingual_csv(src, [
        ('Hello there.', '你好。'),
        ('Found %d results.', '找到了结果。'),
    ])
    out = tmp_path / 'report.html'
    result = _run(['align', str(src), '--src', 'en-US', '--tgt', 'zh-CN',
                   '--no-header', '--report', str(out)])
    assert result.returncode == 0, result.stderr
    assert 'Wrote %s' % out in result.stdout
    content = out.read_text(encoding='utf-8')
    assert '<title>Alignment Check</title>' in content
    assert 'QA-flagged: 1' in content


def test_term_check_report_writes_html_with_hit_table(tmp_path):
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('big data.', '大资料。'), _u('clean sentence.', '干净的句子。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    out = tmp_path / 'report.html'
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    content = out.read_text(encoding='utf-8')
    assert '<title>Term-Consistency Check</title>' in content
    assert 'big data' in content and '大资料' in content


def test_report_unsupported_extension_fails_cleanly(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_u('Hello', '你好')])
    out = tmp_path / 'report.txt'
    result = _run(['qa', str(input_), '--report', str(out)])
    assert result.returncode != 0
    assert 'unsupported extension' in result.stderr
    assert not out.exists()


def test_report_pdf_produces_valid_pdf(tmp_path):
    pytest.importorskip('reportlab')
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Hello', '您好')])
    out = tmp_path / 'report.pdf'
    result = _run(['compare', str(a), str(b), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    assert out.read_bytes().startswith(b'%PDF')


def test_term_check_check_approved_skips_rows_with_undeclared_status(tmp_path):
    # status cell left blank *displays* as approved via glossary.read()'s
    # fallback but is marked not-declared -- switching on the opt-in
    # check must not sweep a whole legacy status-less glossary in.
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('about big data.', '关于海量数据。')])
    _write_glossary_csv(gloss, [('big data', '大数据', '')])
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--check-approved'])
    assert result.returncode == 0, result.stderr
    assert 'Flagged=0' in result.stdout


def test_term_check_check_approved_skips_untranslated_segments(tmp_path):
    # An empty target trivially misses the approved term; that's the QA
    # EMPTY_TARGET check's job, not a to-verify hit.
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('about big data.', '')])
    _write_glossary_csv(gloss, [('big data', '大数据', 'approved')])
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--check-approved'])
    assert result.returncode == 0, result.stderr
    assert 'Flagged=0' in result.stdout


def test_term_check_report_pdf_carries_cjk_font(tmp_path):
    # The term report table puts Chinese term text into PDF cells --
    # needs the CJK font registered or glyphs drop to blanks (default
    # Helvetica is WinAnsi-only).
    pytest.importorskip('reportlab')
    src = tmp_path / 'in.tmx'
    gloss = tmp_path / 'glossary.csv'
    _write_tmx(src, [_u('big data.', '大资料。')])
    _write_glossary_csv(gloss, [('big data', '大资料', 'forbidden')])
    out = tmp_path / 'report.pdf'
    result = _run(['term-check', str(src), '--glossary', str(gloss), '--report', str(out)])
    assert result.returncode == 0, result.stderr
    data = out.read_bytes()
    assert data.startswith(b'%PDF')
    assert b'STSong-Light' in data


def test_write_report_surfaces_missing_reportlab_cleanly(tmp_path, monkeypatch, capsys):
    # Without the optional reportlab extra, `--report x.pdf` used to
    # escape as a raw ImportError stack trace (main() only catches
    # ValueError/FileNotFoundError) -- it must come out as a clean
    # error line + non-zero rc instead.
    from language_tools import tm_cli

    def fake_write(path, report):
        raise ImportError('PDF report export requires the optional "reportlab" package')

    monkeypatch.setattr(tm_cli.report_render, 'write', fake_write)
    rc = tm_cli._write_report(str(tmp_path / 'r.pdf'), None)
    assert rc == 1
    assert 'reportlab' in capsys.readouterr().err
