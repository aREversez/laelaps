"""Bilingual xlsx reader.

Uses openpyxl as a normal dependency rather than hand-rolling zip+XML
parsing (see DESIGN.md section 7.1): real-world bilingual xlsx exports
routinely have merged cells, inline rich text, and date-typed cells that a
minimal parser would get wrong, and openpyxl is pure Python with no
PyInstaller packaging cost.

``import openpyxl`` is deferred to inside ``read()`` rather than at module
level: openpyxl pulls in its chart/pivot/drawing submodules on import,
which is measurably slow (hundreds of ms, worse under antivirus real-time
scanning on Windows than in a quick Linux check) -- and this module gets
imported at app startup regardless of which tool page a person actually
opens, since ``toolbox.registry.discover()`` imports every ``toolbox/
tools/*/page.py`` up front to build the sidebar (see that module's
docstring). Paying that cost only when an xlsx file is actually read,
rather than on every launch whether or not xlsx ever comes up in the
session, is the difference between a slow app and a slow xlsx read.

Column selection and header detection mirror docx_table.py via
_rowreader.py. Column overrides use Excel-style letters ('A', 'B', ...).
"""
from language_tools.readers._rowreader import (
    col_letter_to_index, looks_like_header, pick_src_tgt_columns, rows_to_pairs,
)


def read(path, sheet=None, src_col=None, tgt_col=None, header=None, **opts):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = [['' if c is None else str(c).strip() for c in row]
                for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()

    # Number rows by their real position before dropping blanks, so a
    # "missing translation" warning points at the actual xlsx row the
    # person would see in Excel, not a position among survivors.
    numbered_rows = [(i, row) for i, row in enumerate(rows, 1) if any(c for c in row)]
    if not numbered_rows:
        return []
    ncols = max(len(row) for _, row in numbered_rows)
    if ncols < 2:
        raise ValueError('xlsx sheet has fewer than 2 non-empty columns')

    data_rows = numbered_rows
    has_header = header if header is not None else looks_like_header(numbered_rows[0][1])
    if has_header:
        data_rows = numbered_rows[1:]

    src_index = col_letter_to_index(src_col) if src_col is not None else None
    tgt_index = col_letter_to_index(tgt_col) if tgt_col is not None else None
    s_idx, t_idx = pick_src_tgt_columns(ncols, src_index, tgt_index)
    return rows_to_pairs(data_rows, s_idx, t_idx, 'xlsx')
