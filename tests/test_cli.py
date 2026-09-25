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


def test_cli_jsonl_is_opt_in_not_in_default_bundle(tmp_path):
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / 'out.jsonl').exists()


def test_cli_to_jsonl_explicit(tmp_path):
    out_base = str(tmp_path / 'out')
    result = _run([fixture_path('basic.docx'), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
                   '--to', 'jsonl'])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'out.jsonl').exists()
    assert not (tmp_path / 'out.sdltm').exists()
    assert not (tmp_path / 'out.tmx').exists()
    assert not (tmp_path / 'out.csv').exists()

    import json
    lines = (tmp_path / 'out.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 4
    row = json.loads(lines[0])
    assert row['src_lang'] == 'en-US' and row['tgt_lang'] == 'zh-CN'
    assert row['src'] and row['tgt']


def test_cli_single_jsonl_format_via_output_extension(tmp_path):
    out_path = str(tmp_path / 'single.jsonl')
    result = _run([fixture_path('basic.docx'), '-o', out_path, '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'single.jsonl').exists()
    assert not (tmp_path / 'single.sdltm').exists()


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
    # Uses a purpose-built CSV rather than the shared basic.docx fixture:
    # basic.docx's one-time "Apple Inc. ... Jan. 2024" / "...2024年1月..."
    # NUMBER_MISMATCH is now correctly recognized as a false positive (see
    # test_qa.py's month-name-equivalence tests) and no longer flagged, so
    # basic.docx no longer has a QA issue to filter on here. This fixture
    # has a genuine, unambiguous digit mismatch (42 vs 43) that stays a
    # real mismatch regardless of future equivalence rules.
    src_csv = tmp_path / 'src.csv'
    src_csv.write_text(
        'EN,ZH\n'
        'We shipped 42 units.,我们发货了43个单位。\n'
        'Hello there.,你好。\n'
        'Good morning.,早上好。\n'
        'See you soon.,回头见。\n',
        encoding='utf-8')
    out_base = str(tmp_path / 'out')
    # 0.9 filters out just the one unit with a real issue (confidence
    # 0.75), not everything, which also exercises a normal (not
    # edge-case) --min-confidence value end to end.
    result = _run([str(src_csv), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
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


def test_cli_corrupt_input_reports_clean_error(tmp_path):
    # A fake .docx that isn't really a zip used to spill a full zipfile
    # BadZipFile traceback (not caught by the old ValueError/FileNotFoundError
    # guard). It must now surface as a one-line error with a non-zero exit.
    fake = tmp_path / 'fake.docx'
    fake.write_text('this is not a zip archive', encoding='utf-8')
    out_base = str(tmp_path / 'out')
    result = _run([str(fake), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN'])
    assert result.returncode != 0
    assert 'error:' in result.stderr
    assert 'Traceback' not in result.stderr


def test_cli_non_numeric_src_col_reports_clean_error(tmp_path):
    # --src-col is a 0-based index for csv/docx-table input; a stray Excel
    # letter ('B') makes int() raise ValueError. _build_reader_opts used to
    # run outside the try block, so this too dumped a raw traceback.
    src_csv = tmp_path / 'src.csv'
    src_csv.write_text('EN,ZH\nHello,你好\n', encoding='utf-8')
    out_base = str(tmp_path / 'out')
    result = _run([str(src_csv), '-o', out_base, '--src', 'en-US', '--tgt', 'zh-CN',
                   '--src-col', 'B'])
    assert result.returncode != 0
    assert 'error:' in result.stderr
    assert 'Traceback' not in result.stderr
