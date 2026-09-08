from conftest import tmx_path

from language_tools import qa
from language_tools.corpus_readers import tmx_reader
from language_tools.model import InlineNode, TranslationUnit


def _tu(src, tgt):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt)


def _tu_markup(src, tgt, src_markup=None, tgt_markup=None):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt,
                            src_markup=src_markup, tgt_markup=tgt_markup)


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


def test_placeholder_mismatch_flags_renamed_variable():
    units = [_tu('Welcome, {name}!', '欢迎，{名字}！')]
    qa.run(units, length_ratio=1.0)
    assert 'PLACEHOLDER_MISMATCH' in units[0].meta['qa_issues']


def test_no_placeholder_mismatch_when_token_matches():
    units = [_tu('Welcome, {name}!', '欢迎，{name}！')]
    qa.run(units, length_ratio=1.0)
    assert 'PLACEHOLDER_MISMATCH' not in units[0].meta['qa_issues']


def test_placeholder_mismatch_flags_dropped_printf_style_token():
    units = [_tu('Found %d results.', '找到了结果。')]
    qa.run(units, length_ratio=1.0)
    assert 'PLACEHOLDER_MISMATCH' in units[0].meta['qa_issues']


def test_no_placeholder_mismatch_when_neither_side_has_one():
    units = [_tu('Plain sentence.', '普通句子。')]
    qa.run(units, length_ratio=1.0)
    assert 'PLACEHOLDER_MISMATCH' not in units[0].meta['qa_issues']


def test_url_mismatch_flags_dropped_url():
    units = [_tu('See https://example.com/docs for details.', '详情见文档。')]
    qa.run(units, length_ratio=1.0)
    assert 'URL_MISMATCH' in units[0].meta['qa_issues']


def test_no_url_mismatch_when_url_matches():
    units = [_tu('See https://example.com/docs for details.', '详情见 https://example.com/docs。')]
    qa.run(units, length_ratio=1.0)
    assert 'URL_MISMATCH' not in units[0].meta['qa_issues']


def test_url_mismatch_flags_altered_url():
    # Same domain, different path -- a translator (or a bad find/replace)
    # pointed the link somewhere else.
    units = [_tu('See https://example.com/docs for details.',
                 '详情见 https://example.com/other。')]
    qa.run(units, length_ratio=1.0)
    assert 'URL_MISMATCH' in units[0].meta['qa_issues']


def test_tag_mismatch_flags_dropped_formatting():
    src_markup = [InlineNode(kind='text', content='Please '),
                  InlineNode(kind='tag', content='<bpt i="1">&lt;b&gt;</bpt>'),
                  InlineNode(kind='text', content='save'),
                  InlineNode(kind='tag', content='<ept i="1">&lt;/b&gt;</ept>'),
                  InlineNode(kind='text', content=' your work.')]
    units = [_tu_markup('Please save your work.', '请保存您的工作。', src_markup=src_markup)]
    qa.run(units, length_ratio=1.0)
    assert 'TAG_MISMATCH' in units[0].meta['qa_issues']


def test_no_tag_mismatch_when_neither_side_has_markup():
    units = [_tu_markup('Plain sentence.', '普通句子。')]
    qa.run(units, length_ratio=1.0)
    assert 'TAG_MISMATCH' not in units[0].meta['qa_issues']


def test_no_tag_mismatch_when_tag_reordered_but_counts_match():
    # Translator moved the bold span relative to surrounding words -- a
    # normal target-language word-order adjustment, not a defect. Only
    # tag *type counts* are compared, not position.
    src_markup = [InlineNode(kind='tag', content='<bpt i="1">&lt;b&gt;</bpt>'),
                  InlineNode(kind='text', content='OK'),
                  InlineNode(kind='tag', content='<ept i="1">&lt;/b&gt;</ept>'),
                  InlineNode(kind='text', content=' now')]
    tgt_markup = [InlineNode(kind='text', content='现在 '),
                  InlineNode(kind='tag', content='<bpt i="1">&lt;b&gt;</bpt>'),
                  InlineNode(kind='text', content='确定'),
                  InlineNode(kind='tag', content='<ept i="1">&lt;/b&gt;</ept>')]
    units = [_tu_markup('OK now', '现在确定', src_markup=src_markup, tgt_markup=tgt_markup)]
    qa.run(units, length_ratio=1.0)
    assert 'TAG_MISMATCH' not in units[0].meta['qa_issues']


def test_tag_mismatch_flags_extra_tag_on_target_side():
    tgt_markup = [InlineNode(kind='tag', content='<hi>已经</hi>'),
                  InlineNode(kind='text', content='准备就绪')]
    units = [_tu_markup('Ready.', '已经准备就绪。', tgt_markup=tgt_markup)]
    qa.run(units, length_ratio=1.0)
    assert 'TAG_MISMATCH' in units[0].meta['qa_issues']


def test_inline_markup_fixture_end_to_end():
    # Real TMX with hand-written bpt/ept/ph/hi inline tags, read through
    # the actual tmx_reader (not hand-built InlineNode lists) -- exercises
    # the real parse path the checks above assume.
    units = tmx_reader.read(tmx_path('inline_markup_qa.tmx'))
    qa.run(units, length_ratio=1.0)
    assert len(units) == 8

    # tu 1: reordered bold span, same tag counts -> no TAG_MISMATCH
    assert 'TAG_MISMATCH' not in units[0].meta['qa_issues']
    # tu 2: target dropped the bold formatting entirely
    assert 'TAG_MISMATCH' in units[1].meta['qa_issues']
    # tu 3: target added a <hi> span the source doesn't have
    assert 'TAG_MISMATCH' in units[2].meta['qa_issues']
    # tu 4: matching <ph> placeholder tag on both sides
    assert 'TAG_MISMATCH' not in units[3].meta['qa_issues']
    # tu 5: matching text placeholder token
    assert 'PLACEHOLDER_MISMATCH' not in units[4].meta['qa_issues']
    # tu 6: translator renamed the placeholder variable
    assert 'PLACEHOLDER_MISMATCH' in units[5].meta['qa_issues']
    # tu 7: URL preserved
    assert 'URL_MISMATCH' not in units[6].meta['qa_issues']
    # tu 8: URL dropped
    assert 'URL_MISMATCH' in units[7].meta['qa_issues']


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
