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

``compact_combo()``/``labeled_field()`` followed the same path again:
``alignment_check`` introduced them (to lay 原文语言/译文语言/文档排版方式
out inline in one row instead of three stacked full-width QFormLayout
rows), ``tm_maintenance`` got a second private copy for its own
保存到/冲突处理策略 row, and ``corpus_convert`` -- whose 语言/排版方式
inputs are the exact ones ``alignment_check`` copied the pattern from in
the first place -- is the third, so promoted here now with all three call
sites switched over.

``LOG_COLORS`` is the same story, several times over: ``corpus_convert``,
``qa_check``, ``tm_maintenance``, ``alignment_check``, and
``term_management`` had each independently grown their own identical
``_LOG_COLORS = {'info': ..., 'error': ..., 'success': ...}`` for their
append-only result log's text color -- five private copies of the same
three hex codes, well past the "third call site" signal, so promoted
here now with every call site switched over.

``CORPUS_FILTER`` (the ``'Corpus files (*.tmx *.sdltm)'`` string passed
to ``QFileDialog.getOpenFileName``/``getOpenFileNames`` whenever a tool
picks an existing tmx/sdltm) is the same pattern a fourth time:
``qa_check``, ``term_management``, and ``tm_maintenance`` each had their
own private ``_CORPUS_FILTER`` copy already -- three, right at the
promotion line -- and ``tm_editor`` needing the identical string as its
fourth independent copy is what actually triggered doing it.

