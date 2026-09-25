"""The QA-check tool's page: run every check in ``language_tools.qa``
against an already-existing corpus file (tmx/sdltm) and let the user
browse/filter/export the results.

This is the standalone counterpart to the QA checkbox in
``corpus_convert``'s page: that one runs QA as a side effect of
conversion, this one runs QA as the whole point, against a corpus you
already have. Both ultimately call the same ``language_tools.qa.run()``
-- see ``language_tools/tm/qa_report.py`` for the thin wiring that reads
an existing file and calls it (this page just wraps that module in a UI,
same "no HTTP layer" shape as every other tool page).

Same conventions as the other two tools: ``section()``/``CallableWorker``
from ``toolbox.widgets``/``toolbox.workers`` (this is the third tool using
both, which is why they're shared modules and not another private copy),
``objectName('primaryButton')``/``objectName('logConsole')``.

Result presentation follows tm_maintenance's stats-tab precedent (a
``QTableWidget``, not a log dump) but goes further: QA output is
per-segment, potentially thousands of rows for a large TM, so simply
listing everything would bury the handful of rows that actually need a
human's attention. Two controls narrow the view: a "只显示有问题的条目"
checkbox (checked by default -- the useful default view for someone who
just wants the punch list) and an issue-type filter dropdown. Both are
display-only filters over data already in memory (``self._last_units``)
-- neither re-runs QA or touches the file, so toggling them is instant.

A third control, "自动换行" (unchecked by default), trades that compact
one-row-per-item layout for readability: the default single-line view
elides long 原文/译文 text with "…", which is the right call for scanning
a punch list quickly but means a long sentence can't actually be read
without opening the exported CSV. Checking it switches those two columns
to word-wrapped, auto-growing rows instead.

For a row with NUMBER_MISMATCH, PLACEHOLDER_MISMATCH, URL_MISMATCH,
PUNCTUATION_UNBALANCED, or WIDTH_MIXING, every relevant span
(``qa.find_number_spans()``, ``find_placeholder_spans()``,
``find_url_spans()``, ``find_punctuation_pair_spans()``,
``find_width_mixing_spans()`` respectively) in 原文/译文 is highlighted
(bold, danger-red -- the one semantic "problem" color this app's
stylesheet defines, not a new decorative one) -- independent of the wrap
toggle, since a reviewer scanning the default single-line view needs
exactly as much help spotting what to compare as one who expanded a row
to read it in full; wrap only controls whether the *rest* of the
sentence is elided or shown in full, not whether anything gets marked.
All five checks share one highlight color rather than each getting its
own: a row can have more than one of these issues at once (see e.g.
``test_table_shows_multiple_issue_labels_joined_for_one_row``), and a
per-type color palette would mean either learning a legend or the
colors becoming noise; the "问题类型" column already says *what* kind of
issue it is, so highlighting's only job is *where* to look, not *which*
check flagged it. TAG_MISMATCH is deliberately not included: it's
detected over structured inline-markup nodes, not simple substring
matches on raw text, so there's no straightforward span to point at (see
qa.py's ``_tag_type_counts()``); LENGTH_RATIO_OUTLIER, EMPTY_SOURCE/
_TARGET, SOURCE_/TARGET_CONFLICT, and LEADING_TRAILING_SPACE are
whole-segment properties with no particular substring to blame either --
LEADING_TRAILING_SPACE specifically has a "span" (the leading/trailing
run) but it's whitespace, which renders as nothing to look at even in
red, so there's no point highlighting it. See ``_HIGHLIGHT_HINT``: a
small caption above the table explains what the red text means, shown
only when the current (filtered) results actually contain a row with at
least one of the highlightable issue types -- no point explaining a
color the user isn't looking at. The point of highlighting a
NUMBER_MISMATCH row specifically isn't to mark which number is "the"
wrong one -- with a set-based comparison there often isn't a single
answer to that, e.g. one extra number on either side shifts every
pairing -- it's to make every number in the sentence visually findable
at a glance, since NUMBER_MISMATCH itself is silent about which of
possibly several numbers is involved (see qa.py's NUMBER_MISMATCH
docstring and ``find_number_spans()``'s for the detection/highlighting
split this relies on). PLACEHOLDER_MISMATCH and URL_MISMATCH don't have
that same "which one" ambiguity -- they're localized substring
comparisons already -- but get the same treatment for consistency and
because it's the same one-line-of-code cost per check once the
"highlight this span" plumbing exists at all.

Because a highlightable row needs rich-text highlighting even in the
default (non-wrap) view, that path still uses a QLabel cell widget
(``_make_cell_label()``, unchanged since it works fine there -- a
single-line label's height doesn't depend on its width, so none of the
problems below apply to it). Wrap mode is the case that actually needs a
content-driven, width-dependent row height, and that's where a cell
widget turns out to be the wrong tool:

``QTableWidget.setCellWidget()`` places a real child widget into a cell,
but a *cell widget's* size is not part of the table view's native
painting/sizing path the way a plain item's is -- the widget's own
``sizeHint()``/``heightForWidth()`` and the table's row-height
computation are two separate systems that have to be kept in sync by
hand, and getting that synchronization right for a wrapped, rich-text
label turned out to fail in more ways than expected: a bare
``QTextDocument`` re-implementation of text layout that didn't match
what ``QLabel`` actually rendered; ``QLabel.heightForWidth()`` fed a
column width read at a moment that could be stale (a later row's height
pushing the vertical scrollbar into existence narrows every column
out from under an earlier row's already-computed height);
``QTableWidget.resizeRowsToContents()``, whose ``sizeHint()`` call
doesn't track a word-wrapped rich-text ``QLabel``'s actual assigned
width at all (confirmed empirically: a label 455px wide reported a
``sizeHint`` of width 228); and finally reacting to the widget's own
``resizeEvent()`` with a settling timer, which worked but could only
grow a row, never shrink it back down once a since-widened window no
longer needed the extra height.

The fix was to stop using a cell widget for this at all. In wrap mode,
原文/译文 stay as ordinary ``QTableWidgetItem``s (so ``item(row, col)``
still works, e.g. for tests) with their escaped/highlighted HTML stashed
in a private data role (``_WRAP_HTML_ROLE``) instead of ``DisplayRole``.
``_QaTextDelegate`` -- the table's ``QStyledItemDelegate`` -- paints that
HTML and, critically, its ``sizeHint(option, index)`` is *called by the
view itself* with ``option.rect`` already set to that cell's real,
current width, every time the view needs to know a row's height. There's
no separate widget with its own out-of-band geometry to keep in sync --
the width sizeHint() is asked about *is* the width the view is about to
paint at, by construction, because it's the same object handing out both
answers. That's what every widget-based attempt above was missing.

``_reflow_wrapped_rows()`` still needs to prompt the view to re-ask the
delegate (``resizeRowsToContents()`` isn't automatic), and still needs
to guard against re-laying-out rows changing the vertical scrollbar's
presence and therefore the column width every row was just measured
against -- same mechanism as above, just now resolved by re-checking
column width after each pass and stopping once it's stable, rather than
by a widget's own settling timer.

A window resize changes the Stretch-resized 原文/译文 columns' width,
which affects non-wrap mode's "…" elide point for a highlighted row (a
widened window may now fit text that used to need truncating) -- see
``QaCheckPage.resizeEvent()`` for how that's kept in sync with the
table's current width via a debounced full ``_refresh_table()`` rather
than the header's ``sectionResized`` signal: querying ``columnWidth()``
synchronously inside a ``sectionResized`` handler reads a *stale* value
until every column's resize signal for that layout pass has been
processed (confirmed empirically), which is what caused elided rows to
stay stuck at their old truncation point even after the window was
widened back out. The same debounced refresh also starts
``_wrap_reflow`` (another debounce, not called inline: several resize
events can fire in a burst, and there's no reason to re-lay-out the
whole table once per event when only the final, settled width matters)
to recompute wrapped row heights once the Stretch columns settle.

Export is deliberately NOT filtered by the current view: "导出 CSV"
always writes the full corpus (every unit, QA columns included) via the
existing ``csv_writer.write(..., include_qa=True)``, unfiltered. Two
reasons: (1) reusing that function exactly as the convert pipeline already
does means there's no second "filtered CSV" code path to keep in sync,
and (2) a reviewer opening the CSV in Excel can filter/sort there with
full context (they can still see what passed, not just what failed) --
narrowing to "problems only" at export time would silently discard that.

Issue codes (TAG_MISMATCH, etc.) are translated to Chinese labels for
display -- both here (results table + filter dropdown, via
``_issue_label()``) and in the exported CSV (``csv_writer.py``'s own use
of the same ``qa.ISSUE_LABELS`` table) -- since a bare code means nothing
to a translator/reviewer who isn't the one who wrote the QA checks. The
codes themselves stay untouched as ``self._last_units[i].meta['qa_issues']``
and as the filter dropdown's underlying ``currentData()`` values; only the
*rendered* text changes.

Settings persistence: implements the optional ``restore_settings()``/
``save_settings()`` hooks ``main_window.py`` checks for (see
``corpus_convert/page.py``'s docstring for the full reasoning) --
只显示有问题的条目/自动换行 and the file dialog's last-used directory
round-trip across launches via ``toolbox/settings.py``, under the
``qa_check/`` key prefix. 问题类型 filter selection isn't persisted:
it's chosen against whatever check just ran, not a standing preference.

导出报告 (``_start_export_report()``) is a second export button next to
导出 CSV: same source data (``self._last_units``) but going through
``language_tools.reports`` instead -- a summary (total/flagged-rate/
by-issue-type breakdown, via ``report_adapters.from_qa_summary()``) as
HTML or PDF, for a non-technical stakeholder who wants a readable report
rather than a CSV to filter in Excel. Synchronous, unlike CSV export's
``CallableWorker`` thread: this is writing one small summary, not
``self._last_units`` in full, so there's nothing here worth a background
thread for. tm_maintenance/page.py's leverage/compare tabs are the other
two ``tmtool`` subcommands with a ``--report``, and use the identical
``report_render.write()``/extension-dispatch pattern.

导出审阅文档 (``_start_export_review()``) is a third export button,
going through the same ``report_render``/``report_adapters`` machinery
as 导出报告 but a different adapter (``from_bilingual_review()``): a
bilingual side-by-side HTML page listing only the *flagged* segments,
with the exact spans a highlightable check caught marked red the same
way this page's own results table does (``qa.merged_highlight_spans()``
is the shared logic both draw on -- see that function's docstring). For
handing to a client or proofreader to work through line by line, not
for a stakeholder wanting totals -- that's still 导出报告's job. HTML
only, no PDF option in its file dialog filter (``_REVIEW_FILTER``):
reportlab can't render the adapter's HTML-highlight markup, and
``report_render.write_pdf()`` raises rather than attempting it if a
`.pdf` path is typed in anyway. Also synchronous despite iterating
``self._last_units`` rather than one summary dict: the adapter's own
row cap (``_BILINGUAL_REVIEW_ROW_CAP`` in reports/adapters.py) keeps
this to at most a few hundred cheap regex passes, well under what would
justify a background thread.
"""
import html
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAbstractTextDocumentLayout, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from language_tools import qa as qa_module
from language_tools.reports import adapters as report_adapters
from language_tools.reports import render as report_render
from language_tools.tm import io as tm_io
from language_tools.tm import qa_report as qa_report_module
from language_tools.writers import csv_writer
from toolbox import settings
from toolbox.widgets import CORPUS_FILTER, LOG_COLORS, page_shell, section
from toolbox.workers import CallableWorker, wait_for_running

