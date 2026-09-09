from PySide6.QtCore import Qt

from language_tools.corpus_readers import tmx_reader
from language_tools.model import TranslationUnit
from language_tools.writers import tmx_writer
from toolbox.tools.tm_maintenance.page import TmMaintenancePage


def _u(src, tgt, **kw):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt, **kw)


def _write_tmx(path, units):
    tmx_writer.write(str(path), units, 'en-US', 'zh-CN')


# ------------------------------------------------------------------ clean

def test_clean_empty_input_shows_validation_error(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.clean_btn.click()
    assert '请先选择要清理的文件' in page.log.toPlainText()


def test_clean_no_options_checked_shows_validation_error(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好')])
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.clean_input_edit.setText(str(src))
    for cb in (page.clean_chk_normalize, page.clean_chk_dedupe,
               page.clean_chk_remove_empty, page.clean_chk_remove_identical):
        cb.setChecked(False)
    page.clean_btn.click()
    assert '至少勾选一项清理选项' in page.log.toPlainText()


def test_clean_end_to_end_overwrites_input_by_default(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好'), _u('Bye', '再见')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.clean_input_edit.setText(str(src))
    page.clean_btn.click()
    qtbot.waitUntil(lambda: page.clean_btn.isEnabled(), timeout=5000)

    log_text = page.log.toPlainText()
    assert '清理完成' in log_text
    assert '出错了' not in log_text
    units = tmx_reader.read(str(src))
    assert len(units) == 2


def test_clean_end_to_end_saves_to_output_path_when_given(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    out = tmp_path / 'out.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.clean_input_edit.setText(str(src))
    page.clean_output_edit.setText(str(out))
    page.clean_btn.click()
    qtbot.waitUntil(lambda: page.clean_btn.isEnabled(), timeout=5000)

    assert out.exists()
    assert len(tmx_reader.read(str(src))) == 2  # input untouched
    assert len(tmx_reader.read(str(out))) == 1  # deduped output


# ------------------------------------------------------------------ merge

def test_merge_no_files_shows_validation_error(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_btn.click()
    assert '请先添加要合并的文件' in page.log.toPlainText()


def test_merge_no_output_shows_validation_error(qtbot, tmp_path):
    src = tmp_path / 'a.tmx'
    _write_tmx(src, [_u('Hello', '你好')])
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_list.addItem(str(src))
    page.merge_btn.click()
    assert '请指定合并结果的保存位置' in page.log.toPlainText()


def test_merge_remove_selected_removes_only_selected_items(qtbot, tmp_path):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_list.addItem('a.tmx')
    page.merge_list.addItem('b.tmx')
    page.merge_list.item(0).setSelected(True)
    page.merge_remove_btn.click()
    assert page.merge_list.count() == 1
    assert page.merge_list.item(0).text() == 'b.tmx'


def test_merge_clear_empties_the_list(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_list.addItem('a.tmx')
    page.merge_list.addItem('b.tmx')
    page.merge_clear_btn.click()
    assert page.merge_list.count() == 0


def test_merge_strategy_combo_shows_short_labels_but_passes_technical_value(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    assert page.merge_strategy_combo.itemText(2) == '保留后出现的'
    page.merge_strategy_combo.setCurrentIndex(2)
    assert page.merge_strategy_combo.currentData() == 'prefer-last'


def test_merge_strategy_combo_items_have_detail_tooltips(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    for i in range(page.merge_strategy_combo.count()):
        tip = page.merge_strategy_combo.itemData(i, Qt.ToolTipRole)
        assert tip, 'strategy option %d has no tooltip' % i


def test_merge_end_to_end_keep_all(qtbot, tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    out = tmp_path / 'merged.tmx'
    _write_tmx(a, [_u('Hello', '你好')])
    _write_tmx(b, [_u('Bye', '再见')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_list.addItem(str(a))
    page.merge_list.addItem(str(b))
    page.merge_output_edit.setText(str(out))
    page.merge_btn.click()
    qtbot.waitUntil(lambda: page.merge_btn.isEnabled(), timeout=5000)

    log_text = page.log.toPlainText()
    assert '合并完成' in log_text
    assert '出错了' not in log_text
    assert len(tmx_reader.read(str(out))) == 2


def test_merge_end_to_end_prefer_last_resolves_conflict(qtbot, tmp_path):
    a = tmp_path / 'a.tmx'
    b = tmp_path / 'b.tmx'
    out = tmp_path / 'merged.tmx'
    _write_tmx(a, [_u('Ready', '已就绪')])
    _write_tmx(b, [_u('Ready', '准备好了')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.merge_list.addItem(str(a))
    page.merge_list.addItem(str(b))
    page.merge_output_edit.setText(str(out))
    page.merge_strategy_combo.setCurrentIndex(2)  # prefer-last
    page.merge_btn.click()
    qtbot.waitUntil(lambda: page.merge_btn.isEnabled(), timeout=5000)

    units = tmx_reader.read(str(out))
    assert len(units) == 1
    assert units[0].tgt_text == '准备好了'


# ------------------------------------------------------------------ stats

def test_stats_empty_input_shows_validation_error(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.stats_btn.click()
    assert '请先选择要查看统计的文件' in page.log.toPlainText()


def test_stats_end_to_end(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好'), _u('Hello', '你好'), _u('Bye', '再见')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.stats_input_edit.setText(str(src))
    page.stats_btn.click()
    qtbot.waitUntil(lambda: page.stats_btn.isEnabled(), timeout=5000)

    assert '统计完成' in page.log.toPlainText()

    def _table_rows():
        return {page.stats_table.item(r, 0).text(): page.stats_table.item(r, 1).text()
                for r in range(page.stats_table.rowCount())}

    rows = _table_rows()
    assert rows['总条数'] == '3'
    assert rows['去重后条数'] == '2'
    assert '语言对 en-US-zh-CN' in rows
    assert rows['语言对 en-US-zh-CN'] == '3 条'


def test_stats_table_is_cleared_before_a_new_run(qtbot, tmp_path):
    src = tmp_path / 'in.tmx'
    _write_tmx(src, [_u('Hello', '你好')])

    page = TmMaintenancePage()
    qtbot.addWidget(page)
    page.stats_input_edit.setText(str(src))
    page.stats_btn.click()
    qtbot.waitUntil(lambda: page.stats_btn.isEnabled(), timeout=5000)
    assert page.stats_table.rowCount() > 0

    # Clicking again with no valid input (file removed) shouldn't leave
    # stale results from the previous successful run sitting in the table.
    src.unlink()
    page.stats_btn.click()
    qtbot.waitUntil(lambda: page.stats_btn.isEnabled(), timeout=5000)
    assert page.stats_table.rowCount() == 0


def test_stats_table_header_left_aligned_to_match_item_content(qtbot):
    # Header text used to default to centered while item text defaults to
    # left -- with the value column stretched wide, that mismatch looked
    # inconsistent. Both should now agree.
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    alignment = page.stats_table.horizontalHeader().defaultAlignment()
    assert alignment & Qt.AlignLeft


# ------------------------------------------------------------------ shared

def test_clean_option_checkboxes_have_tooltips(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    assert page.clean_chk_normalize.toolTip()
    assert page.clean_chk_dedupe.toolTip()
    assert page.clean_chk_remove_empty.toolTip()
    assert page.clean_chk_remove_identical.toolTip()


def test_tabs_present_for_all_three_actions(qtbot):
    page = TmMaintenancePage()
    qtbot.addWidget(page)
    titles = [page.tabs.tabText(i) for i in range(page.tabs.count())]
    assert titles == ['清理', '合并', '统计']
