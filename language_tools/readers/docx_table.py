"""Bilingual DOCX reader for the table layout: a 2+ column table where each
row is one source/target paragraph pair (as opposed to docx_numbered.py's
"[1]..[N] source block, then [1]..[N] target block" convention).

Column selection and header detection are shared with the xlsx/csv readers
via _rowreader.py -- all three are "rows of cells" readers underneath.
"""
from language_tools.readers._ooxml import iter_body_tables
from language_tools.readers._rowreader import looks_like_header, pick_src_tgt_columns, rows_to_pairs


def read(path, src_col_index=None, tgt_col_index=None, header=None, **opts):
    for table in iter_body_tables(path):
        pairs = _read_table(table, src_col_index, tgt_col_index, header)
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

    data_rows = rows
    has_header = header if header is not None else looks_like_header(rows[0])
    if has_header:
        data_rows = rows[1:]

    s_idx, t_idx = pick_src_tgt_columns(ncols, src_col_index, tgt_col_index)
    return rows_to_pairs(data_rows, s_idx, t_idx, 'table')
