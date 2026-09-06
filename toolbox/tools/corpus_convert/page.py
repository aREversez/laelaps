"""The corpus-conversion tool's page: a form wrapping
``language_tools.api.convert()`` directly (no HTTP layer -- this is a
native desktop app, the GUI just imports and calls the library).

Conversion runs in a QThread (``ConvertWorker``) so the UI doesn't freeze
on larger files; results/errors come back via Qt signals.

Copy guidelines for this page (and for any future tool page -- keep this
consistent): write for someone glancing at the screen, not someone
reading documentation. Prefer "翻译记忆库" (the term CAT-tool users
actually use daily) over "语料库格式" (a linguistics/computational term
that's technically accurate but not what a translator recognizes at a
glance).

Explanation belongs in a tooltip on the relevant control, not as
permanently-visible text -- an earlier version put a full explanatory
sentence under every section title and it made the page "眼花缭乱" (busy/
overwhelming) even though every individual sentence was fine on its own.
Default view stays compact (short labels only); hovering a field/checkbox/
dropdown item reveals detail via .setToolTip() (or, for QComboBox items,
Qt.ToolTipRole via setItemData). Enum-like choices (docx layout) get
short human-readable labels in the visible list while the underlying
value passed to the library stays the technical string
(QComboBox.addItem(display_text, value) + .currentData()).
"""
import html
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from language_tools import api

_BILINGUAL_EXTS = {'.docx', '.xlsx', '.xlsm', '.csv', '.tsv'}
_SUPPORTED_FILTER = 'Supported files (*.docx *.xlsx *.xlsm *.csv *.tsv *.tmx *.sdltm)'

_LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

# (short label shown in the dropdown, technical value passed to the library, tooltip detail)
_LAYOUT_CHOICES = [
    ('自动识别（推荐）', 'auto', '系统自己判断用哪种版式；识别错了再手动指定其他选项。'),
    ('编号分段', 'numbered', '先列出全部原文段落，再列出全部译文段落，编号各自从 1 开始。'),
    ('表格对照', 'table', '一个两列表格，左边原文右边译文，一行一句。'),
    ('逐段对照', 'alternating', '一段原文后面紧跟着一段译文，这样交替排列。'),
]

_LANG_TOOLTIP = ('双语文档（docx/xlsx/csv）必须填写；如果选的是翻译记忆库文件（tmx/sdltm），'
                 '留空即可，系统会自动从文件里识别。')
_QA_TOOLTIP = '检查有没有漏译、数字对不上这类明显问题，结果会记在 csv 里。'
_FORMAT_TOOLTIPS = {
    'sdltm': 'Trados 用的翻译记忆库格式。',
    'tmx': '各家 CAT 工具通用的翻译记忆库格式。',
    'csv': '方便人工打开核对的表格。',
}


