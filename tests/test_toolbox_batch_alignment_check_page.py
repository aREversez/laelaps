import csv
import os
import shutil

from toolbox.tools.batch_alignment_check.page import BatchAlignmentCheckPage
from toolbox.widgets import lang_combo_code

from conftest import fixture_path


def _status_text(page, row):
    return page.file_table.item(row, 1).text()


def _status_color(page, row):
    # .name() lowercases ('#b23b3b'), LOG_COLORS is uppercase.
    return page.file_table.item(row, 1).foreground().color().name().upper()


# ------------------------------------------------------------------ fixtures
# Controlled units matching toolbox/tools/test_toolbox_alignment_check_page's
# _u shape -- the real DP aligner isn't coaxed into specific move types on
# demand here either; tests that need exact gap/QA tallies monkeypatch
# align_report.run, while the end-to-end test below uses real fixtures and
# only asserts terminal-state transitions.

def _units(total=0, gaps=0, flagged=0):
    from language_tools.model import TranslationUnit

    out = []
    for i in range(total - gaps):
        qa = ['NUMBER_MISMATCH'] if i < flagged else []
        out.append(TranslationUnit(
            src_lang='en-US', tgt_lang='zh-CN', src_text='s%d' % i, tgt_text='t%d' % i,
            meta={'align_move': '1:1', 'align_gap': False, 'qa_issues': qa}))
    for _ in range(gaps):
        out.append(TranslationUnit(
            src_lang='en-US', tgt_lang='zh-CN', src_text='g', tgt_text='',
            meta={'align_move': '1:0', 'align_gap': True, 'qa_issues': []}))
    return out


def _fake_run(results):
    """Stand-in for align_report.run() popping a prepared unit list per
    call, so a two-file batch can get two different controlled summaries.
    """
    calls = iter(results)
    return lambda *a, **k: next(calls)


# --------------------------------------------------------------- validation

def test_empty_list_shows_validation_error(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page.start_btn.click()
    assert '请先添加要检查的文件' in page.summary_label.text()


def test_missing_lang_shows_error(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._refresh_count()
    page.src_edit.setEditText('')
    page.start_btn.click()
    assert '原文语言和译文语言' in page.summary_label.text()


def test_adding_same_file_twice_does_not_duplicate(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('basic.docx'))
    page._append_path(fixture_path('basic.docx'))
    assert len(page._paths) == 1
    assert page.file_table.rowCount() == 1


# ------------------------------------------------------------------ running

def test_check_end_to_end_with_real_docx_fixtures(qtbot, tmp_path):
    a = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')
    b = shutil.copy(fixture_path('table_layout.docx'), tmp_path / 'table_layout.docx')
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path(str(a))
    page._append_path(str(b))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)

    for row in (0, 1):
        assert _status_text(page, row) not in ('等待中', '检查中…')
    assert '完成' in page.summary_label.text()
    # basic.docx aligns into 4 units (same count the single-file tool's
    # end-to-end test asserts) -- wording differs by outcome, the number
    # shouldn't.
    assert '共 4 条' in _status_text(page, 0) or '需检查：共 4 条' in _status_text(page, 0)


def test_missing_file_row_surfaces_error_in_red(qtbot, tmp_path):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path(str(tmp_path / 'nope.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert _status_text(page, 0).startswith('检查失败：')
    assert _status_color(page, 0) == '#B23B3B'


def test_needs_review_row_marked_red_clean_row_green(qtbot, monkeypatch):
    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.align_report.run',
        _fake_run([_units(total=5, gaps=2, flagged=1), _units(total=3)]))
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path('a.docx')
    page._append_path('b.docx')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert _status_text(page, 0) == '需检查：共 5 条，2 GAP，1 QA 标记'
    assert _status_color(page, 0) == '#B23B3B'
    assert _status_text(page, 1) == '共 3 条，全部对齐正常'
    assert _status_color(page, 1) == '#2F855A'
    assert '1 个需要人工看一眼' in page.summary_label.text()


def test_all_clean_logs_loud_confirmation(qtbot, monkeypatch):
    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.align_report.run',
        _fake_run([_units(total=3)]))
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path('a.docx')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert '全部对齐正常，没有发现问题' in page.summary_label.text()


# ------------------------------------------------------------------- export

def test_export_disabled_until_a_check_ran(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    assert not page.export_btn.isEnabled()


def test_export_summary_csv_one_row_per_file(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.align_report.run',
        _fake_run([_units(total=5, gaps=2, flagged=1), _units(total=3)]))
    out = tmp_path / 'summary.csv'
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path('a.docx')
    page._append_path('b.docx')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)
    assert page.export_btn.isEnabled()

    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()

    assert '汇总 CSV 已导出到' in page.summary_label.text()
    with open(out, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    assert rows[0] == ['file', 'units', 'gap_count', 'qa_flagged', 'status']
    assert rows[1][0] == os.path.join('a.docx') or rows[1][0] == 'a.docx'
    assert rows[1][1:] == ['5', '2', '1', '需检查：共 5 条，2 GAP，1 QA 标记']
    assert rows[2][1:] == ['3', '0', '0', '共 3 条，全部对齐正常']


def test_export_includes_failed_and_pending_rows(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.align_report.run',
        _fake_run([_units(total=3)]))
    out = tmp_path / 'summary.csv'
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path('a.docx')
    page._append_path('b.docx')  # only one run result prepared -> IndexError path
    # First file runs, then the second raises inside the worker's caught
    # Exception branch -> 检查失败 row; both terminal, export covers both.
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()

    with open(out, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3
    assert rows[1][1:] == ['3', '0', '0', '共 3 条，全部对齐正常']
    assert rows[2][1:4] == ['', '', '']  # failed row: no counts, status only
    assert rows[2][4].startswith('检查失败：')


# ------------------------------------------------------- completed-row drop

def test_adding_files_drops_previous_completed_rows(qtbot, monkeypatch):
    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.align_report.run',
        _fake_run([_units(total=3)]))
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path('a.docx')
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)
    assert page.file_table.rowCount() == 1

    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.QFileDialog.getOpenFileNames',
        staticmethod(lambda *a, **k: ([fixture_path('table_layout.docx')], '')),
    )
    page._add_files()
    # finished row dropped, only the fresh one remains -- re-running won't
    # silently redo a.docx (same contract as batch_convert).
    assert page.file_table.rowCount() == 1
    assert page._paths == [fixture_path('table_layout.docx')]