``page_shell()`` is the shared page skeleton every tool page's
``_build_ui()`` starts from (2026-09 UI modernization round): the
ad-hoc ``outer = QVBoxLayout(self)`` + inline-styled title/subtitle
labels that all nine pages had individually grown are replaced by one
header (objectName-styled, no more per-page hex codes) above a single
white content card inside a ``QScrollArea``, with the page's one light
elevation shadow applied here so no tool page reaches for
``QGraphicsDropShadowEffect`` itself -- per DESIGN.md §13, shadows are
reserved for this card and the home-page tiles, nothing else. Takes the
calling page's ``self`` explicitly (``page_shell(self, title, subtitle)``)
rather than inferring it by walking the call stack for a QWidget-typed
local named ``self`` -- an earlier version did that, and it happened to
work for every call site that existed at the time, but nothing about it
was actually guaranteed to find the right widget once a page was built
from a nested helper or while another widget's own ``__init__`` was still
on the stack.
"""
import os

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)


# Shared by every tool page's append-only result log (and, from
# batch_convert onward, per-row status text too): gray for a neutral
# progress note, red for a failure, green for a success.
LOG_COLORS = {'info': '#6B7280', 'error': '#B23B3B', 'success': '#2F855A'}

# Shared by every tool page's "open an existing tmx/sdltm" file dialog.
CORPUS_FILTER = 'Corpus files (*.tmx *.sdltm)'


def section(title, content_widget):
    """A self-contained section *card*: a soft tinted, rounded panel holding
    a small title (with an indigo left accent bar) above its content.

    The 2026-09 layout rounds first tried flat sections separated by a
    full-width hairline, then a faint tint on the tab pane -- both read as
    "no change" because a hairline and a near-white tint are too subtle to
    create figure-ground. This is the decisive version: every section is
    now a distinct block (``#sectionCard`` in style.qss, a light cool-gray
    on the white page card), so a page reads as a set of grouped panels
    rather than one long stack of identical full-width rows. The tint is
    flat + hairline only -- no shadow (DESIGN.md §13 reserves shadow for
    the page card and home tiles).

    The ``role="hairline"`` frame is kept in the structure (rendered at
    height 0) so the QSS contract and any structural inspection still see
    one consistent wrapper shape.
    """
    card = QWidget()
    card.setObjectName('sectionCard')
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)

    label = QLabel(title)
    label.setProperty('role', 'sectionTitle')
    layout.addWidget(label)

    rule = QFrame()
    rule.setProperty('role', 'hairline')
    layout.addWidget(rule)

    layout.addWidget(content_widget)
    return card


def columns(*cards, spacing=16):
    """Lay a handful of ``section()`` cards out side by side as one row of
    equal-width columns -- the two-column reflow that breaks the "every
    field is its own full-width band" spreadsheet rhythm. Short related
    inputs (e.g. 选择文件 / 输出到) become a compact cluster instead of two
    stacked rows, and the card framing makes the grouping read at a glance.

    Each card gets equal stretch, so they share the row width evenly; on a
    narrow window the surrounding ``page_shell`` scroll area's horizontal
    bar (ScrollBarAsNeeded) keeps the row's minimum width reachable.
    """
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for card in cards:
        layout.addWidget(card, 1)
    return row


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


def set_lang_combo_code(combo, code):
    """Selects the ``LANG_CHOICES`` entry matching ``code`` if there is
    one, otherwise types ``code`` in directly (freeform entry) -- the
    same "prefer a matching preset, fall back to as-typed" rule
    ``make_lang_combo()`` uses for its own initial default. Pulled out
    on its own so ``toolbox/settings.py``-backed restore_settings()
    hooks can reapply a saved code the same way, without duplicating
    this matching logic per tool page.
    """
    idx = combo.findData(code)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    else:
        combo.setCurrentText(code)


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
    set_lang_combo_code(combo, default_code)
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


# QComboBox chrome reserved by style.qss's QComboBox/QComboBox::drop-down
# rules (padding: 6px 8px, 1px border each side, 26px drop-down arrow),
# plus a small safety margin. AdjustToContents' own sizeHint() doesn't
# reliably add this back once a style sheet is in play -- see
# compact_combo()'s docstring for what that looked like on real Windows.
_COMBO_STYLESHEET_CHROME_PX = 56


def compact_combo(combo):
    """Makes a combo box's width track its actual content instead of
    whatever the surrounding layout hands it. Without this, a combo whose
    longest item is a handful of characters (e.g. "自动识别（推荐）") ends
    up stretched to hundreds of pixels wide the moment it's the field in a
    QFormLayout row (that layout's default field-growth policy stretches
    the field column to the row's full width regardless of the widget's
    own size hint) -- which is why controls like this used to look so
    oversized for how little text is in them. AdjustToContents recomputes
    the width whenever the current item/text changes, so it stays
    correctly sized as the user picks a different option, not just on
    first show.

    Real Windows testing surfaced a second problem this alone doesn't
    fix: with this app's style.qss applied, AdjustToContents' computed
    width didn't reliably include the stylesheet's own padding/border/
    drop-down-arrow chrome on top of the text -- a longer item like
    "简体中文 (zh-CN)" got a box just narrow enough that its first
    character was clipped against the left edge, while shorter items
    (which happened to still fit inside whatever width the box was
    already getting from minimumContentsLength) looked fine, which is
    why this went unnoticed until a long language label was actually
    tried. AdjustToContents is a *relative* fit -- it sizes to whatever
    the box's own sizeHint() reports, and doesn't know to pad that for
    chrome a style sheet adds outside Qt's own metrics -- so this backs
    it with an *absolute* floor computed straight from font metrics on
    every current item, sized generously enough to cover that chrome
    regardless of what AdjustToContents alone comes up with.
    """
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    combo.setMinimumContentsLength(10)
    _ensure_minimum_width_for_items(combo)


def _ensure_minimum_width_for_items(combo):
    fm = combo.fontMetrics()
    widest_text_px = max(
        (fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
        default=0,
    )
    combo.setMinimumWidth(widest_text_px + _COMBO_STYLESHEET_CHROME_PX)


def labeled_field(label_text, field_widget):
    """A label stacked above a field widget, as a tight (label, field)
    pair meant to sit inline with other such pairs in one QHBoxLayout --
    the "several related short inputs in one compact row" replacement for
    stacking each in its own full-width QFormLayout section.
    """
    box = QVBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    label = QLabel(label_text)
    label.setProperty('role', 'fieldLabel')
    box.addWidget(label)
    box.addWidget(field_widget)
    return box


# The stroke color every tool sidebar glyph is drawn with; home-page
# tiles re-render the same SVG with this swapped to the accent indigo
# (see tinted_icon_pixmap) so the big icons read as actionable without
# the sidebar set changing character.
_GLYPH_SLATE = '#6B7280'
_GLYPH_INDIGO = '#2E4374'


def tinted_icon_pixmap(icon_path, size):
    """Render an icon SVG at ``size`` with its slate stroke swapped to
    the accent indigo -- home-page tiles only, sidebar glyphs stay quiet.
    String-level swap on the SVG source (the one documented glyph color,
    never a color-management surprise) then QSvgRenderer from the edited
    string keeps anti-aliasing and the two-tone white-fill details.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    with open(icon_path, encoding='utf-8') as f:
        svg = f.read().replace(_GLYPH_SLATE, _GLYPH_INDIGO)

    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    QSvgRenderer(svg.encode('utf-8')).render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def apply_page_icon(page, icon_path):
    """Drop a tool's glyph into the header chip ``page_shell()`` reserved for
    it (``QLabel#pageHeaderIcon``), tinted indigo like the home tiles so the
    top of every page carries one clear color focal point.

    Called by ``MainWindow`` right after building each page from its
    ``ToolSpec`` -- the window already knows the icon path, so no tool page
    has to hardcode its own id/path or thread it through ``page_shell()``.
    A no-op for a page built outside the window (tests) or one that never
    installed the header chip (e.g. the home page): ``findChild`` returns
    None and we simply skip.
    """
    label = page.findChild(QLabel, 'pageHeaderIcon')
    if label is None or not icon_path or not os.path.exists(icon_path):
        return
    label.setPixmap(tinted_icon_pixmap(icon_path, 34))
    label.show()


