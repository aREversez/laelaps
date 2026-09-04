from language_tools import qa
from language_tools.model import TranslationUnit


def _tu(src, tgt):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt)


def test_flags_empty_source_and_target():
    units = [_tu('', 'has target'), _tu('has source', '')]
    qa.run(units, length_ratio=1.0)
    assert 'EMPTY_SOURCE' in units[0].meta['qa_issues']
    assert 'EMPTY_TARGET' in units[1].meta['qa_issues']


def test_flags_duplicate_tu():
    units = [_tu('Same text.', '相同文本。'), _tu('Same text.', '相同文本。'), _tu('Different.', '不同。')]
    qa.run(units, length_ratio=1.0)
    assert 'DUPLICATE_TU' in units[0].meta['qa_issues']
    assert 'DUPLICATE_TU' in units[1].meta['qa_issues']
    assert 'DUPLICATE_TU' not in units[2].meta['qa_issues']


def test_flags_number_mismatch():
    units = [_tu('We shipped 42 units.', '我们发货了43个单位。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_no_number_mismatch_when_numbers_match():
    units = [_tu('We shipped 42 units.', '我们发货了42个单位。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_flags_length_ratio_outlier():
    # length_ratio says target should be roughly src_len/1.0; a target
    # 1/10th the expected length should trip the outlier check.
    units = [_tu('This is a reasonably long English sentence for testing.', '短。')]
    qa.run(units, length_ratio=1.0)
    assert 'LENGTH_RATIO_OUTLIER' in units[0].meta['qa_issues']


def test_confidence_is_one_when_no_issues():
    units = [_tu('Clean pair.', '干净的句对。')]
    qa.run(units, length_ratio=1.0)
    assert units[0].meta['qa_issues'] == []
    assert units[0].meta['qa_confidence'] == 1.0


def test_csv_writer_qa_columns_opt_in(tmp_path):
    from language_tools.writers import csv_writer

    units = [_tu('', 'orphan target')]
    qa.run(units, length_ratio=1.0)
    path = str(tmp_path / 'out.csv')

    csv_writer.write(path, units)  # default: no QA columns
    with open(path, encoding='utf-8-sig') as f:
        header = f.readline().strip()
    assert header == 'No,EN,ZH'

    csv_writer.write(path, units, include_qa=True)
    with open(path, encoding='utf-8-sig') as f:
        header = f.readline().strip()
        row = f.readline().strip()
    assert header == 'No,EN,ZH,confidence,status,issues'
    assert 'EMPTY_SOURCE' in row