# ----------------------------------------------------------------- folder add

def test_add_folder_scans_recursively_and_skips_unsupported_files(qtbot, monkeypatch, tmp_path):
    sub = tmp_path / 'nested'
    sub.mkdir()
    shutil.copy(fixture_path('basic.docx'), tmp_path / 'a.docx')
    shutil.copy(fixture_path('table_layout.docx'), sub / 'b.docx')
    (tmp_path / 'notes.txt').write_text('not a supported format')
    (tmp_path / 'c.tmx').write_text('<tmx/>')  # corpus file: nothing to align

    monkeypatch.setattr(
        'toolbox.tools.batch_alignment_check.page.QFileDialog.getExistingDirectory',
        staticmethod(lambda *a, **k: str(tmp_path)))
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._add_folder()
    assert sorted(os.path.basename(p) for p in page._paths) == ['a.docx', 'b.docx']


# ------------------------------------------------------------------ settings

def test_restore_settings_defaults_when_nothing_saved_yet(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page.restore_settings()
    assert lang_combo_code(page.src_edit) == 'en-US'
    assert lang_combo_code(page.tgt_edit) == 'zh-CN'
    assert page.layout_combo.currentData() == 'auto'
    assert page._last_dir == ''


def test_save_then_restore_settings_round_trips(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page.src_edit.setEditText('ja-JP')
    page.tgt_edit.setEditText('ko-KR')
    idx = page.layout_combo.findData('table')
    page.layout_combo.setCurrentIndex(idx)
    page._last_dir = '/some/folder'
    page.save_settings()

    fresh = BatchAlignmentCheckPage()
    qtbot.addWidget(fresh)
    fresh.restore_settings()
    assert lang_combo_code(fresh.src_edit) == 'ja-JP'
    assert lang_combo_code(fresh.tgt_edit) == 'ko-KR'
    assert fresh.layout_combo.currentData() == 'table'
    assert fresh._last_dir == '/some/folder'