class LogConsole(QTextEdit):
    """The shared append-only result/status log (``objectName('logConsole')``,
    read-only). Behaves exactly like the plain ``QTextEdit`` pages used to
    build by hand -- ``append()``/``toPlainText()`` and the QSS selector all
    still work -- but adds one thing they lacked: a real *empty state*.

    A bare QTextEdit with a top-left placeholder turned the (often
    screen-filling) result area into a big white void with a lonely gray
    word in the corner -- the single biggest source of the "单调/空" feel on
    pages like 语料维护/语料转换. When there's no content yet we paint a
    centered line-art "console" glyph + the hint underneath instead; the
    moment anything is appended the document is non-empty and the normal
    console rendering takes over. The glyph is drawn with QPainter
    primitives (not an icon font), so it renders identically on Windows and
    the Linux CI canary -- no per-glyph CJK/symbol fallback surprises.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('logConsole')
        self.setReadOnly(True)
        self._empty_hint = ''

    def set_empty_hint(self, text):
        self._empty_hint = text
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._empty_hint and self.document().isEmpty():
            self._paint_empty_state()

    def _paint_empty_state(self):
        vp = self.viewport()
        painter = QPainter(vp)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = vp.width() / 2, vp.height() / 2

        icon_w, icon_h = 38, 28
        ix, iy = int(cx - icon_w / 2), int(cy - icon_h / 2 - 12)
        pen = QPen(QColor('#C3C9D3'))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(ix, iy, icon_w, icon_h, 5, 5)
        # three "log lines" of differing length inside the frame
        for i, frac in enumerate((0.55, 0.78, 0.42)):
            ly = iy + 8 + i * 6
            painter.drawLine(ix + 6, ly, int(ix + 6 + (icon_w - 12) * frac), ly)

        painter.setPen(QColor('#A6ACB6'))
        text_rect = QRect(0, iy + icon_h + 8, vp.width(), 20)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._empty_hint)
        painter.end()


def page_shell(page, title, subtitle, spacing=18, max_width=960):
    """The standard skeleton for a tool page's ``_build_ui()``: a page
    header (20px title + muted subtitle, styled via objectName in
    style.qss -- never inline setStyleSheet here) above one white content
    card wrapped in a ``QScrollArea`` (short pages never scroll, tall ones
    no longer clip at small window sizes), the card carrying the app's
    only per-page elevation shadow.

    ``page`` is the ``QWidget`` calling this from its own ``_build_ui()``
    (pass ``self``) -- the layout this builds gets installed on it via a
    plain ``page.setLayout(root)``. This used to be inferred by walking
    the call stack for a local named ``self`` typed as a ``QWidget``,
    which happened to work for every current call site (`_build_ui()`
    called directly from `__init__`) but was never guaranteed to: a page
    built from a nested helper, or constructed while another widget's own
    `__init__` is still on the stack, could have silently attached the
    layout to the wrong widget with no error. An explicit parameter can't
    misattach.

    The header + card live in a column capped to ``max_width`` and
    *centered* horizontally (2026-09 layout pass): on a wide window the
    page reads as a focused pane instead of a form whose fields stretch
    edge-to-edge across every pixel. The cap is what keeps a line edit
    from running 1500px on a maximized monitor; centering is what keeps
    the leftover space balanced -- a left-aligned capped column dumped
    every spare pixel into one cavernous band on the right, which read as
    a layout bug rather than a margin. The column still fills the vertical
    space so the scroll area grows with the window.

    Returns ``(outer_layout, title_label, subtitle_label)``:
    ``outer_layout`` is what a page adds its sections to, exactly like
    the ``outer = QVBoxLayout(self)`` it replaced -- except its direct
    child is now the scroll area's card, so ``addWidget`` keeps working
    unchanged. The two label references let pages/tests assert on the
    header without hunting for it by objectName.
    """
    root = QVBoxLayout()
    root.setContentsMargins(28, 24, 28, 24)
    root.setSpacing(0)

    hwrap = QHBoxLayout()
    hwrap.setContentsMargins(0, 0, 0, 0)
    hwrap.setSpacing(0)

    column = QWidget()
    column.setObjectName('pageColumn')
    column.setMaximumWidth(max_width)
    # Expanding (not Preferred) horizontally so the column grows to fill the
    # window up to ``max_width``; the surrounding stretches then only absorb
    # the *remaining* slack and center it. With Preferred it would sit at its
    # content's narrow natural width and leave big blanks on both sides.
    column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    col_layout = QVBoxLayout(column)
    col_layout.setContentsMargins(0, 0, 0, 0)
    col_layout.setSpacing(14)

    header = QWidget()
    header.setObjectName('pageHeader')
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(14)
    # Icon chip reserved for the tool glyph (filled by MainWindow via
    # apply_page_icon()); hidden until an icon lands so a page built without
    # one (home, tests) shows no empty colored box. Indigo glyph on an
    # indigo-tinted rounded chip -- the one deliberate color focal point at
    # the top of every page.
    icon_label = QLabel()
    icon_label.setObjectName('pageHeaderIcon')
    icon_label.setFixedSize(44, 44)
    icon_label.setAlignment(Qt.AlignCenter)
    icon_label.hide()
    title_label = QLabel(title)
    title_label.setObjectName('pageTitle')
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName('pageSubtitle')
    text_col = QVBoxLayout()
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(2)
    text_col.addWidget(title_label)
    text_col.addWidget(subtitle_label)
    header_layout.addWidget(icon_label, 0, Qt.AlignVCenter)
    header_layout.addLayout(text_col, 1)
    col_layout.addWidget(header)

    card = QWidget()
    card.setObjectName('pageCard')
    outer = QVBoxLayout(card)
    outer.setContentsMargins(24, 22, 24, 22)
    outer.setSpacing(spacing)

    shadow = QGraphicsDropShadowEffect(blurRadius=14, xOffset=0, yOffset=2)
    shadow.setColor(QColor(26, 29, 35, 16))  # ink at ~6% -- see DESIGN.md §13
    card.setGraphicsEffect(shadow)

    scroll = QScrollArea()
    scroll.setObjectName('pageScroll')
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    # As-needed, not AlwaysOff: a row of inline fields (e.g. corpus_convert's
    # 原文语言/译文语言/文档排版方式, or a line edit + its 浏览 button) has a
    # minimum width it can't shrink below. With the bar hard-off, a window
    # narrower than that silently clipped the rightmost control off-screen
    # with no way to reach it. AsNeeded keeps wide/maximized windows
    # scrollbar-free (the common case) while a genuinely narrow window gets a
    # horizontal bar so nothing is ever unreachable.
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(card)
    col_layout.addWidget(scroll, 1)

    # The column's stretch factor dominates (1000 vs the side stretches' 1),
    # so it absorbs all slack first and grows to its ``max_width`` cap; the
    # tiny leftover is then split evenly by the two side stretches, centering
    # the capped column. (A plain addWidget + equal stretches would instead
    # leave the column at its narrow natural width with big blanks on both
    # sides; a lone trailing stretch would pile every spare pixel on the right.)
    hwrap.addStretch(1)
    hwrap.addWidget(column, 1000)
    hwrap.addStretch(1)
    root.addLayout(hwrap, 1)

    # `page` (the caller's `self`, passed in explicitly -- see docstring)
    # gets the root layout installed here -- pages keep adding sections to
    # the returned `outer` (the card's layout) with no other change to
    # their _build_ui() bodies.
    page.setLayout(root)
    return outer, title_label, subtitle_label


class CurrentPageTabWidget(QTabWidget):
    """A ``QTabWidget`` that sizes to its *current* page instead of the
    tallest one.

    The stock widget reserves room for the largest page so switching tabs
    never resizes -- but in a page whose tabs hold very different amounts
    of content (tm_maintenance: a couple of short inputs on 清理 vs a big
    results table on 统计), that leaves the short tab with a tall empty
    band under its controls, which reads as a layout bug and fights the
    results area below for space. Reporting the current page's size lets
    the surrounding layout hand the freed vertical space to whatever
    stretches (the shared 结果 log), so no tab shows a void. Re-emits
    ``updateGeometry`` on tab change so the surrounding layout re-flows
    the moment the user switches.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda *_: self.updateGeometry())

    def _current_page_hint(self, which):
        # Keep the stock WIDTH (max over all pages + tab bar) so the tab
        # bar never gets squeezed into scroller arrows and the surrounding
        # width-capped column stays its intended width; only the HEIGHT
        # tracks the current page -- that is the whole point.
        base = super().sizeHint() if which == 'size' else super().minimumSizeHint()
        current = self.currentWidget()
        if current is None:
            return base
        page_hint = current.sizeHint() if which == 'size' else current.minimumSizeHint()
        # + tab-bar height and a few px for the pane border/`top` offset
        # the QSS gives QTabWidget::pane, so the pane never clips content.
        bar = self.tabBar().sizeHint().height()
        return QSize(base.width(), page_hint.height() + bar + 12)

    def sizeHint(self):
        return self._current_page_hint('size')

    def minimumSizeHint(self):
        return self._current_page_hint('min')
