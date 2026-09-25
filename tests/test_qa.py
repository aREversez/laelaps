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


def test_no_number_mismatch_for_month_name_to_numeric_month():
    # "September" (no digits at all) vs "9月" -- both express month 9.
    # Old raw-digit-only extraction saw {} vs {"9"} and false-fired.
    units = [_tu('Sales grew in September.', '销售额在9月增长。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_abbreviated_month_name():
    units = [_tu('Sept. 2024 report.', '2024年9月报告。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_number_mismatch_still_fires_for_different_month():
    units = [_tu('Sales grew in September.', '销售额在10月增长。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_month_name_expansion_does_not_misfire_on_modal_verb_may():
    # "May" is deliberately excluded from the month table -- it collides
    # with the common modal verb. A wrong expansion here (treating "may"
    # as month 5) would inject a spurious digit and could false-fire
    # NUMBER_MISMATCH against a target with no corresponding "5".
    units = [_tu('You may proceed.', '您可以继续。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_month_name_expansion_does_not_misfire_on_lowercase_march():
    # Lowercase "march" (the noun/verb, e.g. a protest march) must not be
    # treated as the month -- only case-sensitive "March" is.
    units = [_tu('The march continued for hours.', '游行持续了几个小时。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_billion_to_yi():
    # "$350bn" vs "3500亿美元" -- same value (350e9 == 3500e8), different
    # base/scale. Old bare-digit comparison saw {350} vs {3500}.
    units = [_tu('Revenue reached $350bn last year.', '去年收入达到3500亿美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_fractional_billion_to_yi():
    units = [_tu('The deal is worth $1.5bn.', '这笔交易价值15亿美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_million_to_wan():
    units = [_tu('We raised $2 million.', '我们筹集了200万美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_no_number_mismatch_for_trn_to_wanyi():
    # "$4trn" vs "4万亿美元" -- "万亿" (literally "ten-thousand yi") is
    # trillion, matched as its own two-character token so it doesn't get
    # chopped into "万" (10,000) with a dangling, unmatched "亿" left over.
    units = [_tu("Apple's market value hit $4trn.", '苹果市值达到4万亿美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']


def test_number_mismatch_still_fires_for_different_trillion_amount():
    units = [_tu("Apple's market value hit $4trn.", '苹果市值达到5万亿美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_number_mismatch_still_fires_for_different_billion_amount():
    # Real value drift ($350bn vs $450bn) must still be caught after
    # both sides are expanded to their full canonical value.
    units = [_tu('Revenue reached $350bn last year.', '去年收入达到4500亿美元。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' in units[0].meta['qa_issues']


def test_magnitude_expansion_does_not_misfire_on_single_letter_abbreviation():
    # "5m" is genuinely ambiguous (5 million? 5 meters? 5 minutes?) and is
    # deliberately NOT in the magnitude table -- expanding it wrongly
    # would be worse than leaving it to the plain bare-digit comparison.
    units = [_tu('The room is 5m long.', '这个房间长5米。')]
    qa.run(units, length_ratio=1.0)
    assert 'NUMBER_MISMATCH' not in units[0].meta['qa_issues']



def test_number_mismatch_sets_qa_details_with_normalized_numbers_on_each_side():
    units = [_tu('We shipped 42 units.', '我们发货了43个单位。')]
    qa.run(units, length_ratio=1.0)
    details = units[0].meta['qa_details']['NUMBER_MISMATCH']
    assert details == {'src_numbers': ['42'], 'tgt_numbers': ['43']}


def test_no_qa_details_when_numbers_match():
    units = [_tu('We shipped 42 units.', '我们发货了42个单位。')]
    qa.run(units, length_ratio=1.0)
    assert 'qa_details' not in units[0].meta


def test_find_number_spans_returns_original_substrings():
    text = "Since he replaced Jobs in 2011, sales quadrupled to $416bn."
    spans = qa.find_number_spans(text)
    assert [text[s:e] for s, e in spans] == ['2011', '416bn']


def test_find_number_spans_expands_month_and_magnitude_as_whole_tokens():
    # "September" and "4万亿" should each highlight as one whole span, not
    # get split into a bare digit plus leftover unrecognized characters.
    assert [
        '苹果市值达到4万亿美元。'[s:e]
        for s, e in qa.find_number_spans('苹果市值达到4万亿美元。')
    ] == ['4万亿']
    assert [
        'Sales grew in September.'[s:e]
        for s, e in qa.find_number_spans('Sales grew in September.')
    ] == ['September']


def test_find_number_spans_returns_empty_list_for_no_numbers():
    assert qa.find_number_spans('You may proceed.') == []


def test_find_placeholder_spans_returns_original_substrings():
    text = 'Welcome, {name}! You have %d new messages.'
    spans = qa.find_placeholder_spans(text)
    assert [text[s:e] for s, e in spans] == ['{name}', '%d']


def test_find_placeholder_spans_returns_empty_list_for_no_placeholders():
    assert qa.find_placeholder_spans('Plain sentence, nothing here.') == []


def test_find_url_spans_returns_original_substrings():
    text = 'See https://example.com/docs for details.'
    spans = qa.find_url_spans(text)
    assert [text[s:e] for s, e in spans] == ['https://example.com/docs']


def test_find_url_spans_excludes_trailing_sentence_punctuation():
    # The comma right after the URL is the sentence's punctuation, not
    # part of the link -- the span must not include it.
    text = 'See https://example.com/docs, for details.'
    spans = qa.find_url_spans(text)
    assert text[spans[0][0]:spans[0][1]] == 'https://example.com/docs'


def test_find_url_spans_returns_empty_list_for_no_urls():
    assert qa.find_url_spans('No links in this sentence.') == []


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


def test_url_mismatch_detects_uppercase_scheme():
    # RFC 3986 makes the scheme case-insensitive; _URL_RE used to be
    # case-sensitive, so an all-caps "HTTPS://..." slipped past detection.
    units = [_tu('Visit HTTPS://EXAMPLE.COM/docs now.', '立即访问。')]
    qa.run(units, length_ratio=1.0)
    assert 'URL_MISMATCH' in units[0].meta['qa_issues']


def test_no_placeholder_mismatch_for_bracketed_cjk_prose():
    # {文件} is glossed prose, not a Python/printf code placeholder. The old
    # \{[^{}\s]\} body matched any non-space run, so a target that didn't
    # repeat the braces was wrongly flagged as having dropped a placeholder.
    units = [_tu('请按{文件}选择模板。', '请根据文件选择模板。')]
    qa.run(units, length_ratio=1.0)
    assert 'PLACEHOLDER_MISMATCH' not in units[0].meta['qa_issues']


def test_currency_code_not_stripped_inside_a_word():
    # IGNORECASE made "EUR" match inside "European"; word-boundary anchoring
    # keeps the alphabetic codes matching only as standalone tokens.
    assert qa._CURRENCY_RE.findall('European union') == []
    assert qa._CURRENCY_RE.findall('EUR 50') != []


def test_period_not_swallowed_as_thousands_separator():
    # A period before three digits is far more often a version/decimal
    # fragment than a continental thousands mark -- only comma (and the CJK
    # fullwidth comma) count as thousands separators now.
    assert qa._THOUSANDS_RE.sub('', '1.234') == '1.234'   # version/decimal kept
    assert qa._THOUSANDS_RE.sub('', '1,234') == '1234'     # comma thousands stripped
    assert qa._THOUSANDS_RE.sub('', '1，234') == '1234'     # CJK fullwidth comma


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


def test_punctuation_unbalanced_flags_missing_closing_bracket():
    units = [_tu('Click (OK to continue.', '点击（确定以继续。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' in units[0].meta['qa_issues']
    assert units[0].meta['qa_details']['PUNCTUATION_UNBALANCED']['src'] == {'(': (1, 0)}
    assert units[0].meta['qa_details']['PUNCTUATION_UNBALANCED']['tgt'] == {'（': (1, 0)}


def test_no_punctuation_unbalanced_when_pairs_match():
    units = [_tu('Click (OK) to continue.', '点击（确定）以继续。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' not in units[0].meta['qa_issues']


def test_no_punctuation_unbalanced_for_straight_quote_apostrophe():
    # Straight quotes/apostrophes are deliberately excluded -- "don't"
    # alone would otherwise register as one unmatched `'`.
    units = [_tu("Don't stop.", '别停。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' not in units[0].meta['qa_issues']


def test_punctuation_unbalanced_flags_smart_quote_mismatch():
    units = [_tu('He said “hello.', '他说“你好。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' in units[0].meta['qa_issues']


def test_no_punctuation_unbalanced_for_curly_apostrophe():
    # P1-5: U+2019 is the typographic apostrophe (don’t / users’ / l’homme),
    # the same glyph as the closing single quote. A contraction has an
    # unmatched ’ with no opening ‘, which the naive count check flagged as
    # a bracket defect on every English source that uses smart quotes.
    units = [_tu('Don\u2019t stop \u2014 it\u2019s the users\u2019 choice.', '别停。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' not in units[0].meta['qa_issues']


def test_punctuation_unbalanced_still_flags_unclosed_open_single_quote():
    # The open side U+2018 is never an apostrophe, so a ‘ with no matching
    # ’ is still a real defect and must keep firing -- the fix only drops
    # the ambiguous close direction.
    units = [_tu('He said \u2018hello and walked on.', '他说了声“你好”就走了。')]
    qa.run(units, length_ratio=1.0)
    assert 'PUNCTUATION_UNBALANCED' in units[0].meta['qa_issues']
    assert units[0].meta['qa_details']['PUNCTUATION_UNBALANCED']['src'] == {'\u2018': (1, 0)}


def test_find_punctuation_pair_spans_returns_original_substrings():
    text = 'Click (OK to continue.'
    spans = qa.find_punctuation_pair_spans(text)
    assert [text[s:e] for s, e in spans] == ['(']


def test_width_mixing_flags_half_and_full_width_same_mark():
    # tgt uses both the half-width and full-width form of "?" -- a style
    # inconsistency, even though each individual occurrence is valid
    # punctuation on its own.
    units = [_tu('Really? Yes!', '真的?还是？')]
    qa.run(units, length_ratio=1.0)
    assert 'WIDTH_MIXING' in units[0].meta['qa_issues']
    assert units[0].meta['qa_details']['WIDTH_MIXING']['tgt'] == ['?']


def test_no_width_mixing_when_consistently_full_width():
    units = [_tu('Really? Yes!', '真的？还是？')]
    qa.run(units, length_ratio=1.0)
    assert 'WIDTH_MIXING' not in units[0].meta['qa_issues']


def test_no_width_mixing_for_comma_or_period_thousands_and_decimal_use():
    # Comma/period deliberately excluded -- see module docstring; a
    # thousands-separated number next to an unrelated full-width comma
    # elsewhere in the sentence is not a style inconsistency.
    units = [_tu('Revenue was 1,000 units.', '销售额为1000个单位，同比增长。')]
    qa.run(units, length_ratio=1.0)
    assert 'WIDTH_MIXING' not in units[0].meta['qa_issues']


def test_find_width_mixing_spans_returns_original_substrings():
    text = '等等！真的?'
    spans = qa.find_width_mixing_spans(text)
    assert sorted(text[s:e] for s, e in spans) == ['?', '！']


def test_leading_trailing_space_flags_source_and_target_independently():
    units = [_tu(' Hello', 'Hi '), _tu('Clean.', 'Clean.')]
    qa.run(units, length_ratio=1.0)
    assert 'LEADING_TRAILING_SPACE' in units[0].meta['qa_issues']
    assert set(units[0].meta['qa_details']['LEADING_TRAILING_SPACE']['sides']) == {'src', 'tgt'}
    assert 'LEADING_TRAILING_SPACE' not in units[1].meta['qa_issues']


def test_leading_trailing_space_detects_cjk_fullwidth_space():
    units = [_tu('Hello', '\u3000你好')]
    qa.run(units, length_ratio=1.0)
    assert 'LEADING_TRAILING_SPACE' in units[0].meta['qa_issues']


def test_no_leading_trailing_space_for_internal_whitespace_only():
    units = [_tu('Hello world', '你好 世界')]
    qa.run(units, length_ratio=1.0)
    assert 'LEADING_TRAILING_SPACE' not in units[0].meta['qa_issues']


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
    # the raw code stays present (grep/filter-friendly in Excel) but is no
    # longer the only thing shown -- a bare "EMPTY_SOURCE" means nothing
    # to a translator reading the sheet, so the Chinese label leads.
    assert 'EMPTY_SOURCE' in row
    assert '原文为空(EMPTY_SOURCE)' in row


def test_csv_writer_formats_multiple_issues_on_one_row(tmp_path):
    from language_tools.writers import csv_writer

    units = [_tu('Found %d results.', '找到了结果。')]  # empty tgt-ish + placeholder
    units[0].tgt_text = ''  # also trigger EMPTY_TARGET alongside PLACEHOLDER_MISMATCH
    qa.run(units, length_ratio=1.0)
    path = str(tmp_path / 'out.csv')
    csv_writer.write(path, units, include_qa=True)
    with open(path, encoding='utf-8-sig') as f:
        f.readline()
        row = f.readline().strip()
    assert '原文为空' not in row  # sanity: wrong label didn't leak in
    assert '译文为空(EMPTY_TARGET)' in row


def test_csv_writer_falls_back_to_raw_code_for_unmapped_issue(tmp_path, monkeypatch):
    from language_tools.writers import csv_writer

    units = [_tu('Hello', '你好')]
    units[0].meta['qa_issues'] = ['SOME_FUTURE_CHECK_NOT_YET_LABELED']
    units[0].meta['qa_confidence'] = 0.5
    path = str(tmp_path / 'out.csv')
    csv_writer.write(path, units, include_qa=True)
    with open(path, encoding='utf-8-sig') as f:
        f.readline()
        row = f.readline().strip()
    assert 'SOME_FUTURE_CHECK_NOT_YET_LABELED' in row


def test_csv_writer_include_align_adds_paragraph_and_move_columns(tmp_path):
    from language_tools.writers import csv_writer

    units = [_tu('Hi. Bye.', '你好，再见。')]
    units[0].source_key = '3'
    units[0].meta['align_move'] = '2:1'
    path = str(tmp_path / 'out.csv')
    csv_writer.write(path, units, include_align=True)
    with open(path, encoding='utf-8-sig') as f:
        header = f.readline().strip()
        row = f.readline().strip()
    assert header == 'No,EN,ZH,paragraph,align_move'
    assert row.startswith('1,Hi. Bye.,你好，再见。,3,')
    assert '合并（2→1）(2:1)' in row


def test_csv_writer_include_align_and_include_qa_together(tmp_path):
    from language_tools.writers import csv_writer

    units = [_tu('Hi. Bye.', '你好，再见。')]
    units[0].source_key = '1'
    units[0].meta['align_move'] = '1:1'
    units[0].meta['qa_issues'] = ['NUMBER_MISMATCH']
    units[0].meta['qa_confidence'] = 0.3
    path = str(tmp_path / 'out.csv')
    csv_writer.write(path, units, include_align=True, include_qa=True)
    with open(path, encoding='utf-8-sig') as f:
        header = f.readline().strip()
    assert header == 'No,EN,ZH,paragraph,align_move,confidence,status,issues'
