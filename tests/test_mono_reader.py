import pytest

from language_tools import mono
from language_tools.readers._ooxml import iter_body_paragraphs, iter_text_paragraphs
from language_tools.readers_mono import docx as docx_mono

from tests import docx_builder as d


def _doc(tmp_path, body, name='doc.docx'):
    return d.write(tmp_path / name, body)


# ---- extraction rules (readers/_ooxml.iter_text_paragraphs) ----------------

def test_body_paragraphs_in_document_order_empty_ones_dropped(tmp_path):
    path = _doc(tmp_path, d.para('First.') + d.para('') + d.para('   ') + d.para('Second.'))
    assert docx_mono.read(path) == ['First.', 'Second.']


def test_table_cell_paragraphs_are_included_in_document_order(tmp_path):
    body = (d.para('Before.') + d.table([['A1', ['B1 line one', 'B1 line two']], ['A2', 'B2']])
            + d.para('After.'))
    assert docx_mono.read(_doc(tmp_path, body)) == [
        'Before.', 'A1', 'B1 line one', 'B1 line two', 'A2', 'B2', 'After.']


def test_tab_and_line_break_become_spaces_not_glued_words(tmp_path):
    path = _doc(tmp_path, d.para('Name', '<w:r><w:tab/></w:r>', 'Value',
                                 '<w:r><w:br/></w:r>', 'Next'))
    assert docx_mono.read(path) == ['Name Value Next']
    # the bilingual reader's documented glue behavior is untouched
    assert list(iter_body_paragraphs(path)) == ['NameValueNext']


def test_textbox_text_is_neither_duplicated_nor_read_out_of_order(tmp_path):
    textbox = ('<w:r><mc:AlternateContent>'
               '<mc:Choice Requires="wps"><w:drawing><wp:anchor><wps:txbx><w:txbxContent>'
               + d.para('Boxed text.') +
               '</w:txbxContent></wps:txbx></wp:anchor></w:drawing></mc:Choice>'
               '<mc:Fallback><w:pict><w:txbxContent>' + d.para('Boxed text.') +
               '</w:txbxContent></w:pict></mc:Fallback>'
               '</mc:AlternateContent></w:r>')
    path = _doc(tmp_path, d.para('Body before.', textbox, ' Body after.') + d.para('Next paragraph.'))
    assert docx_mono.read(path) == ['Body before. Body after.', 'Next paragraph.']


def test_tracked_changes_read_as_accepted(tmp_path):
    ins = '<w:ins w:id="1" w:author="a">%s</w:ins>' % d.run('inserted ')
    dele = '<w:del w:id="2" w:author="a"><w:r><w:delText>deleted </w:delText></w:r></w:del>'
    path = _doc(tmp_path, d.para('Keep ', ins, dele, 'end.'))
    assert docx_mono.read(path) == ['Keep inserted end.']


def test_content_control_paragraphs_are_included(tmp_path):
    sdt = '<w:sdt><w:sdtContent>%s</w:sdtContent></w:sdt>' % d.para('Inside a content control.')
    assert docx_mono.read(_doc(tmp_path, sdt + d.para('Outside.'))) == ['Inside a content control.', 'Outside.']


def test_nbsp_is_normalized_to_space(tmp_path):
    assert docx_mono.read(_doc(tmp_path, d.para('a\u00a0b'))) == ['a b']


def test_document_with_no_text_reads_as_empty(tmp_path):
    assert docx_mono.read(_doc(tmp_path, d.para(''))) == []
    assert list(iter_text_paragraphs(_doc(tmp_path, '', 'empty.docx'))) == []


def test_reads_the_real_fixture_documents():
    from tests.conftest import fixture_path
    paras = docx_mono.read(fixture_path('basic.docx'))
    assert paras and all(p == p.strip() and p for p in paras)


# ---- segmentation and unit shape (mono.read_source) ------------------------

def test_english_source_is_split_into_sentences_with_paragraph_keys(tmp_path):
    path = _doc(tmp_path, d.para('Click OK. Then save the file.') + d.para('Done!'))
    units = mono.read_source(path, 'en-US', 'zh-CN')
    assert [u.src_text for u in units] == ['Click OK.', 'Then save the file.', 'Done!']
    assert [u.source_key for u in units] == ['1', '1', '2']
    assert all(u.tgt_text == '' and u.src_lang == 'en-US' and u.tgt_lang == 'zh-CN'
               and u.source_file == path for u in units)


def test_chinese_source_is_split_on_cjk_punctuation(tmp_path):
    path = _doc(tmp_path, d.para('点击确定。然后保存文件！'))
    units = mono.read_source(path, 'zh-CN', 'en-US')
    assert [u.src_text for u in units] == ['点击确定。', '然后保存文件！']


