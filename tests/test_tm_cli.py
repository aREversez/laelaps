import os
import subprocess
import sys

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
