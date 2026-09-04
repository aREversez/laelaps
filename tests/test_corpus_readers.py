from language_tools.corpus_readers import sdltm_reader, tmx_reader
from language_tools.writers import sdltm_writer, tmx_writer
from language_tools.model import TranslationUnit


def _sample_units():
    return [
        TranslationUnit(src_lang='en-US', tgt_lang='zh-CN',
                         src_text='Dr. Smith arrived at 9 a.m.', tgt_text='史密斯博士上午9点到达。'),
        TranslationUnit(src_lang='en-US', tgt_lang='zh-CN',
                         src_text='Sales grew, e.g. in Q3 <they> doubled & tripled.',
                         tgt_text='销售额增长了，例如第三季度<翻倍>并且&三倍。'),
    ]


def test_sdltm_unesc_handles_literal_ampersand_sequences_correctly(tmp_path):
    # Adversarial case for esc()/unesc() order-sensitivity: text that
    # literally contains "&lt;" as a substring (not just "<" or "&"
    # separately). Escaping order is &-first-then-<>; unescaping must be
    # the exact reverse (<>-first-then-&) or this round-trips wrong.
    # Confirmed by deliberately swapping the order and seeing this fail.
    text = 'The spec says R&D output &lt; 5% error, use < and >.'
    units = [TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=text, tgt_text='规格。')]
    path = str(tmp_path / 'adversarial.sdltm')
    sdltm_writer.write(path, units, 'en-US', 'zh-CN', 'test')
    got = sdltm_reader.read(path)
    assert got[0].src_text == text


def test_tmx_reader_round_trips_text_and_lang(tmp_path):
    path = str(tmp_path / 'x.tmx')
    tmx_writer.write(path, _sample_units(), 'en-US', 'zh-CN')
    units = tmx_reader.read(path)
    assert len(units) == 2
    assert units[0].src_lang == 'en-US' and units[0].tgt_lang == 'zh-CN'
    assert units[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert units[0].tgt_text == '史密斯博士上午9点到达。'
    # entity-bearing text (< > &) must decode correctly, not double-escape
    assert units[1].src_text == 'Sales grew, e.g. in Q3 <they> doubled & tripled.'
    assert units[1].tgt_text == '销售额增长了，例如第三季度<翻倍>并且&三倍。'


def test_sdltm_reader_round_trips_text_and_lang(tmp_path):
    path = str(tmp_path / 'x.sdltm')
    sdltm_writer.write(path, _sample_units(), 'en-US', 'zh-CN', 'test-tm')
    units = sdltm_reader.read(path)
    assert len(units) == 2
    assert units[0].src_lang == 'en-US' and units[0].tgt_lang == 'zh-CN'
    assert units[0].src_text == 'Dr. Smith arrived at 9 a.m.'
    assert units[0].tgt_text == '史密斯博士上午9点到达。'
    assert units[1].src_text == 'Sales grew, e.g. in Q3 <they> doubled & tripled.'
    assert units[1].tgt_text == '销售额增长了，例如第三季度<翻倍>并且&三倍。'
    assert units[0].guid and len(units[0].guid) > 0
    assert units[0].created_at


def test_tmx_to_sdltm_to_tmx_round_trip_preserves_text(tmp_path):
    tmx_path = str(tmp_path / 'a.tmx')
    tmx_writer.write(tmx_path, _sample_units(), 'en-US', 'zh-CN')

    units_from_tmx = tmx_reader.read(tmx_path)
    sdltm_path = str(tmp_path / 'b.sdltm')
    sdltm_writer.write(sdltm_path, units_from_tmx, 'en-US', 'zh-CN', 'round-trip')

    units_from_sdltm = sdltm_reader.read(sdltm_path)
    tmx_path2 = str(tmp_path / 'c.tmx')
    tmx_writer.write(tmx_path2, units_from_sdltm, 'en-US', 'zh-CN')

    final = tmx_reader.read(tmx_path2)
    original = _sample_units()
    assert [(u.src_text, u.tgt_text) for u in final] == \
           [(u.src_text, u.tgt_text) for u in original]


def test_sdltm_to_tmx_to_sdltm_round_trip_preserves_text(tmp_path):
    sdltm_path = str(tmp_path / 'a.sdltm')
    sdltm_writer.write(sdltm_path, _sample_units(), 'en-US', 'zh-CN', 'round-trip')

    units_from_sdltm = sdltm_reader.read(sdltm_path)
    tmx_path = str(tmp_path / 'b.tmx')
    tmx_writer.write(tmx_path, units_from_sdltm, 'en-US', 'zh-CN')

    units_from_tmx = tmx_reader.read(tmx_path)
    sdltm_path2 = str(tmp_path / 'c.sdltm')
    sdltm_writer.write(sdltm_path2, units_from_tmx, 'en-US', 'zh-CN', 'round-trip')

    final = sdltm_reader.read(sdltm_path2)
    original = _sample_units()
    assert [(u.src_text, u.tgt_text) for u in final] == \
           [(u.src_text, u.tgt_text) for u in original]
