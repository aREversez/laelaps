import os
import subprocess
import sys

from conftest import fixture_path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args, cwd=None):
    env = dict(os.environ, PYTHONPATH=_REPO_ROOT)
    return subprocess.run(
        [sys.executable, '-m', 'language_tools.cli'] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def test_cli_basic_all_formats(tmp_path):
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode == 0, result.stderr
    assert 'Units=4' in result.stdout
    assert (tmp_path / 'out.sdltm').exists()
    assert (tmp_path / 'out.tmx').exists()
    assert (tmp_path / 'out.csv').exists()


def test_cli_missing_src_tgt_for_bilingual_source_errors():
    result = _run([fixture_path('basic.docx'), '-o', '/tmp/should_not_exist'])
    assert result.returncode != 0
    assert '--src and --tgt are required' in result.stderr


def test_cli_default_output_base_derived_from_input(tmp_path):
    import shutil
    shutil.copy(fixture_path('basic.docx'), tmp_path / 'mydoc.docx')
    result = _run(['mydoc.docx', '--src', 'en-US', '--tgt', 'zh-CN'], cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'mydoc.sdltm').exists()
    assert (tmp_path / 'mydoc.tmx').exists()
    assert (tmp_path / 'mydoc.csv').exists()


def test_cli_single_format_via_output_extension(tmp_path):
    out_path = str(tmp_path / 'single.tmx')
    result = _run([fixture_path('basic.docx'), '-o', out_path, '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'single.tmx').exists()
    assert not (tmp_path / 'single.sdltm').exists()
    assert not (tmp_path / 'single.csv').exists()


def test_cli_to_flag_repeatable(tmp_path):
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
                   '--to', 'tmx', '--to', 'csv'])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'out.tmx').exists()
    assert (tmp_path / 'out.csv').exists()
    assert not (tmp_path / 'out.sdltm').exists()


def test_cli_corpus_to_corpus_infers_language(tmp_path):
    step1 = str(tmp_path / 'step1')
    r1 = _run([fixture_path('basic.docx'), '-o', step1, '--src', 'en-US', '--tgt', 'zh-CN', '--to', 'tmx'])
    assert r1.returncode == 0, r1.stderr

    step2 = str(tmp_path / 'step2')
    r2 = _run([step1 + '.tmx', '-o', step2, '--to', 'sdltm'])
    assert r2.returncode == 0, r2.stderr
    assert 'Units=4' in r2.stdout
    assert (tmp_path / 'step2.sdltm').exists()


def test_cli_docx_layout_override(tmp_path):
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('table_layout.docx'), '-o', out_base,
                   '--src', 'en-US', '--tgt', 'zh-CN', '--layout', 'table'])
    assert result.returncode == 0, result.stderr
    assert 'Units=3' in result.stdout


def test_cli_min_confidence_reported(tmp_path):
    out_base = str(tmp_path / 'out')
    # basic.docx has one unit with a real NUMBER_MISMATCH issue (confidence
    # 0.75) and three clean ones (confidence 1.0) -- 0.9 filters out just
    # the one with an issue, not everything, which also exercises a normal
    # (not edge-case) --min-confidence value end to end.
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
                   '--min-confidence', '0.9'])
    assert result.returncode == 0, result.stderr
    assert 'Units=4' in result.stdout
    assert 'Exported=3' in result.stdout


def test_cli_min_confidence_rejects_out_of_range_value(tmp_path):
    # confidence is a 0..1 score; a value above 1 could be misread as "no
    # filtering" (assuming it's a percentage) rather than "stricter than
    # perfect, filters everything" -- CLI-level input validation should
    # reject it outright with a clear message instead of silently doing
    # something the person probably didn't intend.
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
                   '--min-confidence', '1.01'])
    assert result.returncode != 0
    assert 'must be between 0 and 1' in result.stderr
