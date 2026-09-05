from language_tools import api
from language_tools.writers import csv_writer
from language_tools.corpus_readers import sdltm_reader

from conftest import fixture_path


def test_min_confidence_filters_sdltm_but_csv_keeps_everything(tmp_path):
    # numbering_mismatch.docx has real content -- add a duplicate scenario
    # isn't needed here, empty/length-ratio flags aren't naturally present
    # in this fixture, so just confirm the plumbing: min_confidence=0 (off)
    # exports everything, and a a very high threshold excludes everything
    # from sdltm/tmx while csv still lists every unit.
    out_base = str(tmp_path / 'out')
    result = api.convert(fixture_path('basic.docx'), out_base, src_lang='en-US', tgt_lang='zh-CN',
                          min_confidence=0.0)
    assert result['exported'] == result['units']

    out_base2 = str(tmp_path / 'out2')
    result2 = api.convert(fixture_path('basic.docx'), out_base2, src_lang='en-US', tgt_lang='zh-CN',
                           min_confidence=1.01)  # impossible to meet -- confidence maxes at 1.0
    assert result2['exported'] == 0
    sdltm_units = sdltm_reader.read(out_base2 + '.sdltm')
    assert len(sdltm_units) == 0

    with open(out_base2 + '.csv', encoding='utf-8-sig') as f:
        csv_rows = f.readlines()
    assert len(csv_rows) - 1 == result2['units']  # header + all units, unfiltered


def test_min_confidence_implies_qa_columns_in_csv(tmp_path):
    out_base = str(tmp_path / 'out')
    api.convert(fixture_path('basic.docx'), out_base, src_lang='en-US', tgt_lang='zh-CN',
                min_confidence=0.5)
    with open(out_base + '.csv', encoding='utf-8-sig') as f:
        header = f.readline().strip()
    assert 'confidence' in header
