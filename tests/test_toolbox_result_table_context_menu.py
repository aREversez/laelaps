"""结果表格右键"复制"菜单的回归测试（DESIGN.md 15.4 P1-c）。

菜单动作本身（QMenu.exec）依赖真实屏幕坐标，offscreen 下不可靠；这里直接
验证菜单背后的复制辅助方法（把可见列文本 / 原文 / 译文写进系统剪贴板），
并断言四张遗漏表格都按现有模式接线了自定义右键菜单
（setContextMenuPolicy + customContextMenuRequested）。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from toolbox.tools.alignment_check.page import AlignmentCheckPage
from toolbox.tools.batch_alignment_check.page import BatchAlignmentCheckPage
from toolbox.tools.batch_preflight.page import BatchPreflightPage
from toolbox.tools.qa_check.page import QaCheckPage


def _menu_is_wired(page, table):
    return (table.contextMenuPolicy() == Qt.CustomContextMenu
            and callable(getattr(page, '_show_entry_context_menu', None)))


# ------------------------------------------------------------------ qa_check

def test_qa_check_table_has_context_menu_wired(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    assert _menu_is_wired(page, page.results_table)


def test_qa_check_copies_row_and_cells_from_displayed_model(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    # 高亮/wrap 态下 原文/译文列是 cellWidget，item() 取不到文本，菜单从
    # _displayed_rows 快照读——这里直接填快照验证，无需真跑一次 QA。
    page._displayed_rows = [['1', 'Hello world', '你好世界', '漏译', '0.90']]

    QApplication.clipboard().setText('')
    page._copy_entry_row(0)
    assert QApplication.clipboard().text() == '1\tHello world\t你好世界\t漏译\t0.90'

    QApplication.clipboard().setText('')
    page._copy_entry_cell(0, 1)
    assert QApplication.clipboard().text() == 'Hello world'

    QApplication.clipboard().setText('')
    page._copy_entry_cell(0, 2)
    assert QApplication.clipboard().text() == '你好世界'


def test_qa_check_copy_out_of_range_is_noop(qtbot):
    page = QaCheckPage()
    qtbot.addWidget(page)
    page._displayed_rows = []
    QApplication.clipboard().setText('sentinel')
    page._copy_entry_row(0)
    assert QApplication.clipboard().text() == 'sentinel'


# ------------------------------------------------------------ alignment_check

def test_alignment_check_table_has_context_menu_wired(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    assert _menu_is_wired(page, page.results_table)


def test_alignment_check_copies_row_and_src_tgt(qtbot):
    page = AlignmentCheckPage()
    qtbot.addWidget(page)
    page.results_table.setRowCount(1)
    for col, text in enumerate(['P1', 'Hello', '你好', '一一对应', '0.00', '-']):
        page.results_table.setItem(0, col, QTableWidgetItem(text))

    QApplication.clipboard().setText('')
    page._copy_entry_row(0)
    assert QApplication.clipboard().text() == 'P1\tHello\t你好\t一一对应\t0.00\t-'

    QApplication.clipboard().setText('')
    page._copy_entry_cell(0, 1)
    assert QApplication.clipboard().text() == 'Hello'


# ------------------------------------------------------ batch_alignment_check

def test_batch_alignment_check_table_has_context_menu_wired(qtbot):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    assert _menu_is_wired(page, page.file_table)


def test_batch_alignment_check_copies_selected_rows(qtbot, tmp_path):
    page = BatchAlignmentCheckPage()
    qtbot.addWidget(page)
    page._append_path(str(tmp_path / 'a.docx'))
    page._append_path(str(tmp_path / 'b.docx'))

    QApplication.clipboard().setText('')
    page._copy_rows([0])
    assert QApplication.clipboard().text().startswith('a.docx')

    QApplication.clipboard().setText('')
    page._copy_rows([0, 1])
    lines = QApplication.clipboard().text().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith('a.docx')
    assert lines[1].startswith('b.docx')


# ------------------------------------------------------------ batch_preflight

def test_batch_preflight_table_has_context_menu_wired(qtbot):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    assert _menu_is_wired(page, page.file_table)


def test_batch_preflight_copies_row(qtbot, tmp_path):
    page = BatchPreflightPage()
    qtbot.addWidget(page)
    page._append_path(str(tmp_path / 'doc.docx'))

    QApplication.clipboard().setText('')
    page._copy_rows([0])
    assert QApplication.clipboard().text().startswith('doc.docx')
