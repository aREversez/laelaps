from language_tools import align_report
from language_tools import qa as qa_module
from language_tools.model import TranslationUnit
from language_tools.reports import adapters
from language_tools.tm import compare as compare_module
from language_tools.tm import leverage as leverage_module
from language_tools.tm import qa_report as qa_report_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_from_qa_summary_includes_total_and_flagged_pct():
    summary = qa_report_module.summarize([_u('Hello', '你好')])
    report = adapters.from_qa_summary(summary)
    assert report.title == 'QA Report'
    assert any('Total segments: 1' in line for line in report.summary_lines)


def test_from_qa_summary_table_only_lists_nonzero_issue_types():
    units = [_u('Hello', '')]  # empty target -> flags an issue
    qa_module.run(units, qa_module.expected_length_ratio(units))
    summary = qa_report_module.summarize(units)
    assert summary['flagged'] > 0
    report = adapters.from_qa_summary(summary)
    assert report.table is not None
    assert all(int(row[1]) > 0 for row in report.table.rows)


def test_from_leverage_summary_includes_all_bands():
    tm = [_u('Click OK to continue.', '点击确定继续。')]
    candidates = [_u('Click OK to continue.', '')]
    leverage_module.analyze(tm, candidates)
    summary = leverage_module.summarize(candidates)
    report = adapters.from_leverage_summary(summary)
    assert report.title == 'Leverage Analysis'
    band_names = [row[0] for row in report.table.rows]
    assert band_names == leverage_module.BANDS


def test_from_compare_report_includes_per_label_lines_and_conflict_table():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '您好')]
    cmp_report = compare_module.compare([('a', a), ('b', b)])
    report = adapters.from_compare_report(cmp_report)
    assert report.title == 'TM Comparison'
    assert any('a: 1 segments, 0 unique to this TM' in line for line in report.summary_lines)
    assert report.table.columns == ['Source', 'a', 'b']
    assert report.table.rows == [['Hello', '你好', '您好']]


def test_from_compare_report_no_conflicts_has_no_table():
    a = [_u('Hello', '你好')]
    b = [_u('Hello', '你好')]
    cmp_report = compare_module.compare([('a', a), ('b', b)])
    report = adapters.from_compare_report(cmp_report)
    assert report.table is None


def _align_u(src, tgt, align_move='1:1', align_gap=False):
    return TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt,
        meta={'align_move': align_move, 'align_gap': align_gap})


def test_from_align_summary_totals_and_labeled_move_table():
    units = [
        _align_u('Hello', '你好'),
        _align_u('Bye', '再见', align_move='2:1'),
        _align_u('Dangling', '', align_move='1:0', align_gap=True),
    ]
    report = adapters.from_align_summary(align_report.summarize(units))
    assert report.title == 'Alignment Check'
    assert any('Total segments: 3' in line for line in report.summary_lines)
    assert any('Gaps (no corresponding sentence): 1' in line for line in report.summary_lines)
    # Move codes are labeled via move_label(), not left as raw codes.
    row_labels = [row[0] for row in report.table.rows]
    assert any('2:1' in label and '合并' in label for label in row_labels)


def _term_u(src, tgt, hits=()):
    return TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt,
        meta={'term_issues': [{'src_term': s, 'tgt_term': t, 'note': ''} for s, t in hits]})


def test_from_term_summary_aggregates_hits_per_term_pair():
    units = [
        _term_u('big data rules.', '大资料规则。', hits=[('big data', '大资料')]),
        _term_u('big data and AI.', '大资料和人工智慧。',
                hits=[('big data', '大资料'), ('AI', '人工智慧')]),
        _term_u('clean.', '干净。'),
    ]
    summary = {'total': 3, 'flagged': 2}
    report = adapters.from_term_summary(summary, units)
    assert report.title == 'Term-Consistency Check'
    assert any('Flagged: 2 (66.7%)' in line for line in report.summary_lines)
    # Sorted by hit count desc: 'big data' fired twice, 'AI' once.
    assert report.table.rows == [['big data', '大资料', '2'], ['AI', '人工智慧', '1']]


def test_from_term_summary_no_hits_has_no_table():
    units = [_term_u('clean.', '干净。')]
    report = adapters.from_term_summary({'total': 1, 'flagged': 0}, units)
    assert report.table is None
