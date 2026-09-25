"""Tests for the external semantic-review hook (DESIGN.md 15.2 third
priority, "LLM 语义 QA" skeleton). Three layers, mirroring how the hook is
meant to be used: ``attach()``/``summarize()`` against a stub reviewer,
the CSV column, and the CLI's opt-in ``--semantic-review`` wiring.

The load-bearing assertions are the *isolation* ones: the QA channels
(``qa_issues``/``qa_confidence``) must be untouched by a semantic pass,
and nothing may appear in ``meta`` when no reviewer was injected -- those
are what keep an injected reviewer a "to-verify hint" beside the rule
checks instead of a new input to them.
"""
import csv
import os
import subprocess
import sys

from conftest import tmx_path

from language_tools import qa
from language_tools import semantic_review
from language_tools.corpus_readers import tmx_reader
from language_tools.model import TranslationUnit
from language_tools.writers import csv_writer

from semantic_stub import IdenticalTextReviewer

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS_DIR = os.path.join(_REPO_ROOT, 'tests')


def _tu(src, tgt):
    return TranslationUnit('en-US', 'zh-CN', src, tgt)


# ---------------------------------------------------------------- attach


def test_meta_key_absent_when_no_reviewer_injected():
    # The default path: qa.run() alone must leave no trace of the semantic
    # channel -- not even an empty list.
    units = [_tu('A B C', 'A B C'), _tu('Hello', '你好')]
    qa.run(units, 1.0)
    assert all('semantic_issues' not in u.meta for u in units)


def test_attach_writes_own_channel_and_leaves_qa_channels_untouched():
    units = [_tu('A B C', 'A B C'), _tu('Hello', '你好')]
    qa.run(units, 1.0)
    before = {id(u): (list(u.meta['qa_issues']), u.meta['qa_confidence'])
              for u in units}

    semantic_review.attach(units, IdenticalTextReviewer())

    hits = units[0].meta['semantic_issues']
    assert [h.type for h in hits] == ['SEM_SUSPECT_IDENTICAL']
    assert hits[0].span_hint == 'A B C'
    # Reviewed-but-clean units get an explicit empty list ("reviewed,
    # nothing flagged" distinguishable from "never reviewed").
    assert units[1].meta['semantic_issues'] == []
    # The rule checks' verdict did not move at all.
    for u in units:
        issues, conf = before[id(u)]
        assert u.meta['qa_issues'] == issues
        assert u.meta['qa_confidence'] == conf


def test_stub_satisfies_reviewer_protocol():
    assert isinstance(IdenticalTextReviewer(), semantic_review.Reviewer)


def test_reviewer_findings_flow_into_units_read_via_corpus():
    # tmx_reader -> attach is the shape the CLI uses; the 'A B C'
    # duplicate pair in the fixture is also what fires SOURCE_CONFLICT
    # (qa) -- here only one unit, so qa_issues stays empty while the
    # semantic pass flags it: the two channels really are independent.
    units = tmx_reader.read(tmx_path('semantic_review.tmx'))
    semantic_review.attach(units, IdenticalTextReviewer())
    by_src = {u.src_text: u for u in units}
    assert [h.type for h in by_src['A B C'].meta['semantic_issues']] == \
        ['SEM_SUSPECT_IDENTICAL']
    assert by_src['The system is ready.'].meta['semantic_issues'] == []


def test_summarize_shape():
    units = [_tu('A B C', 'A B C'), _tu('Hello', '你好'), _tu('Bye', '再见')]
    semantic_review.attach(units, IdenticalTextReviewer())
    s = semantic_review.summarize(units)
    assert s == {'total': 3, 'flagged': 1, 'by_type': {'SEM_SUSPECT_IDENTICAL': 1}}


# ------------------------------------------------------------------- CSV


def _read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.reader(f))


def test_csv_semantic_column_rendering(tmp_path):
    units = [_tu('A B C', 'A B C'), _tu('Hello', '你好')]
    qa.run(units, 1.0)
    semantic_review.attach(units, IdenticalTextReviewer())
    out = tmp_path / 'report.csv'
    csv_writer.write(str(out), units, include_qa=True, include_semantic=True)
    rows = _read_csv(out)
    assert rows[0] == ['No', 'EN', 'ZH', 'confidence', 'status', 'issues',
                       'semantic_issues']
    # "<TYPE>(<description>) -- <span_hint>" (see csv_writer docstring)
    assert rows[1][6] == ('SEM_SUSPECT_IDENTICAL(target identical to source '
                          '(possible untranslated copy)) -- A B C')
    # reviewed, nothing flagged -> empty cell
    assert rows[2][6] == ''


