"""Cheap, read-only pre-checks for a DOCX file before trusting it to the
real conversion pipeline (DESIGN.md section 15.2, "批量预检"). Nothing
here writes anything or extracts the actual bilingual pairs -- that's
what ``api.convert()``/the readers themselves are for. This only
surfaces the handful of structural/heuristic signals a human should
glance at before running a whole batch through auto-detection unattended:

- **Layout confidence**: is auto-detect (``readers/docx.py``) actually
  sure, or guessing? Reuses each reader's own ``confidence()`` directly
  rather than re-deriving a score -- same numbers ``docx.read()`` itself
  would use to pick a layout.
- **Merged cells** / **empty tables**: either can silently corrupt a
  table-layout read (a horizontally-merged header row, or a decorative
  empty table sitting where the real content table was expected) without
  raising an error -- the reader just extracts something plausible-
  looking but wrong. Reuses ``_ooxml.iter_body_tables_with_merge_flags()``.
- **Language-direction anomaly**: does the picked source/target column
  text actually look like the declared languages? Reuses the exact
  declared-lang-vs-content-sniff heuristic ``align/splitters.py``'s
  ``pick_splitter()`` already uses at split time (``is_cjk_lang()`` +
  ``looks_cjk()``) -- same real bug DESIGN.md's Phase 0 notes ("正向/
  反向语言方向") this project has hit before, just caught earlier, before
  a whole batch gets converted with the columns swapped.

``check()`` returns one dict per file; nothing here decides pass/fail --
that's left to the caller (CLI exit code, GUI row color), since e.g. "one
merged cell" is a heads-up worth a glance, not necessarily a blocker.
"""
from language_tools.align.splitters import is_cjk_lang, looks_cjk
from language_tools.readers import docx_alternating, docx_numbered, docx_table
from language_tools.readers._ooxml import iter_body_tables_with_merge_flags

# Below this, the best-scoring reader isn't a strong signal -- see each
# reader's own confidence() docstring for its tiering (0.85 is the
# "strong positive signal" tier every reader uses); auto-detect is
# guessing, not confident, and the file is worth a manual --layout check.
_LOW_CONFIDENCE_THRESHOLD = 0.85


def check(path, src_lang=None, tgt_lang=None):
    """Run every preflight check against one DOCX file.

    ``src_lang``/``tgt_lang`` are optional -- the direction check is
    skipped (not reported as an error) when they're not supplied, since
    preflight can reasonably run before the language pair is chosen.
    """
    scores = {
        'table': docx_table.confidence(path),
        'numbered': docx_numbered.confidence(path),
        'alternating': docx_alternating.confidence(path),
    }
    best_layout, best_score = max(scores.items(), key=lambda kv: kv[1])
    layout_ambiguous = best_score < _LOW_CONFIDENCE_THRESHOLD

    merged_cell_count = 0
    empty_table_count = 0
    for rows, merged in iter_body_tables_with_merge_flags(path):
        merged_cell_count += merged
        if rows and not any(cell.strip() for row in rows for cell in row):
            empty_table_count += 1

    direction_issues = []
    if src_lang or tgt_lang:
        src_sample, tgt_sample = docx_table.sample_column_text(path)
        for label, lang, sample in (('原文', src_lang, src_sample), ('译文', tgt_lang, tgt_sample)):
            if lang and sample and is_cjk_lang(lang) != looks_cjk(sample):
                direction_issues.append(
                    '%s列内容%s，但声明的语言是 %s，方向可能反了' % (
                        label, '看起来是中文/CJK' if looks_cjk(sample) else '看起来不是中文/CJK', lang))

    issues = []
    if layout_ambiguous:
        issues.append('版式置信度偏低（最佳猜测 %s = %.2f），建议用 --layout 手动指定确认'
                       % (best_layout, best_score))
    if merged_cell_count:
        issues.append('检测到 %d 个合并单元格，表格版式提取结果可能不准确' % merged_cell_count)
    if empty_table_count:
        issues.append('检测到 %d 个空表格' % empty_table_count)
    issues.extend(direction_issues)

    return {
        'layout_confidence': scores,
        'best_layout': best_layout,
        'best_score': best_score,
        'layout_ambiguous': layout_ambiguous,
        'merged_cell_count': merged_cell_count,
        'empty_table_count': empty_table_count,
        'direction_issues': direction_issues,
        'issues': issues,
    }
