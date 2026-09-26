import pytest

from language_tools import align_report

_DOCX = 'tests/fixtures/docx/basic.docx'


def test_run_returns_units_with_alignment_and_qa_meta():
    units = align_report.run(_DOCX, 'en-US', 'zh-CN')
    assert len(units) > 0
    for u in units:
        assert 'align_move' in u.meta
        assert 'align_gap' in u.meta
        assert 'qa_issues' in u.meta
        assert 'qa_confidence' in u.meta


def test_run_raises_for_corpus_format(tmp_path):
    bad = tmp_path / 'in.tmx'
    bad.write_text('<tmx/>')
    with pytest.raises(ValueError, match='unsupported bilingual source format'):
        align_report.run(str(bad), 'en-US', 'zh-CN')


def test_run_raises_for_totally_unknown_format(tmp_path):
    bad = tmp_path / 'in.pdf'
    bad.write_text('not a docx')
    with pytest.raises(ValueError):
        align_report.run(str(bad), 'en-US', 'zh-CN')


def test_summarize_counts_total_moves_and_gaps():
    units = align_report.run(_DOCX, 'en-US', 'zh-CN')
    s = align_report.summarize(units)
    assert s['total'] == len(units)
    assert sum(s['move_counts'].values()) == len(units)
    assert s['gap_count'] == sum(1 for u in units if u.meta['align_gap'])
    assert s['qa_flagged'] == sum(1 for u in units if u.meta['qa_issues'])


def test_summarize_empty_units_does_not_raise():
    s = align_report.summarize([])
    assert s == {'total': 0, 'gap_count': 0, 'move_counts': {}, 'qa_flagged': 0}


def test_move_label_translates_known_codes():
    assert align_report.move_label('1:1') == '一一对应'
    assert align_report.move_label('2:1') == '合并（2→1）'
    assert align_report.move_label('1:0') == '跳过（原文无对应）'


def test_move_label_falls_back_to_raw_code_for_unknown_move():
    assert align_report.move_label('9:9') == '9:9'


def test_move_labels_cover_every_move_aligner_can_actually_produce():
    # Kill-test-style guard: MOVE_LABELS is documented as exhaustive
    # against aligner.MATCHES, not a best-effort guess. If MATCHES grows
    # a move this table doesn't know about, this test should catch the
    # drift immediately rather than silently falling back to raw codes
    # in the GUI later.
    from language_tools.align.aligner import MATCHES
    for src_n, tgt_n in MATCHES:
        code = '%d:%d' % (src_n, tgt_n)
        assert code in align_report.MOVE_LABELS, 'no label for aligner move %r' % code
