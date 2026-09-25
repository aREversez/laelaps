from language_tools.corpus_readers import sdltm_reader, tmx_reader
from language_tools.writers import sdltm_writer, tmx_writer
from language_tools.model import TranslationUnit

import pytest


def test_illegal_xml_control_chars_survive_round_trip_in_both_formats(tmp_path):
    # XML 1.0 illegal control chars (form feed \x0c and friends really
    # occur in TM/CSV-sourced text). Before esc() sanitized them: the TMX
    # file was unparseable end to end (ET.parse: "not well-formed
    # (invalid token)"), and the SDLTM one "read back fine" with src_text
    # silently '' -- the reader's ParseError fallback swallowed the
    # corruption instead of reporting it.
    text = 'Form\x0cfeed and \x01other\x1f control chars.'
    units = [TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=text, tgt_text='控制字符。')]

    tmx = str(tmp_path / 'ctrl.tmx')
    tmx_writer.write(tmx, units, 'en-US', 'zh-CN')
    back = tmx_reader.read(tmx)  # must not raise
    assert len(back) == 1
    assert back[0].src_text == text.replace('\x0c', '\ufffd').replace('\x01', '\ufffd').replace('\x1f', '\ufffd')

    sdltm = str(tmp_path / 'ctrl.sdltm')
    sdltm_writer.write(sdltm, units, 'en-US', 'zh-CN', 'test')
    back = sdltm_reader.read(sdltm)
    assert len(back) == 1
    assert back[0].src_text == text.replace('\x0c', '\ufffd').replace('\x01', '\ufffd').replace('\x1f', '\ufffd')


def test_sdltm_reader_raises_loudly_on_unparseable_segment_xml(tmp_path):
    # A corrupt/foreign Segment blob must not read back as an empty
    # unit -- '' is indistinguishable from a genuinely empty segment, so
    # the old behavior silently emptied text with no signal at all.
    import sqlite3

    path = str(tmp_path / 'corrupt.sdltm')
    sdltm_writer.write(path, [], 'en-US', 'zh-CN', 'test')
    con = sqlite3.connect(path)
    try:
        con.execute(
            'INSERT INTO translation_units(guid,translation_memory_id,source_hash,'
            'source_segment,target_hash,target_segment,creation_date,creation_user,'
            'change_date,change_user,last_used_date,last_used_user,usage_counter,flags) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (b'\x00' * 16, 1, 0, '<Segment><unclosed>', 0,
             '<Segment>ok</Segment>', '2024-01-01 00:00:00', 'test',
             '2024-01-01 00:00:00', 'test', '2024-01-01 00:00:00', 'test', 0, 131073))
        con.commit()
    finally:
        con.close()

    with pytest.raises(ValueError, match='unparseable segment XML'):
        sdltm_reader.read(path)


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


def test_writers_preserve_unit_timestamps_instead_of_stamping_now(tmp_path):
    # P0-4: both writers ignored u.created_at/u.modified_at and stamped
    # datetime.now(), so a TMX<->SDLTM round-trip reset every TU's
    # provenance to the moment of writing -- aging reports, merge
    # 'prefer-newer' conflict resolution and audit history all keyed off
    # dates that no longer meant anything.
    units = [TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text='Hello there.', tgt_text='你好。',
        created_at='2019-03-04 05:06:07', modified_at='2020-07-08 09:10:11')]

    sdltm = str(tmp_path / 'ts.sdltm')
    sdltm_writer.write(sdltm, units, 'en-US', 'zh-CN', 'test')
    back = sdltm_reader.read(sdltm)
    assert back[0].created_at == '2019-03-04 05:06:07'
    assert back[0].modified_at == '2020-07-08 09:10:11'

    tmx = str(tmp_path / 'ts.tmx')
    tmx_writer.write(tmx, units, 'en-US', 'zh-CN')
    back = tmx_reader.read(tmx)
    # TMX renders the same instants in its compact UTC attribute format
    assert back[0].created_at == '20190304T050607Z'
    assert back[0].modified_at == '20200708T091011Z'


def test_writer_preserves_timestamps_across_formats(tmp_path):
    # An SDLTM column date must land in TMX's compact form and back again
    # without drifting -- normalize_ts re-renders the instant per format.
    units = [TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text='Cross format.', tgt_text='跨格式。',
        created_at='2021-12-25 13:14:15', modified_at='2022-01-01 00:00:00')]
    tmx = str(tmp_path / 'cross.tmx')
    tmx_writer.write(tmx, units, 'en-US', 'zh-CN')
    sdltm = str(tmp_path / 'cross.sdltm')
    sdltm_writer.write(sdltm, tmx_reader.read(tmx), 'en-US', 'zh-CN', 'test')
    back = sdltm_reader.read(sdltm)
    assert back[0].created_at == '2021-12-25 13:14:15'
    assert back[0].modified_at == '2022-01-01 00:00:00'


