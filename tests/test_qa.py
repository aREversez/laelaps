from language_tools import qa
from language_tools.model import TranslationUnit


def _tu(src, tgt):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt)


def test_flags_empty_source_and_target():
    units = [_tu('', 'has target'), _tu('has source', '')]
    qa.run(units, length_ratio=1.0)
    assert 'EMPTY_SOURCE' in units[0].meta['qa_issues']
    assert 'EMPTY_TARGET' in units[1].meta['qa_issues']


def test_exact_duplicate_tu_is_allowed():
    # Repeated boilerplate/UI strings translated the same way every time
    # is normal TM content (e.g. "Click OK." -> "点击确定。" appearing many
    # times across a document), not a quality problem -- flagging it would
    # just be noise.
    units = [_tu('Same text.', '相同文本。'), _tu('Same text.', '相同文本。'), _tu('Different.', '不同。')]
    qa.run(units, length_ratio=1.0)
    assert units[0].meta['qa_issues'] == []
    assert units[1].meta['qa_issues'] == []
    assert units[2].meta['qa_issues'] == []


def test_flags_source_conflict_when_same_source_has_different_targets():
    # The same source text translated two different ways is a real
    # inconsistency worth a human's attention.
    units = [_tu('Click OK.', '点击确定。'), _tu('Click OK.', '单击确定')]
    qa.run(units, length_ratio=1.0)
    assert 'SOURCE_CONFLICT' in units[0].meta['qa_issues']
    assert 'SOURCE_CONFLICT' in units[1].meta['qa_issues']


def test_flags_target_conflict_when_same_target_has_different_sources():
    units = [_tu('Click OK.', '点击确定。'), _tu('Press OK.', '点击确定。')]
    qa.run(units, length_ratio=1.0)
    assert 'TARGET_CONFLICT' in units[0].meta['qa_issues']
    assert 'TARGET_CONFLICT' in units[1].meta['qa_issues']


def test_empty_source_or_target_does_not_also_spuriously_flag_conflict():
    # All-empty src_text units would otherwise all "conflict" with each
    # other under a naive source->targets grouping keyed on ''.
    units = [_tu('', 'target one'), _tu('', 'target two')]
    qa.run(units, length_ratio=1.0)
    assert 'SOURCE_CONFLICT' not in units[0].meta['qa_issues']
    assert 'SOURCE_CONFLICT' not in units[1].meta['qa_issues']


def test_flags_number_mismatch():
    units = [_tu('We shipped 42 units.', '我们发货了43个单位。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_no_number_mismatch_when_numbers_match():
    units = [_tu('We shipped 42 units.', '我们发货了42个单位。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_thousands_separator_variation():
    # "$1,000" vs "1000" -- the old raw-digit regex saw {1,000} vs {1000}
    # and false-fired. After normalization both are {1000}.
    units = [_tu('Revenue: $1,000 total.', '收入总计1000。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_decimal_separator_variation():
    # "1.5" (en) vs "1,5" (some European locales) -- both normalize to "1.5".
    units = [_tu('The rate is 1.5 percent.', '比率为1,5%。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_trailing_zero_decimal():
    # "1.20" vs "1.2" -- same number, different formatting. Old regex
    # saw {"1.20"} vs {"1.2"} and false-fired. Normalization strips
    # trailing zeros so both become "1.2".
    units = [_tu('Version 1.20 released.', '版本1.2发布。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_currency_prefix_variation():
    # "USD 50" vs "$50" -- both normalize to {50} after currency stripping.
    units = [_tu('Price: USD 50 per unit.', '每件价格$50。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_number_mismatch_still_fires_for_real_missing_number():
    # Sanity: normalization shouldn't make the check miss actual mismatches.
    # "42 units" vs "43 个" is a real difference.
    units = [_tu('We shipped 42 units in 2024.', '我们2024年发货了43个。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_number_mismatch_still_fires_for_extra_number_in_translation():
    # Translation added a number the source doesn't have.
    units = [_tu('See chapter 5.', '参见第5章第3节。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


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