def test_csv_column_absent_without_include_semantic(tmp_path):
    # Byte-shape guard for every existing caller: without the opt-in the
    # header must stay exactly what it was.
    units = [_tu('Hello', '你好')]
    out = tmp_path / 'plain.csv'
    csv_writer.write(str(out), units, include_qa=True)
    assert _read_csv(out)[0] == ['No', 'EN', 'ZH', 'confidence', 'status', 'issues']


# ------------------------------------------------------------------- CLI


def _run(args, with_stub_on_path=False):
    pythonpath = _REPO_ROOT + (os.pathsep + _TESTS_DIR if with_stub_on_path else '')
    env = dict(os.environ, PYTHONPATH=pythonpath)
    return subprocess.run(
        [sys.executable, '-m', 'language_tools.tm_cli'] + args,
        capture_output=True, text=True, env=env,
    )


def test_cli_without_flag_output_has_no_semantic_section(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('A B C', 'A B C')])
    result = _run(['qa', str(input_)])
    assert result.returncode == 0, result.stderr
    assert 'Semantic' not in result.stdout
    assert 'SEM_SUSPECT_IDENTICAL' not in result.stdout


def _write_tmx(path, units):
    from language_tools.writers import tmx_writer
    tmx_writer.write(str(path), units, 'en-US', 'zh-CN')


def test_cli_end_to_end_with_injected_stub(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('A B C', 'A B C'), _tu('Hello', '你好')])
    out = tmp_path / 'report.csv'
    result = _run(['qa', str(input_), '--semantic-review',
                   'semantic_stub:IdenticalTextReviewer', '--export', str(out)],
                  with_stub_on_path=True)
    assert result.returncode == 0, result.stderr
    assert 'Semantic flagged=1' in result.stdout
    assert 'SEM_SUSPECT_IDENTICAL: 1' in result.stdout
    rows = _read_csv(out)
    assert rows[0][-1] == 'semantic_issues'
    assert rows[1][-1].startswith('SEM_SUSPECT_IDENTICAL(')
    assert rows[2][-1] == ''


def test_cli_exit_code_unaffected_by_semantic_hits(tmp_path):
    # "to-verify hint, not defect verdict": a corpus whose only findings
    # are semantic still exits 0 (qa itself has no --fail-on-issues, but
    # the exit code staying 0 is the invariant worth pinning).
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('A B C', 'A B C')])
    result = _run(['qa', str(input_), '--semantic-review',
                   'semantic_stub:IdenticalTextReviewer'], with_stub_on_path=True)
    assert result.returncode == 0, result.stderr


def test_cli_dot_spec_also_accepted(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('A B C', 'A B C')])
    result = _run(['qa', str(input_), '--semantic-review',
                   'semantic_stub.IdenticalTextReviewer'], with_stub_on_path=True)
    assert result.returncode == 0, result.stderr
    assert 'Semantic flagged=1' in result.stdout


def test_cli_bad_spec_unimportable_module():
    result = _run(['qa', 'tests/fixtures/tmx/semantic_review.tmx',
                   '--semantic-review', 'no_such_reviewer_module:Nope'])
    assert result.returncode != 0
    assert 'cannot import module' in result.stderr


def test_cli_bad_spec_not_a_reviewer(tmp_path):
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('Hello', '你好')])
    # The class name itself is a valid spec (instantiated with no
    # arguments); a module-level string is the cleanest object that can
    # never satisfy the protocol.
    result = _run(['qa', str(input_), '--semantic-review', 'semantic_stub:__doc__'],
                  with_stub_on_path=True)
    assert result.returncode != 0
    assert 'does not satisfy the Reviewer protocol' in result.stderr


def test_cli_spec_naming_a_prebuilt_instance(tmp_path):
    # Module-level singleton, no class instantiation involved.
    input_ = tmp_path / 'in.tmx'
    _write_tmx(input_, [_tu('A B C', 'A B C')])
    result = _run(['qa', str(input_), '--semantic-review',
                   'semantic_stub:REVIEWER'], with_stub_on_path=True)
    assert result.returncode == 0, result.stderr
    assert 'Semantic flagged=1' in result.stdout
