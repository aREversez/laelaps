import json

import pytest

from language_tools.model import TranslationUnit
from language_tools.tm import leverage as leverage_module
from language_tools.tm import quote as quote_module


def _u(src, tgt, src_lang='en-US', tgt_lang='zh-CN'):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt)


def test_weighted_words_applies_default_weights_per_band():
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    candidates = [
        _u('Click OK to continue.', ''),           # exact, 4 words -> 0% weight
        _u('Totally unrelated content here.', ''),  # no_match, 4 words -> 100% weight
    ]
    leverage_module.analyze(tm, candidates)
    s = leverage_module.summarize(candidates)
    total, per_band = quote_module.weighted_words(s)
    assert per_band['exact'] == 0.0
    assert per_band['no_match'] == 4.0
    assert total == 4.0
    # every band present even at zero, same convention as leverage.summarize()
    for band in leverage_module.BANDS:
        assert band in per_band


def test_weighted_words_accepts_custom_weights():
    s = leverage_module.summarize([])
    s['bands']['no_match']['words'] = 100
    total, per_band = quote_module.weighted_words(s, weights={'no_match': 50.0})
    assert per_band['no_match'] == 50.0
    assert total == 50.0
    # bands not present in the custom dict still fall back to DEFAULT_WEIGHTS
    assert per_band['exact'] == 0.0


def test_load_weights_reads_json_and_falls_back_to_defaults(tmp_path):
    path = tmp_path / 'weights.json'
    path.write_text(json.dumps({'no_match': 80.0}), encoding='utf-8')
    weights = quote_module.load_weights(str(path))
    assert weights['no_match'] == 80.0
    assert weights['exact'] == quote_module.DEFAULT_WEIGHTS['exact']


def test_load_weights_rejects_unknown_band(tmp_path):
    path = tmp_path / 'weights.json'
    path.write_text(json.dumps({'totally_made_up': 50.0}), encoding='utf-8')
    with pytest.raises(ValueError, match='unknown band'):
        quote_module.load_weights(str(path))


def test_load_weights_rejects_out_of_range_weight(tmp_path):
    path = tmp_path / 'weights.json'
    path.write_text(json.dumps({'no_match': 150.0}), encoding='utf-8')
    with pytest.raises(ValueError, match='0-100'):
        quote_module.load_weights(str(path))


def test_load_weights_rejects_top_level_json_array(tmp_path):
    # A rate card that's a list (or any non-object JSON) must raise ValueError
    # through tm_cli.main()'s error handling, not an AttributeError traceback.
    path = tmp_path / 'weights.json'
    path.write_text(json.dumps([{'no_match': 80.0}]), encoding='utf-8')
    with pytest.raises(ValueError, match='must contain a JSON object'):
        quote_module.load_weights(str(path))


def test_load_weights_rejects_top_level_json_scalar(tmp_path):
    path = tmp_path / 'weights.json'
    path.write_text('80.0', encoding='utf-8')
    with pytest.raises(ValueError, match='must contain a JSON object'):
        quote_module.load_weights(str(path))


def test_quote_batch_rolls_up_per_file_and_total():
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    file_units = {
        'a.tmx': [_u('Click OK to continue.', '')],           # exact, 4 words
        'b.tmx': [_u('Totally unrelated content here.', '')],  # no_match, 4 words
    }
    result = quote_module.quote_batch(file_units, tm)
    assert result['files']['a.tmx']['summary']['bands']['exact']['words'] == 4
    assert result['files']['a.tmx']['weighted_total'] == 0.0
    assert result['files']['b.tmx']['summary']['bands']['no_match']['words'] == 4
    assert result['files']['b.tmx']['weighted_total'] == 4.0
    assert result['total']['summary']['total'] == 2
    assert result['total']['summary']['total_words'] == 8
    assert result['total']['weighted_total'] == 4.0


def test_quote_batch_mutates_units_in_place_via_leverage_analyze():
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    units = [_u('Click OK to continue.', '')]
    quote_module.quote_batch({'a.tmx': units}, tm)
    assert units[0].meta['leverage_band'] == 'exact'


def test_quote_batch_empty_batch_does_not_raise():
    result = quote_module.quote_batch({}, [])
    assert result['files'] == {}
    assert result['total']['summary']['total'] == 0
    assert result['total']['weighted_total'] == 0.0


def test_write_quote_csv_writes_per_file_and_total_rows(tmp_path):
    tm = [_u('Click OK to continue.', '点击确定以继续。')]
    file_units = {'a.tmx': [_u('Click OK to continue.', '')]}
    result = quote_module.quote_batch(file_units, tm)
    out = tmp_path / 'quote.csv'
    quote_module.write_quote_csv(str(out), result)
    content = out.read_text(encoding='utf-8-sig')
    lines = content.strip().splitlines()
    assert lines[0].split(',')[:4] == ['file', 'segments', 'words', 'weighted_words']
    assert lines[1].startswith('a.tmx,1,4,0.0')
    assert lines[2].startswith('TOTAL,1,4,0.0')