def test_tmx_writer_omits_changedate_when_unit_has_no_modification(tmp_path):
    # Absence must stay absence, not echo the creation stamp: TMX files
    # with no changedate read back modified_at=None so stats aging can
    # still bucket them as 'unknown'.
    units = [TranslationUnit(
        src_lang='en-US', tgt_lang='zh-CN', src_text='x', tgt_text='x')]
    tmx = str(tmp_path / 'plain.tmx')
    tmx_writer.write(tmx, units, 'en-US', 'zh-CN')
    back = tmx_reader.read(tmx)
    assert back[0].created_at  # creationdate always present
    assert back[0].modified_at is None


def test_sdltm_reader_handles_entities_beyond_our_own_writer(tmp_path):
    # Our own writer only ever produces &amp;/&lt;/&gt; (the 3 entities its
    # hand-rolled esc() emits), and the old unesc() only reversed exactly
    # those. A real Trados-native .sdltm can contain other valid XML
    # entities our writer never would (e.g. a numeric character reference
    # for an apostrophe) -- a real XML parser handles all of them per
    # spec, a hand-rolled reverse-of-our-own-escaping function wouldn't.
    import sqlite3
    from language_tools.writers import sdltm_writer as w

    path = str(tmp_path / 'native_style.sdltm')
    con = None
    try:
        w.write(path, [], 'en-US', 'zh-CN', 'test')  # creates schema, 0 rows
        con = sqlite3.connect(path)
        seg = ('<Segment><Elements><Text><Value>It&#39;s ready</Value></Text>'
               '</Elements><CultureName>en-US</CultureName></Segment>')
        tgt_seg = ('<Segment><Elements><Text><Value>准备好了</Value></Text>'
                   '</Elements><CultureName>zh-CN</CultureName></Segment>')
        con.execute(
            'INSERT INTO translation_units(guid,translation_memory_id,source_hash,'
            'source_segment,target_hash,target_segment,creation_date,creation_user,'
            'change_date,change_user,last_used_date,last_used_user,usage_counter,flags) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (b'\x00' * 16, 1, 0, seg, 0, tgt_seg, '2024-01-01 00:00:00', 'test',
             '2024-01-01 00:00:00', 'test', '2024-01-01 00:00:00', 'test', 0, 131073))
        con.commit()
    finally:
        if con:
            con.close()

    units = sdltm_reader.read(path)
    assert len(units) == 1
    assert units[0].src_text == "It's ready"


def test_tmx_reader_handles_default_xml_namespace(tmp_path):
    # Some TMX exports declare a default xmlns on <tmx>; plain
    # root.find('body') etc. only match unqualified tag names and
    # silently return nothing at all for such a file -- confirmed by
    # reverting to that lookup and reproducing zero units found.
    path = tmp_path / 'namespaced.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx xmlns="http://www.lisa.org/tmx14" version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu><tuv xml:lang="en-US"><seg>Hello world.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>你好世界。</seg></tuv></tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path))
    assert len(units) == 1
    assert units[0].src_text == 'Hello world.'
    assert units[0].tgt_text == '你好世界。'


def test_tmx_reader_preserves_text_around_inline_tags(tmp_path):
    # seg.text alone only captures text before the first child element;
    # anything inside/after an inline tag (<bpt>/<ept>/<ph>/<hi>, all
    # common in real TMX for placeholders/formatting) was silently
    # dropped -- confirmed: "Click <b>OK</b> to continue." round-tripped
    # to just "Click" before this fix.
    path = tmp_path / 'inline_tags.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu><tuv xml:lang="en-US"><seg>Click <bpt i="1">&lt;b&gt;</bpt>OK'
        '<ept i="1">&lt;/b&gt;</ept> to continue.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>继续</seg></tuv></tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path))
    assert len(units) == 1
    assert units[0].src_text == 'Click <b>OK</b> to continue.'


def test_tmx_reader_matches_tuv_by_requested_language(tmp_path):
    # Without an explicit src_lang/tgt_lang, the reader falls back to
    # positional (first two tuv); with them given, it should pick the
    # right tuv by language even if a <tu> has more than two (or the
    # requested pair isn't first).
    path = tmp_path / 'multilingual.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="fr-FR"><seg>Bonjour.</seg></tuv>'
        '<tuv xml:lang="en-US"><seg>Hello.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>你好。</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path), src_lang='en-US', tgt_lang='zh-CN')
    assert len(units) == 1
    assert units[0].src_text == 'Hello.'
    assert units[0].tgt_text == '你好。'


def test_tmx_reader_matches_region_less_lang_tag(tmp_path):
    # Some CAT tools export TMX with a bare xml:lang="en" (no region).
    # Requesting the default 'en-US'/'zh-CN' pair should still find it via
    # base-subtag fallback instead of skipping the <tu> entirely.
    path = tmp_path / 'no_region.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="en"><seg>Hello.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>你好。</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path), src_lang='en-US', tgt_lang='zh-CN')
    assert len(units) == 1
    assert units[0].src_text == 'Hello.'
    assert units[0].tgt_text == '你好。'