_CSV_FILTER = 'CSV (*.csv)'
_REPORT_FILTER = 'HTML (*.html);;PDF (*.pdf)'
_REVIEW_FILTER = 'HTML (*.html)'  # HTML only -- see report_render.write_pdf()'s raw_html guard
_SETTINGS_PREFIX = 'qa_check/'

# Opt-in diagnostic logging for the wrap-mode row-height/resize path,
# which has been the subject of several rounds of "fixed here, still
# broken on the user's real machine" -- reproducing what's actually
# happening on a specific real machine (a specific font, DPI, and
# resize-event timing this sandbox's offscreen platform can't match) has
# repeatedly turned out to be more useful than another guess made
# without seeing real data from it. Set QA_CHECK_DEBUG=1 before launching
# the app (from a terminal, so stderr is visible) to print each resize/
# reflow step -- when it fires, what column widths and row heights it
# computes -- as it happens; off (the default) has zero runtime cost
# beyond the one environment-variable read below.
_DEBUG = os.environ.get('QA_CHECK_DEBUG') == '1'


def _debug_log(message):
    if _DEBUG:
        print(f'[qa_check debug] {message}', file=sys.stderr, flush=True)
_WRAP_HTML_ROLE = Qt.UserRole + 1
_CELL_HORIZONTAL_PADDING = 20
# The vertical offset paint() translates by before drawing (below) --
# not a separate, hand-typed "6" in sizeHint()'s own height computation.
# A second, independently-typed copy of this number is exactly the kind
# of thing that drifts: paint() used 6px, sizeHint() used 0, and the
# 6px gap between them was clipping the bottom of every row whose
# content actually grew past the single-line floor (short/single-line
# rows never showed it: the floor already had more slack than 6px to
# absorb it). One constant, read by both, means there's no second copy
# to drift out of sync with this one again.
_CELL_TOP_PADDING = 6

