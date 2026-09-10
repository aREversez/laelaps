"""Small shared UI helpers used by more than one tool page.

``section()`` started as a private copy in ``corpus_convert/page.py``,
then got a second private copy in ``tm_maintenance/page.py`` (that
file's docstring said explicitly: two copies is a coincidence, not yet a
pattern -- wait for a clearer signal before sharing). ``qa_check`` is the
third tool wanting the identical helper, which is that clearer signal:
promoted here now, with both existing call sites switched over to import
it instead of keeping their own copies.

``LANG_CHOICES``/``make_lang_combo()``/``lang_combo_code()`` and
``LAYOUT_CHOICES`` followed the same path: private to
``corpus_convert/page.py`` until ``alignment_check`` needed the identical
"pick a bilingual source, tell it src/tgt language and (for .docx) which
layout" form controls -- aligning a document needs exactly the same
language/layout inputs as converting one, so duplicating that logic for a
second page would just be two copies of the same combo box drifting
apart over time.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QVBoxLayout, QWidget


def section(title, content_widget):
    """A section header (label + hairline rule) above a content widget --
    used instead of QGroupBox, whose native chrome can't be made to look
    clean via QSS alone. Every tool page should use this for section
    headers, for visual consistency across the toolbox.
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


# (display label, language code) -- common pairs, prefilled into an
# editable combobox so most users just pick from the list instead of
# typing a BCP-47 code by hand. Editable so an uncommon pair can still be
# typed in directly; the underlying value a caller should use is always
# whatever's in the edit field (via lang_combo_code()), not a fixed list.
LANG_CHOICES = [
    ('英语 (en-US)', 'en-US'),
    ('英语-英国 (en-GB)', 'en-GB'),
    ('简体中文 (zh-CN)', 'zh-CN'),
    ('繁体中文 (zh-TW)', 'zh-TW'),
    ('日语 (ja-JP)', 'ja-JP'),
    ('韩语 (ko-KR)', 'ko-KR'),
    ('法语 (fr-FR)', 'fr-FR'),
    ('德语 (de-DE)', 'de-DE'),
    ('西班牙语 (es-ES)', 'es-ES'),
    ('葡萄牙语 (pt-PT)', 'pt-PT'),
    ('意大利语 (it-IT)', 'it-IT'),
    ('俄语 (ru-RU)', 'ru-RU'),
    ('阿拉伯语 (ar-SA)', 'ar-SA'),
]

LANG_TOOLTIP = '双语文档必填；tmx/sdltm 留空会自动识别。可直接选，也可以手动输入其它语言代码'

# (short label shown in the dropdown, technical value passed to the
# library, tooltip detail) -- only meaningful for .docx input; readers for
# other bilingual formats ignore a 'layout' reader_opt if given one.
LAYOUT_CHOICES = [
    ('自动识别（推荐）', 'auto', '自动判断版式，错了再手动选'),
    ('编号分段', 'numbered', '先列全部原文段落，再列全部译文段落'),
    ('表格对照', 'table', '两列表格，左边原文右边译文'),
    ('逐段对照', 'alternating', '原文译文逐段交替排列'),
]


def make_lang_combo(default_code):
    """An editable QComboBox prefilled with common language pairs
    (``LANG_CHOICES``) but that still accepts a freely typed code --
    picking from the list is the common case, typing stays available for
    anything not in the preset list.
    """
    combo = QComboBox()
    combo.setEditable(True)
    for display_text, code in LANG_CHOICES:
        combo.addItem(display_text, code)
    idx = combo.findData(default_code)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    else:
        combo.setCurrentText(default_code)
    return combo


def lang_combo_code(combo):
    """The language code a lang combo currently represents: the preset's
    code if the current text matches one of the dropdown's display labels
    (selected from the list, not retyped), otherwise the typed text as-is
    (freeform code entry).
    """
    idx = combo.findText(combo.currentText())
    if idx >= 0:
        return combo.itemData(idx)
    return combo.currentText().strip()


def make_layout_combo():
    """A QComboBox populated from ``LAYOUT_CHOICES`` with per-item
    tooltips already wired up (``Qt.ToolTipRole``).
    """
    combo = QComboBox()
    for i, (display_text, value, item_tip) in enumerate(LAYOUT_CHOICES):
        combo.addItem(display_text, value)
        combo.setItemData(i, item_tip, Qt.ToolTipRole)
    return combo
