"""Shared helpers for row-oriented bilingual readers (docx table layout,
xlsx, csv/tsv). All three have the same shape: rows of cells, need to guess
whether row 0 is a header, and need to pick a source/target column pair.
"""
import re


def looks_like_header(row):
    """Crude heuristic: header cells are short and don't end like sentences."""
    for cell in row:
        cell = (cell or '').strip()
        if not cell:
            continue
        if len(cell) > 20 or re.search(r'[.!?。！？]', cell):
            return False
    return True


def col_letter_to_index(letter):
    """'A' -> 0, 'B' -> 1, ... 'AA' -> 26."""
    letter = letter.strip().upper()
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord('A') + 1)
    return n - 1


def pick_src_tgt_columns(ncols, src_index=None, tgt_index=None):
    """Default convention shared by all row-oriented readers: 2 columns ->
    (0, 1); 3+ columns -> the last two, unless explicitly overridden."""
    if src_index is not None and tgt_index is not None:
        return src_index, tgt_index
    return (0, 1) if ncols == 2 else (ncols - 2, ncols - 1)


def rows_to_pairs(numbered_rows, s_idx, t_idx, warn_label):
    """Build ParagraphPair list from row data, warning on one-sided rows.

    ``numbered_rows`` is an iterable of ``(row_number, row)`` tuples, where
    ``row_number`` is the row's position in the *original* source (before
    any header/blank-row filtering the caller already did) -- so a warning
    like "row 5 missing translation" points at row 5 in the actual xlsx/
    csv/table the person opened, not row 5 of whatever survived filtering.
    Callers are responsible for producing that numbering; see
    xlsx_bilingual.py/csv_bilingual.py/docx_table.py for the shared pattern
    (number before filtering blanks, then optionally drop row 1 for a
    header without renumbering anything after it).

    Imports ParagraphPair lazily to avoid a circular import at module load.
    """
    from language_tools.model import ParagraphPair

    pairs, missing = [], []
    for row_number, row in numbered_rows:
        src_text = (row[s_idx] if s_idx < len(row) else '') or ''
        tgt_text = (row[t_idx] if t_idx < len(row) else '') or ''
        src_text, tgt_text = src_text.strip(), tgt_text.strip()
        if not src_text and not tgt_text:
            continue
        if not src_text or not tgt_text:
            missing.append(row_number)
            continue
        pairs.append(ParagraphPair(key=str(row_number), src_text=src_text, tgt_text=tgt_text))
    if missing:
        print('warning: %s rows with only one side filled, dropped: %s' % (warn_label, missing))
    return pairs
