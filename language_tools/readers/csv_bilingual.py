"""Bilingual csv/tsv reader.

Encoding fallback order: utf-8-sig -> utf-8 -> gb18030 (see DESIGN.md
section 7.2). GB18030 rather than GBK for the final fallback: it's a
strict superset of GBK (same Chinese-Windows coverage, more besides) at
zero extra cost, and Excel-exported CSVs from Chinese Windows are often
not UTF-8 at all.
"""
import csv

from language_tools.readers._rowreader import looks_like_header, pick_src_tgt_columns, rows_to_pairs

ENCODINGS = ['utf-8-sig', 'utf-8', 'gb18030']


def _read_text(path):
    last_err = None
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                return f.read(), enc
        except UnicodeDecodeError as e:
            last_err = e
    raise ValueError('could not decode %s with any of %s: %s' % (path, ENCODINGS, last_err))


def read(path, delimiter=None, src_col_index=None, tgt_col_index=None, header=None, **opts):
    text, _enc = _read_text(path)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096]).delimiter
        except csv.Error:
            delimiter = ','

    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    if ncols < 2:
        raise ValueError('%s has fewer than 2 columns (delimiter=%r)' % (path, delimiter))

    data_rows = rows
    has_header = header if header is not None else looks_like_header(rows[0])
    if has_header:
        data_rows = rows[1:]

    s_idx, t_idx = pick_src_tgt_columns(ncols, src_col_index, tgt_col_index)
    return rows_to_pairs(data_rows, s_idx, t_idx, 'csv')
