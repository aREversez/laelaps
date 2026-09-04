"""Phase 0/1 regression baseline.

Golden files under fixtures/expected/*.csv were captured by running the
seed script (reference/docx_to_sdltm_v1.py in the design-doc handoff) on
the matching fixtures/docx/*.docx files. CSV has no embedded guid/timestamp
so it's the one format that can be compared byte-for-byte (see DESIGN.md
section 5/8 for why sdltm/tmx cannot be). sdltm/tmx are checked here for
semantic equivalence instead: same (src_lang, tgt_lang, src_text, tgt_text)
per unit, ignoring guid/creation timestamps.
"""
import re
import sqlite3
import xml.etree.ElementTree as ET

from language_tools import api
from language_tools.writers.sdltm_writer import unesc

from conftest import expected_path, fixture_path

CASES = [
    ('basic.docx', 'basic.csv', 'en-US', 'zh-CN'),
    ('numbering_mismatch.docx', 'numbering_mismatch.csv', 'en-US', 'zh-CN'),
    ('reversed_direction.docx', 'reversed_direction.csv', 'zh-CN', 'en-US'),
]


def _read_sdltm_semantic(path):
    con = sqlite3.connect(path)
    rows = con.execute('SELECT source_segment, target_segment FROM translation_units').fetchall()
    con.close()
    val_re = re.compile(r'<Value>(.*?)</Value>', re.S)

    def extract(seg_xml_text):
        m = val_re.search(seg_xml_text)
        return unesc(m.group(1)) if m else ''

    return [(extract(s), extract(t)) for s, t in rows]


def _read_tmx_semantic(path):
    ns = {}
    tree = ET.parse(path)
    units = []
    for tu in tree.getroot().find('body').findall('tu'):
        segs = [tuv.find('seg').text or '' for tuv in tu.findall('tuv')]
        units.append(tuple(segs))
    return units


def _read_csv_texts(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [line for line in f]


import pytest


@pytest.mark.parametrize('docx_name,csv_name,src,tgt', CASES)
def test_csv_byte_identical_to_golden(tmp_path, docx_name, csv_name, src, tgt):
    out_base = str(tmp_path / 'out')
    api.convert(fixture_path(docx_name), out_base, src_lang=src, tgt_lang=tgt)
    got = _read_csv_texts(out_base + '.csv')
    want = _read_csv_texts(expected_path(csv_name))
    assert got == want


@pytest.mark.parametrize('docx_name,csv_name,src,tgt', CASES)
def test_sdltm_semantically_matches_csv(tmp_path, docx_name, csv_name, src, tgt):
    out_base = str(tmp_path / 'out')
    api.convert(fixture_path(docx_name), out_base, src_lang=src, tgt_lang=tgt)
    sdltm_units = _read_sdltm_semantic(out_base + '.sdltm')
    csv_rows = _read_csv_texts(out_base + '.csv')[1:]  # skip header
    # csv keeps empty-pair rows, sdltm drops them -- compare the non-empty subset
    import csv as csv_mod
    import io
    reader = csv_mod.reader(io.StringIO(''.join(csv_rows)))
    csv_units = [(r[1], r[2]) for r in reader if r[1].strip() and r[2].strip()]
    assert sdltm_units == csv_units


@pytest.mark.parametrize('docx_name,csv_name,src,tgt', CASES)
def test_tmx_semantically_matches_csv(tmp_path, docx_name, csv_name, src, tgt):
    out_base = str(tmp_path / 'out')
    api.convert(fixture_path(docx_name), out_base, src_lang=src, tgt_lang=tgt)
    tmx_units = _read_tmx_semantic(out_base + '.tmx')
    csv_rows = _read_csv_texts(out_base + '.csv')[1:]
    import csv as csv_mod
    import io
    reader = csv_mod.reader(io.StringIO(''.join(csv_rows)))
    csv_units = [(r[1], r[2]) for r in reader if r[1].strip() and r[2].strip()]
    assert tmx_units == csv_units
