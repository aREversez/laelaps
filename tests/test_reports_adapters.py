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