# Bold + this app's one "problem" semantic color (see toolbox/resources/
# style.qss's design-token comment: "danger -- semantic only, not
# decorative") for a highlighted span -- deliberately not a new
# background-highlight color, and deliberately the same one color for
# every highlightable issue type rather than one color per type (see
# module docstring for why), to stay inside that existing, disciplined
# palette rather than inventing a decorative one for this.
_ISSUE_HIGHLIGHT_STYLE = 'color:#B23B3B; font-weight:600;'

_HIGHLIGHT_HINT = (
    '提示：红色文字为"数字不匹配/占位符不匹配/URL 不匹配/括号引号不成对/'
    '全半角混用"检测涉及的内容，请核对原文与译文是否一致')

_SPAN_FINDERS = qa_module.SPAN_FINDERS  # single source of truth -- see qa.py

_ISSUE_TOOLTIPS = {
    'EMPTY_SOURCE': '这一条的原文是空的',
    'EMPTY_TARGET': '这一条还没有翻译',
    'LENGTH_RATIO_OUTLIER': '译文长度和原文长度的比例明显偏离整个语料库的平均水平',
    'NUMBER_MISMATCH': '原文和译文里出现的数字对不上，可能是漏译或多译',
    'PLACEHOLDER_MISMATCH': '{name}/%s 这类代码占位符在译文里被改动或丢失',
    'URL_MISMATCH': '原文里的链接在译文里丢失或被改动',
    'TAG_MISMATCH': '原文和译文的格式标签（如加粗）数量对不上',
    'PUNCTUATION_UNBALANCED': '原文或译文里的括号、引号数量不成对',
    'WIDTH_MIXING': '同一句里全角和半角标点混用',
    'LEADING_TRAILING_SPACE': '原文或译文开头/结尾有多余空格',
    'SOURCE_CONFLICT': '同一句原文在语料库里对应了不止一种译文',
    'TARGET_CONFLICT': '同一句译文在语料库里对应了不止一种原文',
}