def test_tmx_reader_captures_inline_markup_in_seg(tmp_path):
    # When a <seg> contains <bpt>/<ept>/<ph>/<hi> (or any other inline
    # element), the reader populates TranslationUnit.src_markup/
    # tgt_markup with an ordered InlineNode list -- not just the visible
    # text. The visible text (itertext-joined) is still in src_text/
    # tgt_text, so existing callers see no change; the markup list lets
    # tmx_writer round-trip the inline structure losslessly.
    from language_tools.model import InlineNode

    path = tmp_path / 'inline_tags.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="en-US"><seg>Click <bpt i="1">&lt;b&gt;</bpt>OK'
        '<ept i="1">&lt;/b&gt;</ept> to continue.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>继续</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path))
    assert len(units) == 1
    # Visible text preserved (unchanged from the pre-markup behavior)
    assert units[0].src_text == 'Click <b>OK</b> to continue.'
    # src_markup captured -- interleaved text/tag/text/tag/text
    markup = units[0].src_markup
    assert markup is not None
    assert [n.kind for n in markup] == ['text', 'tag', 'text', 'tag', 'text']
    assert markup[0].content == 'Click '
    assert '<bpt' in markup[1].content and 'i="1"' in markup[1].content
    assert markup[2].content == 'OK'
    assert '<ept' in markup[3].content
    assert markup[4].content == ' to continue.'
    # tgt had no inline tag -> markup stays None (not an empty list),
    # so callers that don't care about markup can branch on `is not None`.
    assert units[0].tgt_markup is None


def test_tmx_to_tmx_round_trip_preserves_inline_markup(tmp_path):
    # The pre-markup fix only preserved visible text on TMX->TMX round-trip
    # (the <bpt>/<ept> wrappers were dropped on read, then couldn't come
    # back on write). With src_markup/tgt_markup threaded through, a
    # round-trip through tmx_reader -> tmx_writer -> tmx_reader must
    # preserve the inline element structure, not just visible text.
    src_tmx = tmp_path / 'inline.tmx'
    src_tmx.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="en-US"><seg>Click <bpt i="1">&lt;b&gt;</bpt>OK'
        '<ept i="1">&lt;/b&gt;</ept> to continue.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>继续</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')

    units_in = tmx_reader.read(str(src_tmx))
    out_tmx = str(tmp_path / 'round.tmx')
    tmx_writer.write(out_tmx, units_in, 'en-US', 'zh-CN')
    units_out = tmx_reader.read(out_tmx)

    assert units_out[0].src_text == units_in[0].src_text == 'Click <b>OK</b> to continue.'
    # Markup survived -- after writing and re-reading, the InlineNode
    # list should still have the same shape (text/tag/text/tag/text)
    # and the same tag fragments.
    assert units_out[0].src_markup is not None
    assert [n.kind for n in units_out[0].src_markup] == ['text', 'tag', 'text', 'tag', 'text']
    # Tag fragments contain the bpt/ept elements with attributes preserved
    tag_contents = [n.content for n in units_out[0].src_markup if n.kind == 'tag']
    assert any('<bpt' in c and 'i="1"' in c for c in tag_contents)
    assert any('<ept' in c and 'i="1"' in c for c in tag_contents)


def test_text_only_tu_has_none_markup_after_read(tmp_path):
    # The common case: a <seg> with no child elements (just text) must
    # leave src_markup/tgt_markup as None, not as a single-element list
    # -- so downstream code that checks `if u.src_markup is None` doesn't
    # have to also handle empty-list and single-text-node-list edge cases.
    path = tmp_path / 'plain.tmx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="en-US"><seg>Hello world.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>你好世界。</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')
    units = tmx_reader.read(str(path))
    assert units[0].src_markup is None
    assert units[0].tgt_markup is None


def test_convert_wires_lang_through_to_tmx_reader_for_matching(tmp_path):
    # api.convert() must actually pass its own src_lang/tgt_lang into the
    # corpus reader when both are given -- otherwise tmx_reader's language-
    # matching capability is unreachable through the normal pipeline.
    from language_tools import api

    tmx_path = tmp_path / 'multilingual.tmx'
    tmx_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tmx version="1.4">\n'
        '<header creationtool="Test" creationtoolversion="1.0" adminlang="en-US" '
        'srclang="en-US" datatype="unknown" segtype="sentence"/>\n'
        '<body><tu>'
        '<tuv xml:lang="fr-FR"><seg>Bonjour.</seg></tuv>'
        '<tuv xml:lang="en-US"><seg>Hello.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>你好。</seg></tuv>'
        '</tu></body>\n'
        '</tmx>', encoding='utf-8')

    out_base = str(tmp_path / 'out')
    result = api.convert(str(tmx_path), out_base, src_lang='en-US', tgt_lang='zh-CN', formats=('csv',))
    assert result['units'] == 1
    with open(out_base + '.csv', encoding='utf-8-sig') as f:
        rows = f.readlines()
    assert 'Hello.' in rows[1]
    assert '你好。' in rows[1]
