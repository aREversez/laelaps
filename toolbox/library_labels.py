"""Catalog registration for labels that ``language_tools`` owns.

``align.aligner.MOVE_LABELS`` and ``qa.ISSUE_LABELS`` hand the GUI ready-made
Chinese display labels. They stay Chinese in the library on purpose -- the
CLI, the CSV/HTML/PDF exports and the tests all consume them as-is, and the
library must not depend on the GUI's language setting -- so the pages
translate them at display time (``tr(align_report.move_label(code))``).
That is a lookup of a non-literal, which the catalog completeness check in
tests/test_toolbox_i18n.py can't see; listing the labels here with
``tr_noop()`` makes them ordinary catalog keys, and the same test fails when
the library gains a label that is not listed here.
"""
from toolbox.i18n import tr_noop

LIBRARY_LABELS = (
    # align.aligner.MOVE_LABELS
    tr_noop('一一对应'),
    tr_noop('合并（2→1）'),
    tr_noop('拆分（1→2）'),
    tr_noop('合并+拆分（2→2）'),
    tr_noop('合并+拆分（3→2）'),
    tr_noop('合并+拆分（2→3）'),
    tr_noop('拆分（1→3）'),
    tr_noop('合并（3→1）'),
    tr_noop('合并+拆分（3→3）'),
    tr_noop('跳过（原文无对应）'),
    tr_noop('跳过（译文无对应）'),
    # qa.ISSUE_LABELS
    tr_noop('原文为空'),
    tr_noop('译文为空'),
    tr_noop('长度比异常'),
    tr_noop('数字不匹配'),
    tr_noop('占位符不匹配'),
    tr_noop('URL 不匹配'),
    tr_noop('标签不匹配'),
    tr_noop('括号/引号不成对'),
    tr_noop('全半角混用'),
    tr_noop('首尾空格'),
    tr_noop('原文冲突'),
    tr_noop('译文冲突'),
)