def _issue_label(issue_code):
    return qa_module.ISSUE_LABELS.get(issue_code, issue_code)


def _relevant_spans(text, issues):
    """Return merged highlight spans for the row's applicable checks."""
    return qa_module.merged_highlight_spans(text, issues)


def _highlighted_html(text, spans):
    """Escape text and wrap the selected source spans in rich text."""
    out = []
    pos = 0
    for start, end in spans:
        out.append(html.escape(text[pos:start]))
        out.append('<b style="%s">%s</b>' % (_ISSUE_HIGHLIGHT_STYLE, html.escape(text[start:end])))
        pos = end
    out.append(html.escape(text[pos:]))
    return ''.join(out)


class _QaTextDelegate(QStyledItemDelegate):
    """Item delegate for the QA results table's 原文/译文 columns in wrap
    mode. Paints the rich-text HTML stashed in ``_WRAP_HTML_ROLE`` (see
    module docstring for why this replaced a QLabel cell widget) and
    reports a content-driven ``sizeHint()`` using the real column width
    the table view passes in via ``option.rect`` -- the piece every
    earlier cell-widget-based attempt was missing.
    """

    def _document(self, index, width):
        """QTextDocument laid out at ``width``, shared by paint() and
        sizeHint() below -- one implementation of "how is this HTML laid
        out", not two that could drift apart from each other.
        """
        document = QTextDocument()
        document.setDefaultFont(index.data(Qt.FontRole) or self.parent().font())
        document.setDocumentMargin(0)
        html_text = index.data(_WRAP_HTML_ROLE) or ''
        document.setHtml(html_text)
        text_width = max(width - _CELL_HORIZONTAL_PADDING, 1)
        document.setTextWidth(text_width)
        if _DEBUG:
            # Untruncated html (a previous version cut this to 80 chars,
            # which -- for at least one real report -- hid the exact
            # point where two seemingly-similar-length sentences started
            # behaving differently, so there was nothing left to compare
            # them on).
            _debug_log(f'_document: row={index.row()} col={index.column()} '
                       f'requested_width={width} text_width={text_width} '
                       f'raw_doc_size={document.size()} html={html_text!r}')
        return document

    def paint(self, painter, option, index):
        html_text = index.data(_WRAP_HTML_ROLE)
        if not html_text:
            super().paint(painter, option, index)
            return
        # drawControl(CE_ItemViewItem, ...) paints this cell's background,
        # selection, and focus chrome -- not its text, since option.text
        # is never populated here (this delegate never calls
        # initStyleOption(), the only thing that would set it -- verified
        # empirically: drawControl alone renders zero text pixels for
        # this cell, confirming there's no double-painted text sitting
        # underneath the rich-text document drawn below).
        QApplication.style().drawControl(
            QStyle.CE_ItemViewItem, option, painter, option.widget)

        painter.save()
        painter.setClipRect(option.rect)
        document = self._document(index, option.rect.width())
        painter.translate(option.rect.left() + _CELL_HORIZONTAL_PADDING // 2,
                           option.rect.top() + _CELL_TOP_PADDING)
        # document.drawContents(painter) alone leaves this cell's
        # unstyled text color to whatever QTextDocument falls back to
        # implicitly, which is not necessarily this table's actual text
        # color (option.palette, which already reflects this app's real
        # QSS-resolved palette, the same one a plain QTableWidgetItem's
        # text is drawn with) -- an implicit default is exactly the kind
        # of thing that can differ across a Qt version/theme/platform
        # without this code changing at all. Passing an explicit
        # PaintContext built from option.palette pins unstyled text to
        # the same color every other cell already uses, rather than
        # leaving it to an assumption about what QTextDocument defaults
        # to matching that.
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette = option.palette
        document.documentLayout().draw(painter, context)
        painter.restore()

    def sizeHint(self, option, index):
        html_text = index.data(_WRAP_HTML_ROLE)
        floor = self.parent().verticalHeader().defaultSectionSize()
        if not html_text:
            # Also floored, not just returned as-is: row height for these
            # columns (#, 问题类型, 置信度) is set directly by
            # _reflow_wrapped_rows() from the floor alone, without
            # querying this branch at all -- but sizeHint() can still be
            # called for them through other Qt-internal paths (e.g. the
            # view's own layout/scroll bookkeeping), and Qt's own default
            # delegate's sizeHint() for these columns' content can exceed
            # the floor on this app's real font (confirmed empirically:
            # 28-29px vs a 30px floor is close, but not guaranteed to
            # stay that way for longer 问题类型 label text). Keeping this
            # capped means any such call stays consistent with "these
            # columns never make a row taller than its default", which
            # was true before any of this wrap-mode work existed.
            size = super().sizeHint(option, index)
            size.setHeight(min(size.height(), floor))
            return size
        # option.rect.width() here is the table view's own, real,
        # current width for this cell -- not a value read from somewhere
        # else that could be stale or unrelated to what's about to be
        # painted (see module docstring for the history of widget-based
        # approaches that got exactly this wrong).
        document = self._document(index, option.rect.width())
        size = document.size().toSize()
        size.setWidth(option.rect.width())
        # Floored at the table's own normal single-line row height (what
        # a plain, non-wrap row already uses). Not a blind revival of the
        # fixed +12px padding removed earlier (that one was an arbitrary
        # guess, tall enough to push even single-line content over the
        # floor on this app's real font -- confirmed empirically: 30px
        # non-wrap vs 35px wrap-mode for identical one-line content).
        # _CELL_TOP_PADDING is different: it's not a guess, it's the
        # exact vertical offset paint() actually draws at (see that
        # method), so adding it here is correcting a real shortfall
        # (paint() was pushing every row's content down 6px that
        # sizeHint() never accounted for, clipping the bottom of any row
        # whose content grew past the floor -- e.g. a genuinely two-line
        # row correctly measured at 34px still needed 40px once that 6px
        # offset was included), not re-adding the earlier bug: 6px is
        # small enough that single-line content (this app's real font:
        # ~17px) plus it (~23px) still comfortably sits under the floor,
        # so the single-line case stays fixed while the multi-line
        # clipping is now actually corrected instead of only relocated.
        size.setHeight(max(floor, size.height() + _CELL_TOP_PADDING))
        return size


class QaCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_units = None
        self._check_worker = None
        self._export_worker = None
        self._last_dir = ''  # overwritten by restore_settings() when wired through MainWindow
        # Debounced (not immediate) window-resize handling -- see
        # resizeEvent() below for why.
        self._resize_debounce = QTimer(self)
        self._resize_debounce.setSingleShot(True)
        self._resize_debounce.setInterval(80)
        self._resize_debounce.timeout.connect(self._refresh_table)
        self._wrap_reflow = QTimer(self)
        self._wrap_reflow.setSingleShot(True)
        self._wrap_reflow.setInterval(80)
        self._wrap_reflow.timeout.connect(self._reflow_wrapped_rows)
        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounced full refresh on window resize -- see module docstring
        # ("A window resize changes...") for why this is a debounced
        # _refresh_table() rather than an immediate per-event handler or
        # the header's sectionResized signal.
        if self._last_units:
            _debug_log(f'resizeEvent: new size={event.size().width()}x{event.size().height()}, '
                       f'(re)starting _resize_debounce')
            self._resize_debounce.start()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        outer, _, _ = page_shell(
            'QA 检查',
            '对已有的翻译记忆库（tmx/sdltm）跑质量检查，生成审阅报告',
            spacing=18,
        )

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('选择要检查的 tmx/sdltm 文件…')
        browse_btn = QPushButton('浏览…')
        browse_btn.clicked.connect(self._browse_input)
        file_layout.addWidget(self.input_edit, 1)
        file_layout.addWidget(browse_btn)
        outer.addWidget(section('选择文件', file_row))

        action_row = QHBoxLayout()
        self.check_btn = QPushButton('开始检查')
        self.check_btn.setObjectName('primaryButton')
        self.check_btn.clicked.connect(self._start_check)
        self.export_btn = QPushButton('导出 CSV…')
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip('导出全部条目（含未标记问题的），不受下面的筛选影响')
        self.export_btn.clicked.connect(self._start_export)
        self.export_report_btn = QPushButton('导出报告…')
        self.export_report_btn.setEnabled(False)
        self.export_report_btn.setToolTip(
            '导出为 HTML 或 PDF 的汇总报告（总数/问题占比/按类型统计），适合给非技术干系人看')
        self.export_report_btn.clicked.connect(self._start_export_report)
        self.export_review_btn = QPushButton('导出审阅文档…')
        self.export_review_btn.setEnabled(False)
        self.export_review_btn.setToolTip(
            '导出为双语对照 HTML 页（只含有问题的条目，问题相关内容已标红），适合发给客户/审校逐条核对')
        self.export_review_btn.clicked.connect(self._start_export_review)
        action_row.addWidget(self.check_btn)
        action_row.addWidget(self.export_btn)
        action_row.addWidget(self.export_report_btn)
        action_row.addWidget(self.export_review_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('color: #4B5262;')
        outer.addWidget(self.summary_label)

        # --- QA 结果: filter row + table together under one section ---
        # 筛选 used to be its own section above this one; folded in here
        # instead (filter row first, then the table it filters), same
        # move alignment_check made for its own 对齐结果 section (see
        # that page's comment at the equivalent spot) -- a standalone
        # "筛选" box for controls that only ever act on the table right
        # below it reads as "configure the filter, then see results",
        # when it's really the other way around: there's nothing to
        # filter until a check has actually run.
        results_content = QWidget()
        results_layout = QVBoxLayout(results_content)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(10)

        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self.hide_clean_chk = QCheckBox('只显示有问题的条目')
        self.hide_clean_chk.setChecked(True)
        self.hide_clean_chk.stateChanged.connect(self._refresh_table)
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItem('全部问题类型', None)
        for issue_type in qa_report_module.ISSUE_TYPES:
            label = _issue_label(issue_type)
            tip = _ISSUE_TOOLTIPS.get(issue_type, '')
            self.type_filter_combo.addItem(label, issue_type)
            if tip:
                self.type_filter_combo.setItemData(
                    self.type_filter_combo.count() - 1, tip, Qt.ToolTipRole)
        self.type_filter_combo.currentIndexChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.hide_clean_chk)
        filter_layout.addWidget(self.type_filter_combo)
        self.wrap_chk = QCheckBox('自动换行')
        self.wrap_chk.setToolTip('显示完整原文/译文，不再用"…"省略')
        self.wrap_chk.stateChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.wrap_chk)
        filter_layout.addStretch(1)
        results_layout.addWidget(filter_row)

        self.highlight_hint_label = QLabel(_HIGHLIGHT_HINT)
        self.highlight_hint_label.setStyleSheet('color: #6B7280; font-size: 12px;')
        self.highlight_hint_label.setVisible(False)
        results_layout.addWidget(self.highlight_hint_label)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(['#', '原文', '译文', '问题类型', '置信度'])
        self.results_table.verticalHeader().setVisible(False)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        # Header text defaults to centered, item text to left-aligned;
        # with 原文/译文 stretched to fill the window (and their content
        # often long) that mismatch reads as messy, especially maximized.
        # Left-align both so the header sits above its column's content.
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.results_table.setShowGrid(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setItemDelegate(_QaTextDelegate(self.results_table))
        # Window-resize handling (re-flowing wrap-mode row heights and
        # re-eliding non-wrap highlighted rows against the table's new
        # column widths) happens via this page's own resizeEvent(), not
        # a signal connected here -- see that method for why.
        results_layout.addWidget(self.results_table, 1)

        outer.addWidget(section('QA 结果', results_content), 1)

        self.log = QTextEdit()
        self.log.setObjectName('logConsole')
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText('状态信息会显示在这里')
        # The log is a status console, not one more form field -- giving it a
        # 状态 header (via section()) so it reads as an intentional result area
        # instead of a floating empty box under the results table. Same
        # treatment corpus_convert/tm_maintenance give their 结果 log.
        outer.addWidget(section('状态', self.log))

    # ------------------------------------------------------------- dialogs
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self._last_dir, CORPUS_FILTER)
        if path:
            self.input_edit.setText(path)
            self._last_dir = os.path.dirname(path)

    # ---------------------------------------------------------- lifecycle
    def cleanup(self):
        """Called by ``main_window.py`` on a real window close. See
        ``toolbox.workers.wait_for_running()`` for why a page with a
        worker needs this.
        """
        wait_for_running(self._check_worker, self._export_worker)

    # ---------------------------------------------------------- settings
    def restore_settings(self):
        self.hide_clean_chk.setChecked(settings.get_bool(_SETTINGS_PREFIX + 'hideClean', True))
        self.wrap_chk.setChecked(settings.get_bool(_SETTINGS_PREFIX + 'wrap', False))
        self._last_dir = settings.get_str(_SETTINGS_PREFIX + 'lastDir', '')

    def save_settings(self):
        settings.set_value(_SETTINGS_PREFIX + 'hideClean', self.hide_clean_chk.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'wrap', self.wrap_chk.isChecked())
        settings.set_value(_SETTINGS_PREFIX + 'lastDir', self._last_dir)

    # ------------------------------------------------------------ logging
    def _log(self, message, kind='info'):
        color = LOG_COLORS.get(kind, LOG_COLORS['info'])
        self.log.append('<span style="color:%s;">%s</span>' % (color, html.escape(message)))

    # ------------------------------------------------------------- check
    def _validate_check(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            return '请先选择要检查的文件'
        if not os.path.exists(input_path):
            return '找不到这个文件，请重新选择'
        return None

    def _start_check(self):
        self._last_units = None
        self.results_table.setRowCount(0)
        self.summary_label.setText('')
        self.export_btn.setEnabled(False)
        self.export_report_btn.setEnabled(False)
        self.export_review_btn.setEnabled(False)
        self.highlight_hint_label.setVisible(False)

        error = self._validate_check()
        if error:
            self._log(error, 'error')
            return

        input_path = self.input_edit.text().strip()
        self.check_btn.setEnabled(False)
        self._log('正在检查…')
        self._check_worker = CallableWorker(lambda: qa_report_module.run(input_path), parent=self)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.finished_err.connect(self._on_check_err)
        self._check_worker.start()

    def _on_check_ok(self, units):
        self.check_btn.setEnabled(True)
        self._last_units = units
        s = qa_report_module.summarize(units)
        rate = (s['flagged'] / s['total'] * 100) if s['total'] else 0.0
        self.summary_label.setText(
            '共 %d 条，%d 条有问题（%.1f%%）' % (s['total'], s['flagged'], rate))
        self.export_btn.setEnabled(bool(units))
        self.export_report_btn.setEnabled(bool(units))
        self.export_review_btn.setEnabled(bool(units))
        self._refresh_table()
        self._log('检查完成', 'success')

    def _on_check_err(self, message):
        self.check_btn.setEnabled(True)
        self._log('出错了：%s' % message, 'error')

    # ----------------------------------------------------------- filtering
    def _refresh_table(self):
        _debug_log(f'_refresh_table: called (wrap_chk={self.wrap_chk.isChecked()}, '
                   f'has_units={bool(self._last_units)})')
        self.results_table.setRowCount(0)
        if not self._last_units:
            self.highlight_hint_label.setVisible(False)
            return

        hide_clean = self.hide_clean_chk.isChecked()
        selected_type = self.type_filter_combo.currentData()
        wrap = self.wrap_chk.isChecked()

        rows = []
        for i, u in enumerate(self._last_units, 1):
            issues = u.meta.get('qa_issues', [])
            if hide_clean and not issues:
                continue
            if selected_type and selected_type not in issues:
                continue
            rows.append((i, u, issues))

        highlightable_types = set(_SPAN_FINDERS)
        self.highlight_hint_label.setVisible(
            any(highlightable_types.intersection(issues) for _, _, issues in rows))

        self.results_table.setRowCount(len(rows))
        for row, (i, u, issues) in enumerate(rows):
            conf = u.meta.get('qa_confidence', 1.0)
            issue_text = '、'.join(_issue_label(code) for code in issues) if issues else '-'
            self.results_table.setItem(row, 0, QTableWidgetItem(str(i)))
            highlight = bool(highlightable_types.intersection(issues))
            if wrap:
                self._set_wrapped_item(row, 1, u.src_text, issues)
                self._set_wrapped_item(row, 2, u.tgt_text, issues)
            elif highlight:
                src_label = self._make_cell_label(u.src_text, issues, column=1)
                tgt_label = self._make_cell_label(u.tgt_text, issues, column=2)
                self.results_table.setCellWidget(row, 1, src_label)
                self.results_table.setCellWidget(row, 2, tgt_label)
            else:
                self.results_table.setItem(row, 1, QTableWidgetItem(u.src_text))
                self.results_table.setItem(row, 2, QTableWidgetItem(u.tgt_text))
            self.results_table.setItem(row, 3, QTableWidgetItem(issue_text))
            self.results_table.setItem(row, 4, QTableWidgetItem('%.2f' % conf))
        if wrap:
            # Let the delegate measure each item after Qt has settled the
            # Stretch columns.
            _debug_log(f'_refresh_table: wrap on, {len(rows)} rows built, '
                       f'starting _wrap_reflow (columnWidth now: '
                       f'{self.results_table.columnWidth(1)}, '
                       f'{self.results_table.columnWidth(2)})')
            self._wrap_reflow.start()

    def _reflow_wrapped_rows(self):
        if not self.wrap_chk.isChecked() or not self.results_table.rowCount():
            _debug_log('_reflow_wrapped_rows: skipped (wrap off or no rows)')
            return
        table = self.results_table
        delegate = table.itemDelegate()
        floor = table.verticalHeader().defaultSectionSize()
        _debug_log(f'_reflow_wrapped_rows: starting, {table.rowCount()} rows, '
                   f'columnWidth=({table.columnWidth(1)}, {table.columnWidth(2)}), '
                   f'floor={floor}')
        # Row heights are set directly from the delegate's own sizeHint()
        # for just the wrap-HTML columns, NOT via
        # QTableWidget.resizeRowsToContents(): that call was tried first
        # (it's the "obvious" Qt API for this), and its own internal
        # row-height aggregation adds a margin on top of every column's
        # sizeHint() that isn't reflected in any sizeHint() call itself --
        # confirmed empirically: every column's sizeHint() for a row
        # topped out at 30px (matching the floor), yet
        # resizeRowsToContents() still set that row to 35px. That gap is
        # internal to Qt's own aggregation, not something the delegate
        # controls, so it can't be fixed by changing what sizeHint()
        # returns -- only by not going through resizeRowsToContents() at
        # all. #/问题类型/置信度 aren't queried here: their content is
        # always short, fixed-format text that's never needed more than
        # the floor in practice, so floor already covers them exactly as
        # they behaved before any of this wrap-mode work existed (their
        # sizeHint() was simply never queried, and rows sat at the
        # passive default height).
        #
        # Re-laying-out rows can itself make the vertical scrollbar
        # newly appear or disappear (taller rows -> more total content ->
        # scrollbar needed), which narrows/widens the Stretch-resized
        # columns out from under the row heights just computed against
        # the old width -- same mechanism documented in earlier commits'
        # history of this exact bug. Re-checking column width after each
        # pass and stopping once it's stable (rather than a fixed count)
        # does only as many passes as this row set actually needs; the
        # cap is a safety net against pathological back-and-forth, not
        # the normal case (typically converges in one pass).
        width_before = (table.columnWidth(1), table.columnWidth(2))
        for pass_num in range(5):
            table.doItemsLayout()
            for row in range(table.rowCount()):
                needed = floor
                for column in (1, 2):
                    option = QStyleOptionViewItem()
                    option.rect.setWidth(table.columnWidth(column))
                    index = table.model().index(row, column)
                    needed = max(needed, delegate.sizeHint(option, index).height())
                table.setRowHeight(row, needed)
            width_after = (table.columnWidth(1), table.columnWidth(2))
            _debug_log(f'_reflow_wrapped_rows: pass {pass_num}, '
                       f'width {width_before} -> {width_after}, '
                       f'row heights now: {[table.rowHeight(r) for r in range(table.rowCount())]}')
            if width_after == width_before:
                break
            width_before = width_after
        else:
            _debug_log('_reflow_wrapped_rows: hit the 5-pass cap without '
                       'column width settling -- see the per-pass log above')

    def _set_wrapped_item(self, row, column, text, issues):
        item = QTableWidgetItem(text)
        spans = _relevant_spans(text, issues)
        item.setData(_WRAP_HTML_ROLE, _highlighted_html(text, spans) if spans else html.escape(text))
        self.results_table.setItem(row, column, item)

    def _make_cell_label(self, text, issues, column):
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        # Stylesheet's blanket "QWidget { background: ... }" rule (see
        # style.qss) would otherwise paint every cell a flat, non-
        # alternating color instead of letting the table's own
        # alternating-row background show through this widget.
        label.setStyleSheet('background: transparent;')
        # Not wrapped: this path is only reached for a row with a
        # highlightable issue (see caller), which needs highlighting a
        # plain QTableWidgetItem can't render -- so it still needs its
        # own "…" elide, which a rich-text QLabel doesn't do
        # automatically. Elide the plain text first, then highlight
        # *that* (spans recomputed against the now-shorter elided
        # string, so offsets line up with what's actually visible), and
        # keep the untruncated original one hover away via the tooltip.
        fm = self.results_table.fontMetrics()
        width = max(self.results_table.columnWidth(column) - 12, 10)
        elided = fm.elidedText(text, Qt.ElideRight, width)
        spans = _relevant_spans(elided, issues)
        label.setText(_highlighted_html(elided, spans) if spans else html.escape(elided))
        if elided != text:
            label.setToolTip(text)
        return label

    # ------------------------------------------------------------ export
    def _start_export(self):
        # export_btn is only ever enabled after a successful check sets
        # self._last_units, so this can't be hit via the UI -- kept as a
        # silent guard against a future caller invoking this directly
        # (e.g. a keyboard shortcut wired to the same slot later) while no
        # results exist yet, rather than crashing on an empty CSV write.
        if not self._last_units:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', self._last_dir, _CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        self._last_dir = os.path.dirname(path)

        units = self._last_units
        src_lang, tgt_lang = tm_io.infer_langs(units)
        self.export_btn.setEnabled(False)
        self._log('正在导出…')
        self._export_worker = CallableWorker(
            lambda: csv_writer.write(path, units, src_lang or 'SRC', tgt_lang or 'TGT', include_qa=True),
            parent=self)
        self._export_worker.finished_ok.connect(lambda _=None: self._on_export_ok(path))
        self._export_worker.finished_err.connect(self._on_export_err)
        self._export_worker.start()

    def _on_export_ok(self, path):
        self.export_btn.setEnabled(True)
        self._log('已导出到 %s' % path, 'success')

    def _on_export_err(self, message):
        self.export_btn.setEnabled(True)
        self._log('导出失败：%s' % message, 'error')

    def _start_export_report(self):
        if not self._last_units:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, '导出报告', os.path.join(self._last_dir, 'QA报告'), _REPORT_FILTER)
        if not path:
            return
        if '.' not in os.path.basename(path):
            path += '.pdf' if 'PDF' in selected_filter else '.html'
        self._last_dir = os.path.dirname(path)
        s = qa_report_module.summarize(self._last_units)
        try:
            report_render.write(path, report_adapters.from_qa_summary(s))
        except (ValueError, ImportError) as e:
            self._log('出错了：%s' % e, 'error')
            return
        self._log('已导出报告到 %s' % path, 'success')

    def _start_export_review(self):
        if not self._last_units:
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, '导出审阅文档', os.path.join(self._last_dir, '双语审阅文档'), _REVIEW_FILTER)
        if not path:
            return
        if '.' not in os.path.basename(path):
            path += '.html'
        self._last_dir = os.path.dirname(path)
        try:
            report_render.write(path, report_adapters.from_bilingual_review(self._last_units))
        except (ValueError, ImportError) as e:
            self._log('出错了：%s' % e, 'error')
            return
        self._log('已导出审阅文档到 %s' % path, 'success')
