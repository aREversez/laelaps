"""L0 golden baseline for leverage analysis (freezes the tmx/sdltm-input path).

The monolingual-input work (docs: leverage-monolingual design, phase L1) must
not change what the existing corpus-input path reports. This file pins that:
a fixed TM + fixed candidate list is analyzed and every candidate's
(band, pct, repetition) plus the aggregate summary and the CLI's stdout are
compared with a checked-in golden file, ``fixtures/expected/leverage_baseline.json``.

Do NOT regenerate the golden to make a failing run pass. A diff here means
the matching behavior changed; that is only acceptable as a deliberate,
separately-reviewed change (the planned L2 algorithm work), and the golden is
then edited in that same commit with the reason in the commit message.
"""
import json
import os
import subprocess
import sys

from language_tools.model import TranslationUnit
from language_tools.tm import leverage as leverage_module
from language_tools.writers import tmx_writer

from tests.conftest import expected_path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EN, ZH = 'en-US', 'zh-CN'


def _u(src, tgt='', src_lang=EN, tgt_lang=ZH):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


_LONG = 'The system shall log every authentication attempt for audit purposes. ' * 60

TM_UNITS = [
    _u('Click OK to continue.', '点击确定以继续。'),
    _u('The quick brown fox jumps over the lazy dog.', '敏捷的棕色狐狸跳过了懒狗。'),
    _u('Save the file before closing the application.', '关闭应用程序前请保存文件。'),
    _u('Select the mesh density from the drop-down list.', '从下拉列表中选择网格密度。'),
    _u('Enter the boundary condition value.', '输入边界条件值。'),
    _u(_LONG, '长句。'),
    _u('点击确定以继续。', 'Click OK to continue.', src_lang=ZH, tgt_lang=EN),
    _u('请先保存文件，然后关闭应用程序。', 'Save the file, then close the application.', src_lang=ZH, tgt_lang=EN),
    _u('Click OK to continue.', 'wrong pair', src_lang=EN, tgt_lang='ja-JP'),
]

CANDIDATES = [
    _u('Click OK to continue.'),                                   # exact
    _u('  click   ok TO continue.  '),                             # repeats #1 after normalization
    _u('select THE mesh  density from the drop-down list.'),       # exact only after case/space normalization
    _u('The quick brown fox jumps over a lazy dog.'),              # near-exact fuzzy
    _u('Save the file before closing the program.'),               # fuzzy
    _u('Select the mesh density from the list.'),                  # fuzzy
    _u('Enter the boundary condition.'),                           # fuzzy (lower)
    _u('Enter the value.'),                                        # low fuzzy / no match
    _u('Something entirely unrelated to the memory.'),             # no match
    _u('Click OK to continue.'),                                   # repetition of #1
    _u('Something entirely unrelated to the memory.'),             # repetition of #8
    _u(_LONG + 'XY'),                                              # rounds to 100.0, must stay 95-99
    _u(_LONG),                                                     # true exact (long)
    _u(''),                                                        # empty segment
    _u('Enter the boundary condition value.', tgt_lang='ja-JP'),   # en-zh TM has it exact, ja pair must not see it
    _u('Save the file before closing the application.', tgt_lang='de-DE'),  # pair absent from the TM
    _u('点击确定以继续。', src_lang=ZH, tgt_lang=EN),               # zh->en exact
    _u('请先保存文件，然后关闭程序。', src_lang=ZH, tgt_lang=EN),   # zh->en fuzzy
    _u('完全无关的一句话。', src_lang=ZH, tgt_lang=EN),             # zh->en no match
]


def _snapshot(units):
    return [
        {
            'src': u.src_text if len(u.src_text) < 80 else u.src_text[:40] + '...(%d chars)' % len(u.src_text),
            'band': u.meta['leverage_band'],
            'pct': u.meta['leverage_match_pct'],
            'repetition': u.meta['leverage_repetition'],
        }
        for u in units
    ]


def _golden():
    with open(expected_path('leverage_baseline.json'), encoding='utf-8') as f:
        return json.load(f)


def test_analyze_output_matches_golden():
    candidates = [_u(u.src_text, u.tgt_text, u.src_lang, u.tgt_lang) for u in CANDIDATES]
    leverage_module.analyze(TM_UNITS, candidates)
    golden = _golden()
    assert _snapshot(candidates) == golden['per_segment']
    assert leverage_module.summarize(candidates) == golden['summary']


def _run_cli(args):
    env = dict(os.environ, PYTHONPATH=_REPO_ROOT)
    return subprocess.run(
        [sys.executable, '-m', 'language_tools.tm_cli'] + args,
        capture_output=True, text=True, encoding='utf-8', env=env,
    )


def test_cli_corpus_input_stdout_matches_golden(tmp_path):
    # Only the en->zh candidates share one file (a tmx carries one language pair).
    en_zh = [u for u in CANDIDATES if (u.src_lang, u.tgt_lang) == (EN, ZH)]
    tm_path, cand_path = tmp_path / 'tm.tmx', tmp_path / 'cand.tmx'
    tmx_writer.write(str(tm_path), [u for u in TM_UNITS if (u.src_lang, u.tgt_lang) == (EN, ZH)], EN, ZH)
    # tmx_writer drops units with an empty target, so give each candidate a
    # placeholder translation (leverage only reads the source side).
    tmx_writer.write(str(cand_path), [_u(u.src_text, 'x') for u in en_zh], EN, ZH)
    result = _run_cli(['leverage', str(cand_path), '--tm', str(tm_path)])
    assert result.returncode == 0, result.stderr
    assert result.stdout == _golden()['cli_stdout_en_zh']