def _section(title, content_widget):
    """A section header (label + hairline rule) above a content widget --
    used instead of QGroupBox, whose native chrome can't be made to look
    clean via QSS alone. Shared shape for every section on this page; a
    future tool page should follow the same pattern for visual consistency.
    """
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label = QLabel(title)
    label.setProperty('role', 'sectionTitle')
    layout.addWidget(label)

    rule = QFrame()
    rule.setProperty('role', 'hairline')
    layout.addWidget(rule)

    layout.addWidget(content_widget)
    return wrapper


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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel('语料转换')
        title.setStyleSheet('font-size: 20px; font-weight: 600;')
        outer.addWidget(title)
        subtitle = QLabel(
            '把双语对照的 Word/Excel/表格文档，转换成 Trados 等 CAT 工具能用的翻译记忆库；'
            '也可以在两种记忆库格式之间互相转换。')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet('color: #6B7280;')
        outer.addWidget(subtitle)

        # --- file ---
        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('选择要转换的文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_input)
        file_layout.addWidget(self.input_edit, 1)
        file_layout.addWidget(browse_btn)
        outer.addWidget(_section('第一步：选择文件', file_row))

        # --- language ---
        lang_widget = QWidget()
        lang_form = QFormLayout(lang_widget)
        lang_form.setContentsMargins(0, 0, 0, 0)
        self.src_edit = QLineEdit('en-US')
        self.tgt_edit = QLineEdit('zh-CN')
        self.src_edit.setToolTip(_LANG_TOOLTIP)
        self.tgt_edit.setToolTip(_LANG_TOOLTIP)
        lang_form.addRow('原文语言', self.src_edit)
        lang_form.addRow('译文语言', self.tgt_edit)
        outer.addWidget(_section('第二步：确认语言', lang_widget))

        # --- docx layout ---
        layout_widget = QWidget()
        layout_form = QFormLayout(layout_widget)
        layout_form.setContentsMargins(0, 0, 0, 0)
        self.layout_combo = QComboBox()
        self.layout_combo.setToolTip('文档是 Word (.docx) 时才需要关心这个选项。')
        for i, (display_text, value, item_tip) in enumerate(_LAYOUT_CHOICES):
            self.layout_combo.addItem(display_text, value)
            self.layout_combo.setItemData(i, item_tip, Qt.ToolTipRole)
        layout_form.addRow('文档排版方式', self.layout_combo)
        outer.addWidget(_section('文档排版方式', layout_widget))

        # --- output formats ---
        fmt_widget = QWidget()
        fmt_row = QHBoxLayout(fmt_widget)
        fmt_row.setContentsMargins(0, 0, 0, 0)
        self.chk_sdltm = QCheckBox('sdltm')
        self.chk_tmx = QCheckBox('tmx')
        self.chk_csv = QCheckBox('csv')
        for cb, key in ((self.chk_sdltm, 'sdltm'), (self.chk_tmx, 'tmx'), (self.chk_csv, 'csv')):
            cb.setChecked(True)
            cb.setToolTip(_FORMAT_TOOLTIPS[key])
            fmt_row.addWidget(cb)
        fmt_row.addStretch(1)
        outer.addWidget(_section('第三步：要生成哪些格式', fmt_widget))

        self.chk_qa = QCheckBox('运行内容检查')
        self.chk_qa.setToolTip(_QA_TOOLTIP)
        outer.addWidget(self.chk_qa)

        self.convert_btn = QPushButton('开始转换')
        self.convert_btn.setObjectName('primaryButton')
        self.convert_btn.clicked.connect(self._start_convert)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.convert_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setPlaceholderText('转换结果会显示在这里')
        outer.addWidget(self.log, 1)

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = _LOG_COLORS.get(kind, _LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))

    # ------------------------------------------------------------ actions
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', _SUPPORTED_FILTER)
        if path:
            self.input_edit.setText(path)

    def _validate(self):
        """Returns an error string, or None if the form is valid."""
        input_path = self.input_edit.text().strip()
        if not input_path:
            return '请先选择要转换的文件'
        if not os.path.exists(input_path):
            return '找不到这个文件，请重新选择'

        ext = os.path.splitext(input_path)[1].lower()
        if ext in _BILINGUAL_EXTS and (not self.src_edit.text().strip() or not self.tgt_edit.text().strip()):
            return '这类文件需要先填写原文语言和译文语言，才能开始转换'

        if not any(cb.isChecked() for cb in (self.chk_sdltm, self.chk_tmx, self.chk_csv)):
            return '请至少勾选一种要生成的格式'
        return None

    def _start_convert(self):
        error = self._validate()
        if error:
            self._log(error, 'error')
            return

        input_path = self.input_edit.text().strip()
        ext = os.path.splitext(input_path)[1].lower()
        formats = tuple(f for f, cb in (
            ('sdltm', self.chk_sdltm), ('tmx', self.chk_tmx), ('csv', self.chk_csv)) if cb.isChecked())
        reader_opts = {}
        if ext == '.docx' and self.layout_combo.currentData() != 'auto':
            reader_opts['layout'] = self.layout_combo.currentData()

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
        self._log('正在转换…')
        self._worker = ConvertWorker(kwargs, parent=self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result):
        self.convert_btn.setEnabled(True)
        units, exported = result['units'], result['exported']
        if exported == units:
            self._log('转换完成！共对齐 %d 组双语句子，全部导出。' % units, 'success')
        else:
            self._log(
                '转换完成：共对齐 %d 组，其中 %d 组导出，%d 组因质量问题被过滤（在 csv 里能看到详情）。'
                % (units, exported, units - exported), 'success')
        for fmt, count in result['written'].items():
            self._log('· 生成了 %s 文件，共 %d 条' % (fmt, count))

    def _on_error(self, message):
        self.convert_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')
