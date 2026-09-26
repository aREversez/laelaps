from language_tools import api
from language_tools.corpus_readers import sdltm_reader, tmx_reader


def test_convert_docx_to_tmx_then_tmx_to_sdltm_via_api(tmp_path):
    from conftest import fixture_path

    step1 = str(tmp_path / 'step1')
    api.convert(fixture_path('basic.docx'), step1, src_lang='en-US', tgt_lang='zh-CN',
                formats=('tmx',))

    step2 = str(tmp_path / 'step2')
    result = api.convert(step1 + '.tmx', step2, formats=('sdltm',))
    # src_lang/tgt_lang inferred from the tmx itself, not passed explicitly
    assert result['units'] == 4

    units = sdltm_reader.read(step2 + '.sdltm')
    assert len(units) == 4
    assert units[0].src_lang == 'en-US'
    assert units[0].tgt_lang == 'zh-CN'


def test_convert_missing_lang_for_bilingual_source_raises(tmp_path):
    import pytest
    from conftest import fixture_path

    with pytest.raises(ValueError, match='src_lang and tgt_lang are required'):
        api.convert(fixture_path('basic.docx'), str(tmp_path / 'out'))


def test_convert_sdltm_to_tmx_infers_language(tmp_path):
    from conftest import fixture_path

    src_base = str(tmp_path / 'src')
    api.convert(fixture_path('basic.docx'), src_base, src_lang='en-US', tgt_lang='zh-CN',
                formats=('sdltm',))

    out_base = str(tmp_path / 'out')
    result = api.convert(src_base + '.sdltm', out_base, formats=('tmx',))
    assert result['units'] == 4

    units = tmx_reader.read(out_base + '.tmx')
    assert units[0].src_lang == 'en-US'
    assert units[0].tgt_lang == 'zh-CN'


def test_convert_written_count_excludes_dropped_gap_units(tmp_path):
    # tmx_writer/sdltm_writer silently drop units with an empty src/tgt (an
    # alignment GAP surfaces this way), but api.convert used to report
    # written['tmx'] as len(corpus_units) -- inflated by however many GAP
    # units were present. The count must reflect what actually landed in the
    # file. 2 units read, 1 has an empty target, so only 1 is written.
    tmx_in = tmp_path / 'gap.tmx'
    tmx_in.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n'
        '  <header srclang="en-US"/>\n  <body>\n'
        '    <tu><tuv xml:lang="en-US"><seg>Hello.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg>\u4f60\u597d\u3002</seg></tuv></tu>\n'
        '    <tu><tuv xml:lang="en-US"><seg>Gap.</seg></tuv>'
        '<tuv xml:lang="zh-CN"><seg></seg></tuv></tu>\n'
        '  </body>\n</tmx>\n',
        encoding='utf-8')

    out_base = str(tmp_path / 'out')
    result = api.convert(str(tmx_in), out_base, formats=('tmx', 'sdltm', 'jsonl'))
    assert result['units'] == 2                    # both tus were read
    assert result['written']['tmx'] == 1           # only the non-empty one written
    assert result['written']['sdltm'] == 1
    assert result['written']['jsonl'] == 1
