"""Bilingual DOCX reader for the table layout: a 2+ column table where each
row is one source/target paragraph pair (as opposed to docx_numbered.py's
"[1]..[N] source block, then [1]..[N] target block" convention).

Column selection and header detection are shared with the xlsx/csv readers
via _rowreader.py -- all three are "rows of cells" readers underneath.
"""
from language_tools.readers._ooxml import iter_body_tables
from language_tools.readers._rowreader import looks_like_header, pick_src_tgt_columns, rows_to_pairs


def _qualifying_tables(path):
    """Yield each <w:tbl> in the document that has >=2 columns and at
    least one fully-populated data row (both target columns non-empty).

    Used by both confidence() and read(): confidence() counts qualifying
    tables to score how "table-shaped" the document is, read() picks the
    first qualifying table to extract pairs from. Sharing the predicate
    keeps the two views of "what counts as a bilingual table" in sync.
    """
    for rows in iter_body_tables(path):
        if not rows:
            continue
        ncols = max((len(r) for r in rows), default=0)
        if ncols < 2:
            continue
        has_header = looks_like_header(rows[0])
        data_rows = rows[1:] if has_header else rows
        # A row is "fully populated" if both picked columns have non-empty
        # text. Default picks the last two columns (see pick_src_tgt_columns);
        # we don't honor src_col_index/tgt_col_index here because confidence()
        # is meant to be a cheap probe without parsing CLI overrides. This
        # is conservative -- a user who overrides columns for read() is
        # expected to also pass --layout table, skipping auto-detection.
        s_idx, t_idx = pick_src_tgt_columns(ncols, None, None)
        qualified = False
        for r in data_rows:
            src = (r[s_idx] if s_idx < len(r) else '').strip() if r else ''
            tgt = (r[t_idx] if t_idx < len(r) else '').strip() if r else ''
            if src and tgt:
                qualified = True
                break
        if qualified:
            yield rows


def confidence(path):
    """Return a 0..1 score for how strongly this document looks like a
    bilingual table layout. Scoring rationale (kept deliberately simple
    so the formula is auditable):

    - 0 candidates -> 0.0 (no qualifying table at all)
    - 1 qualifying table with >=2 fully-populated data rows -> 0.85
      (strong positive signal; not 1.0 because a single short table
      could still be a stray layout element of a non-bilingual doc)
    - 1 qualifying table with >=4 fully-populated data rows -> 0.95
      (the longer the table, the less likely it's coincidental)
    - >=2 qualifying tables -> 0.95 (multiple bilingual tables, very
      strong signal)
    """
    qualifying = list(_qualifying_tables(path))
    if not qualifying:
        return 0.0
    if len(qualifying) >= 2:
        return 0.95
    rows = qualifying[0]
    has_header = looks_like_header(rows[0])
    data_rows = rows[1:] if has_header else rows
    ncols = max((len(r) for r in rows), default=0)
    s_idx, t_idx = pick_src_tgt_columns(ncols, None, None)
    populated = sum(
        1 for r in data_rows
        if r and (r[s_idx] if s_idx < len(r) else '').strip()
        and (r[t_idx] if t_idx < len(r) else '').strip()
    )
    return 0.95 if populated >= 4 else 0.85


def read(path, src_col_index=None, tgt_col_index=None, header=None, **opts):
    for rows in _qualifying_tables(path):
        pairs = _read_table(rows, src_col_index, tgt_col_index, header)
        if pairs:
            return pairs
    raise ValueError('No usable bilingual table found (need a table with '
                      '>=2 columns and at least one fully-populated data row).')


def _read_table(rows, src_col_index, tgt_col_index, header):
    if not rows:
        return []
    ncols = max((len(r) for r in rows), default=0)
    if ncols < 2:
        return []

    numbered_rows = list(enumerate(rows, 1))
    has_header = header if header is not None else looks_like_header(rows[0])
    if has_header:
        numbered_rows = numbered_rows[1:]

    s_idx, t_idx = pick_src_tgt_columns(ncols, src_col_index, tgt_col_index)
    return rows_to_pairs(numbered_rows, s_idx, t_idx, 'table')
