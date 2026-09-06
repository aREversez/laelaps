import shutil

from toolbox.tools.corpus_convert.page import CorpusConvertPage

from conftest import fixture_path


def test_empty_input_shows_validation_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.convert_btn.click()
    assert '请先选择要转换的文件' in page.log.toPlainText()


def test_missing_lang_for_bilingual_source_shows_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(fixture_path('basic.docx'))
    page.src_edit.setText('')
    page.convert_btn.click()
    assert '原文语言和译文语言' in page.log.toPlainText()


def test_no_output_format_selected_shows_error(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(fixture_path('basic.docx'))
    page.chk_sdltm.setChecked(False)
    page.chk_tmx.setChecked(False)
    page.chk_csv.setChecked(False)
    page.convert_btn.click()
    assert '至少勾选一种要生成的格式' in page.log.toPlainText()


def test_layout_combo_shows_human_labels_but_passes_technical_value(qtbot):
    page = CorpusConvertPage()
    qtbot.addWidget(page)
    # display text is the friendly label...
    assert page.layout_combo.itemText(2) == '表格对照（一个两列表格，左边原文右边译文）'
    # ...but the value actually used by reader_opts is the technical string
    page.layout_combo.setCurrentIndex(2)
    assert page.layout_combo.currentData() == 'table'


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
    assert '转换完成' in log_text
    assert '出错了' not in log_text
    assert (tmp_path / 'basic.sdltm').exists()
    assert (tmp_path / 'basic.tmx').exists()
    assert (tmp_path / 'basic.csv').exists()


def test_partial_export_message_mentions_filtered_count(qtbot, tmp_path):
    src = shutil.copy(fixture_path('basic.docx'), tmp_path / 'basic.docx')

    page = CorpusConvertPage()
    qtbot.addWidget(page)
    page.input_edit.setText(str(src))
    page.src_edit.setText('en-US')
    page.tgt_edit.setText('zh-CN')
    page.chk_qa.setChecked(True)

    # force everything to be filtered out, to exercise the partial-export
    # message branch deterministically (bypasses the UI's normal kwargs
    # assembly since min_confidence isn't exposed as a control yet)
    from toolbox.tools.corpus_convert.page import ConvertWorker

    def _patched_start():
        assert page._validate() is None
        kwargs = dict(
            input_path=page.input_edit.text().strip(),
            output_base=str(tmp_path / 'basic'),
            src_lang='en-US', tgt_lang='zh-CN',
            formats=('csv',), reader_opts={}, qa=True, min_confidence=1.01,
        )
        page.convert_btn.setEnabled(False)
        page._worker = ConvertWorker(kwargs, parent=page)
        page._worker.finished_ok.connect(page._on_done)
        page._worker.finished_err.connect(page._on_error)
        page._worker.start()

    _patched_start()
    qtbot.waitUntil(lambda: page.convert_btn.isEnabled(), timeout=5000)
    log_text = page.log.toPlainText()
    assert '因质量问题被过滤' in log_text
