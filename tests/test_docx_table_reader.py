from language_tools.align.aligner import align_paragraph_pairs
from language_tools.readers import docx, docx_table

from conftest import fixture_path


def _write_two_table_docx(path):
    """Minimal valid .docx whose body holds two qualifying bilingual
    tables (2 columns, one data row each). Built inline rather than
    shipped as a fixture blob -- _ooxml only reads word/document.xml, so
    the three zip entries below are the whole file.
    """
    import zipfile

    def tbl(en, zh):
        return ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>'
                '<w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc></w:tr></w:tbl>' % (en, zh))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        + tbl('First table sentence.', '第一张表的句子。')
        + tbl('Second table sentence.', '第二张表的句子。')
        + '</w:body></w:document>')
    with zipfile.ZipFile(str(path), 'w') as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        z.writestr('word/document.xml', document)


def _write_three_column_docx(path):
    """Minimal .docx with one 3-column table: EN | ZH | empty Notes.
    The default (last-two-columns) probe judges it on ZH + empty Notes and
    finds it unqualified, so only an explicit src=0/tgt=1 override can read
    it -- the docx-table column-override case from P2.
    """
    import zipfile

    def row(en, zh):
        return ('<w:tr>'
                '<w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>'
                '<w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>'
                '<w:tc><w:p/></w:tc>'
                '</w:tr>' % (en, zh))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:tbl>'
        + row('Hello there.', '你好。')
        + row('Good morning.', '早上好。')
        + '</w:tbl></w:body></w:document>')
    with zipfile.ZipFile(str(path), 'w') as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        z.writestr('word/document.xml', document)


def test_explicit_column_override_rescues_a_table_the_default_rejects(tmp_path):
    # P2 (docx-table row): read() qualified each table on the DEFAULT last-
    # two columns while extracting on the caller's override, so an explicit
    # src/tgt could never rescue a table the default deemed unqualified --
    # it raised 'No usable bilingual table found' despite valid EN/ZH data.
    path = tmp_path / 'three_col.docx'
    _write_three_column_docx(path)
    import pytest
    with pytest.raises(ValueError):
        docx_table.read(str(path))  # default (1,2)=ZH,empty Notes -> no table
    pairs = docx_table.read(str(path), src_col_index=0, tgt_col_index=1)
    assert [(p.src_text, p.tgt_text) for p in pairs] == [
        ('Hello there.', '你好。'), ('Good morning.', '早上好。')]


def test_read_collects_every_qualifying_table_not_just_the_first(tmp_path):
    # Regression: read() returned on the first table that produced pairs
    # and silently dropped the rest of the document -- while
    # confidence() scored ">=2 qualifying tables" as its strongest
    # positive signal (0.95), so the two views actively disagreed.
    path = tmp_path / 'two_tables.docx'
    _write_two_table_docx(path)
    assert docx_table.confidence(str(path)) == 0.95  # the 2-table signal
    pairs = docx_table.read(str(path))
    texts = [p.src_text for p in pairs]
    assert texts == ['First table sentence.', 'Second table sentence.']
    assert [p.tgt_text for p in pairs] == ['第一张表的句子。', '第二张表的句子。']
    # Row numbers restart per table -- prefixed from table 2 on so
    # diagnostic keys stay unique ("row 1" would otherwise be ambiguous).
    assert [p.key for p in pairs] == ['1', 't2:1']


def test_auto_detect_reads_both_tables(tmp_path):
    # The same data loss applied through docx.read()'s auto-detect path.
    path = tmp_path / 'two_tables.docx'
    _write_two_table_docx(path)
    pairs = docx.read(str(path))
    assert len(pairs) == 2


def test_table_layout_basic():
    pairs = docx_table.read(fixture_path('table_layout.docx'))
    assert len(pairs) == 3
    assert pairs[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert pairs[0].tgt_text == '史密斯博士上午9点到达。'


def test_table_layout_language_direction_reversal():
    pairs = docx_table.read(fixture_path('table_layout_reversed.docx'))
    assert len(pairs) == 1
    units, _ = align_paragraph_pairs(pairs, 'zh-CN', 'en-US')
    assert len(units) == 2
    assert units[0].tgt_text == 'He left at 3pm while it was raining.'
    assert units[1].tgt_text == 'The taxi was late.'


def test_table_confidence_high_for_table_layout_doc():
    # table_layout.docx has a 3-row bilingual table -> strong positive
    # signal, should score >= 0.85 (specifically 0.95 with 4+ populated
    # rows, or 0.85 with fewer; either way above numbered/alternating).
    score = docx_table.confidence(fixture_path('table_layout.docx'))
    assert score >= 0.85
    # And it should beat the other readers' confidence on the same doc
    from language_tools.readers import docx_alternating, docx_numbered
    assert score > docx_numbered.confidence(fixture_path('table_layout.docx'))
    assert score > docx_alternating.confidence(fixture_path('table_layout.docx'))


def test_table_confidence_zero_for_non_table_doc():
    # basic.docx is the numbered layout, no qualifying tables -> table
    # confidence should be 0.0 (not "small but non-zero").
    assert docx_table.confidence(fixture_path('basic.docx')) == 0.0


def test_auto_detect_picks_table_layout_when_table_present():
    pairs = docx.read(fixture_path('table_layout.docx'))
    assert len(pairs) == 3


def test_auto_detect_falls_back_to_numbered_layout():
    pairs = docx.read(fixture_path('basic.docx'))
    assert len(pairs) == 3
    # numbered-layout paragraphs, not table cells
    assert pairs[0].src_text.startswith('Dr. Smith arrived')


def test_explicit_layout_override():
    pairs = docx.read(fixture_path('table_layout.docx'), layout='table')
    assert len(pairs) == 3
    import pytest
    with pytest.raises(ValueError):
        docx.read(fixture_path('table_layout.docx'), layout='numbered')


def test_sample_column_text_returns_src_and_tgt_samples():
    src_sample, tgt_sample = docx_table.sample_column_text(fixture_path('table_layout.docx'))
    assert 'Dr. Smith arrived at 9 a.m.' in src_sample
    assert '史密斯博士上午9点到达' in tgt_sample


def test_sample_column_text_empty_when_no_qualifying_table():
    src_sample, tgt_sample = docx_table.sample_column_text(fixture_path('basic.docx'))
    assert (src_sample, tgt_sample) == ('', '')


def test_sample_column_text_caps_at_max_chars():
    src_sample, _ = docx_table.sample_column_text(fixture_path('table_layout.docx'), max_chars=10)
    assert len(src_sample) <= 10


def test_iter_body_tables_with_merge_flags_counts_merged_header_cell():
    from language_tools.readers._ooxml import iter_body_tables_with_merge_flags
    tables = list(iter_body_tables_with_merge_flags(fixture_path('table_merged_header.docx')))
    assert len(tables) == 1
    rows, merged = tables[0]
    assert merged == 1
    assert len(rows) == 5  # merged header row + 4 data rows


def test_iter_body_tables_with_merge_flags_zero_for_clean_table():
    from language_tools.readers._ooxml import iter_body_tables_with_merge_flags
    tables = list(iter_body_tables_with_merge_flags(fixture_path('table_layout.docx')))
    assert all(merged == 0 for _rows, merged in tables)