def test_paragraph_granularity_keeps_whole_paragraphs(tmp_path):
    path = _doc(tmp_path, d.para('Click OK. Then save.') + d.para('Second.'))
    units = mono.read_source(path, 'en-US', 'zh-CN', granularity='paragraph')
    assert [u.src_text for u in units] == ['Click OK. Then save.', 'Second.']


def test_repair_rules_apply_before_splitting(tmp_path):
    repairs = tmp_path / 'repairs.json'
    repairs.write_text('{"en": {"Clickthe": "Click the"}}', encoding='utf-8')
    path = _doc(tmp_path, d.para('Clickthe button.'))
    units = mono.read_source(path, 'en-US', 'zh-CN', repair_path=str(repairs))
    assert [u.src_text for u in units] == ['Click the button.']


def test_empty_document_gives_no_units(tmp_path):
    assert mono.read_source(_doc(tmp_path, d.para('')), 'en-US', 'zh-CN') == []


def test_unknown_granularity_is_an_error(tmp_path):
    path = _doc(tmp_path, d.para('x'))
    with pytest.raises(ValueError, match='granularity'):
        mono.read_source(path, 'en-US', 'zh-CN', granularity='word')


@pytest.mark.parametrize('src, tgt', [(None, 'zh-CN'), ('en-US', None), ('', '')])
def test_missing_language_is_an_error_not_a_guess(tmp_path, src, tgt):
    with pytest.raises(ValueError, match='src_lang and tgt_lang'):
        mono.read_source(_doc(tmp_path, d.para('x')), src, tgt)


# ---- input dispatch ----------------------------------------------------------

def test_unsupported_extension_error_names_supported_formats(tmp_path):
    with pytest.raises(ValueError, match=r'\.tmx.*\.docx'):
        mono.read_candidates(str(tmp_path / 'a.pdf'), 'en-US', 'zh-CN')


@pytest.mark.parametrize('ext', ['.xlsx', '.csv', '.tsv', '.xlsm'])
def test_bilingual_only_formats_say_monolingual_is_not_supported_yet(tmp_path, ext):
    with pytest.raises(ValueError, match='only readable as a bilingual source'):
        mono.read_candidates(str(tmp_path / ('a' + ext)), 'en-US', 'zh-CN')


def test_corpus_input_is_read_as_before_and_ignores_language_args(tmp_path):
    from language_tools.model import TranslationUnit as U
    from language_tools.writers import tmx_writer
    path = tmp_path / 'c.tmx'
    tmx_writer.write(str(path), [U('en-US', 'zh-CN', 'Hello', '你好')], 'en-US', 'zh-CN')
    units = mono.read_candidates(str(path), 'fr-FR', 'de-DE')
    assert [(u.src_lang, u.tgt_lang, u.src_text) for u in units] == [('en-US', 'zh-CN', 'Hello')]


# ---- language-pair resolution -------------------------------------------------

def _tm(*pairs):
    from language_tools.model import TranslationUnit as U
    return [U(s, t, 'x %d' % i, 'y') for i, (s, t) in enumerate(pairs)]


def test_explicit_pair_present_in_tm_is_accepted():
    assert mono.resolve_language_pair(_tm(('en-US', 'zh-CN')), 'en-US', 'zh-CN') == ('en-US', 'zh-CN')


def test_target_is_inferred_when_tm_has_one_target_for_the_source():
    tm = _tm(('en-US', 'zh-CN'), ('en-US', 'zh-CN'), ('zh-CN', 'en-US'))
    assert mono.resolve_language_pair(tm, 'en-US') == ('en-US', 'zh-CN')


def test_near_miss_language_code_is_an_error_listing_what_the_tm_has():
    with pytest.raises(ValueError) as e:
        mono.resolve_language_pair(_tm(('en-US', 'zh-CN')), 'en', 'zh')
    assert 'en->zh' in str(e.value) and 'en-US->zh-CN' in str(e.value)


def test_ambiguous_target_must_be_given():
    with pytest.raises(ValueError, match='several target languages'):
        mono.resolve_language_pair(_tm(('en-US', 'zh-CN'), ('en-US', 'ja-JP')), 'en-US')


def test_unknown_source_and_empty_tm_are_errors():
    with pytest.raises(ValueError, match='no entries with source language'):
        mono.resolve_language_pair(_tm(('en-US', 'zh-CN')), 'de-DE')
    with pytest.raises(ValueError, match='empty TM'):
        mono.resolve_language_pair([], 'en-US', 'zh-CN')
