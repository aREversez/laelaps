import csv
import os

from toolbox.tools.batch_preflight.page import BatchPreflightPage

from conftest import fixture_path


def _status_text(page, row):
    return page.file_table.item(row, 1).text()


def _status_color(page, row):
    # .name() lowercases ('#b23b3b'), LOG_COLORS is uppercase.
    return page.file_table.item(row, 1).foreground().color().name().upper()


# --------------------------------------------------------------- validation

def test_empty_list_shows_validation_error(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page.start_btn.click()
    assert '请先添加要预检的文件' in page.summary_label.text()


def test_adding_same_file_twice_does_not_duplicate(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout.docx'))
    page._append_path(fixture_path('table_layout.docx'))
    assert len(page._paths) == 1
    assert page.file_table.rowCount() == 1


# ------------------------------------------------------------------ running

def test_clean_file_marked_green_no_issues(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)

    assert '未发现问题' in _status_text(page, 0)
    assert _status_color(page, 0) == '#2F855A'
    assert '全部通过预检' in page.summary_label.text()


def test_reversed_direction_marked_red_with_issue_count(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout_reversed.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)

    assert '2 项问题' in _status_text(page, 0)
    assert _status_color(page, 0) == '#B23B3B'
    item = page.file_table.item(0, 1)
    assert '方向可能反了' in item.toolTip()
    assert '需要看一眼' in page.summary_label.text()


def test_merged_cells_and_empty_table_flagged(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_merged_header.docx'))
    page._append_path(fixture_path('table_with_empty_table.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)

    assert '1 项问题' in _status_text(page, 0)
    assert '1 项问题' in _status_text(page, 1)
    assert '完成' in page.summary_label.text()


def test_missing_file_row_surfaces_error_in_red(qtbot, tmp_path):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(str(tmp_path / 'nope.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert _status_text(page, 0).startswith('预检失败：')
    assert _status_color(page, 0) == '#B23B3B'


def test_non_docx_row_marked_red_and_skipped(qtbot, tmp_path):
    bad = tmp_path / 'in.csv'
    bad.write_text('a,b')
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(str(bad))  # bypasses the file-picker's .docx filter
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=5000)

    assert '仅支持 .docx' in _status_text(page, 0)
    assert _status_color(page, 0) == '#B23B3B'


# ------------------------------------------------------------------- export

def test_export_disabled_until_a_check_ran(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    assert not page.export_btn.isEnabled()


def test_export_summary_csv_one_row_per_file(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'summary.csv'
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout.docx'))
    page._append_path(fixture_path('table_layout_reversed.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)
    assert page.export_btn.isEnabled()

    monkeypatch.setattr(
        'toolbox.tools.batch_preflight.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()

    assert '汇总 CSV 已导出到' in page.summary_label.text()
    with open(out, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    assert rows[0] == ['file', 'best_layout', 'best_score', 'layout_ambiguous',
                        'merged_cell_count', 'empty_table_count',
                        'direction_issue_count', 'status']
    assert rows[1][1] == 'table'
    assert rows[1][5] == '0'  # empty_table_count for the clean file
    assert rows[2][6] == '2'  # direction_issue_count for the reversed file


def test_export_includes_failed_rows(qtbot, monkeypatch, tmp_path):
    out = tmp_path / 'summary.csv'
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout.docx'))
    page._append_path(str(tmp_path / 'nope.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)

    monkeypatch.setattr(
        'toolbox.tools.batch_preflight.page.QFileDialog.getSaveFileName',
        lambda *a, **k: (str(out), ''))
    page.export_btn.click()

    with open(out, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3
    assert rows[2][1:7] == ['', '', '', '', '', '']  # failed row: no counts
    assert rows[2][7].startswith('预检失败：')


# ------------------------------------------------------- completed-row drop

def test_adding_files_drops_previous_completed_rows(qtbot, monkeypatch):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(fixture_path('table_layout.docx'))
    page.start_btn.click()
    qtbot.waitUntil(lambda: page.start_btn.isEnabled(), timeout=15000)
    assert page.file_table.rowCount() == 1

    monkeypatch.setattr(
        'toolbox.tools.batch_preflight.page.QFileDialog.getOpenFileNames',
        staticmethod(lambda *a, **k: ([fixture_path('table_layout_reversed.docx')], '')),
    )
    page._add_files()
    assert page.file_table.rowCount() == 1
    assert os.path.basename(page._paths[0]) == 'table_layout_reversed.docx'
