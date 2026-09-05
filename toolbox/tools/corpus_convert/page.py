"""The corpus-conversion tool's page: a form wrapping
``language_tools.api.convert()`` directly (no HTTP layer -- this is a
native desktop app, the GUI just imports and calls the library).

Conversion runs in a QThread (``ConvertWorker``) so the UI doesn't freeze
on larger files; results/errors come back via Qt signals.
"""
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from language_tools import api

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}
_SUPPORTED_FILTER = 'Supported files (*.docx *.xlsx *.xlsm *.csv *.tsv *.tmx *.sdltm)'


class ConvertWorker(QThread):
    """Runs api.convert() off the UI thread. One-shot, not reused."""
    finished_ok = Signal(dict)
    finished_err = Signal(str)

    def __init__(self, convert_kwargs, parent=None):
        super().__init__(parent)
        self._kwargs = convert_kwargs

    def run(self):
        try:
            result = api.convert(**self._kwargs)
        except Exception as e:  # noqa: BLE001 -- surfaced to the user, not swallowed
            self.finished_err.emit(str(e))
            return
        self.finished_ok.emit(result)


class CorpusConvertPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('选择要转换的文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_input)
        file_row.addWidget(self.input_edit)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        lang_group = QGroupBox('语言（双语源文件必填；语料库文件可留空，自动识别）')
        lang_form = QFormLayout(lang_group)
        self.src_edit = QLineEdit('en-US')
        self.tgt_edit = QLineEdit('zh-CN')
        lang_form.addRow('源语言', self.src_edit)
        lang_form.addRow('目标语言', self.tgt_edit)
        layout.addWidget(lang_group)

        layout_group = QGroupBox('docx 版式（仅 docx 输入时生效）')
        layout_form = QFormLayout(layout_group)
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(['auto', 'numbered', 'table', 'alternating'])
        layout_form.addRow('版式', self.layout_combo)
        layout.addWidget(layout_group)

        fmt_group = QGroupBox('输出格式')
        fmt_row = QHBoxLayout(fmt_group)
        self.chk_sdltm = QCheckBox('sdltm')
        self.chk_tmx = QCheckBox('tmx')
        self.chk_csv = QCheckBox('csv')
        for cb in (self.chk_sdltm, self.chk_tmx, self.chk_csv):
            cb.setChecked(True)
            fmt_row.addWidget(cb)
        layout.addWidget(fmt_group)

        self.chk_qa = QCheckBox('运行 QA 检查（csv 增加 confidence/status/issues 列）')
        layout.addWidget(self.chk_qa)

        self.convert_btn = QPushButton('转换')
        self.convert_btn.clicked.connect(self._start_convert)
        layout.addWidget(self.convert_btn)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

    # ------------------------------------------------------------ actions
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _SUPPORTED_FILTER)
        if path:
            self.input_edit.setText(path)

    def _validate(self):
        """Returns an error string, or None if the form is valid."""
        input_path = self.input_edit.text().strip()
        if not input_path:
            return '请先选择输入文件'
        if not os.path.exists(input_path):
            return '文件不存在: %s' % input_path

        ext = os.path.splitext(input_path)[1].lower()
        if ext in _BILINGUAL_EXTS and (not self.src_edit.text().strip() or not self.tgt_edit.text().strip()):
            return '该输入格式（%s）需要填写源/目标语言' % ext

        if not any(cb.isChecked() for cb in (self.chk_sdltm, self.chk_tmx, self.chk_csv)):
            return '至少选择一个输出格式'
        return None

    def _start_convert(self):
        error = self._validate()
        if error:
            self.log.appendPlainText('错误：%s' % error)
            return

        input_path = self.input_edit.text().strip()
        ext = os.path.splitext(input_path)[1].lower()
        formats = tuple(f for f, cb in (
            ('sdltm', self.chk_sdltm), ('tmx', self.chk_tmx), ('csv', self.chk_csv)) if cb.isChecked())
        reader_opts = {}
        if ext == '.docx' and self.layout_combo.currentText() != 'auto':
            reader_opts['layout'] = self.layout_combo.currentText()

        kwargs = dict(
            input_path=input_path,
            output_base=os.path.splitext(input_path)[0],
            src_lang=self.src_edit.text().strip() or None,
            tgt_lang=self.tgt_edit.text().strip() or None,
            formats=formats,
            reader_opts=reader_opts,
            qa=self.chk_qa.isChecked(),
        )

        self.convert_btn.setEnabled(False)
        self.log.appendPlainText('正在转换…')
        self._worker = ConvertWorker(kwargs, parent=self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result):
        self.convert_btn.setEnabled(True)
        self.log.appendPlainText(
            '完成：units=%d exported=%d ratio=%.3f' %
            (result['units'], result['exported'], result['length_ratio']))
        for fmt, count in result['written'].items():
            self.log.appendPlainText('  写入 .%s（%d 条）' % (fmt, count))

    def _on_error(self, message):
        self.convert_btn.setEnabled(True)
        self.log.appendPlainText('错误：%s' % message)
