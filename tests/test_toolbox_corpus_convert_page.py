import shutil

from toolbox.tools.corpus_convert.page import CorpusConvertPage

from conftest import fixture_path


def test_empty_input_shows_validation_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.convert_btn.click()
    assert '请先选择输入文件' in page.log.toPlainText()


def test_missing_lang_for_bilingual_source_shows_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(fixture_path('basic.docx'))
    page.src_edit.setText('')
    page.convert_btn.click()
    assert '源/目标语言' in page.log.toPlainText()


def test_no_output_format_selected_shows_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(fixture_path('basic.docx'))
    page.chk_sdltm.setChecked(False)
    page.chk_tmx.setChecked(False)
    page.chk_csv.setChecked(False)
    page.convert_btn.click()
    assert '至少选择一个输出格式' in page.log.toPlainText()


def test_real_conversion_end_to_end(qtbot, tmp_path):
    src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.src_edit.setText('en-US')
    page.tgt_edit.setText('zh-CN')

    page.convert_btn.click()
    # ConvertWorker runs on a real QThread; poll until it re-enables the
    # button (both the success and error handlers do this).
    qtbot.waitUntil(lambda: page.convert_btn.isEnabled(), timeout=5000)

    log_text = page.log.toPlainText()
    assert '完成' in log_text
    assert '错误' not in log_text
    assert (tmp_path / 'basic.sdltm').exists()
    assert (tmp_path / 'basic.tmx').exists()
    assert (tmp_path / 'basic.csv').exists()
