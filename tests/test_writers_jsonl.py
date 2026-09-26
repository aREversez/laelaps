import json

from language_tools.model import TranslationUnit
from language_tools.writers import jsonl_writer


def _unit(src, tgt):
    return TranslationUnit(src_lang='en-US', tgt_lang='zh-CN', src_text=src, tgt_text=tgt)


def test_jsonl_writer_writes_one_object_per_line(tmp_path):
    path = tmp_path / 'out.jsonl'
    units = [_unit('Hello.', '你好。'), _unit('World.', '世界。')]
    jsonl_writer.write(str(path), units, 'en-US', 'zh-CN')

    lines = path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first == {'src_lang': 'en-US', 'tgt_lang': 'zh-CN', 'src': 'Hello.', 'tgt': '你好。'}
    second = json.loads(lines[1])
    assert second == {'src_lang': 'en-US', 'tgt_lang': 'zh-CN', 'src': 'World.', 'tgt': '世界。'}


def test_jsonl_writer_skips_empty_src_or_tgt(tmp_path):
    path = tmp_path / 'out.jsonl'
    units = [_unit('Hello.', '你好。'), _unit('', '空的原文。'), _unit('Empty target.', ''), _unit('  ', '  ')]
    jsonl_writer.write(str(path), units, 'en-US', 'zh-CN')

    lines = path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])['src'] == 'Hello.'


def test_jsonl_writer_strips_whitespace(tmp_path):
    path = tmp_path / 'out.jsonl'
    units = [_unit('  Hello.  ', '  你好。  ')]
    jsonl_writer.write(str(path), units, 'en-US', 'zh-CN')

    row = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
    assert row['src'] == 'Hello.'
    assert row['tgt'] == '你好。'


def test_jsonl_writer_no_bom_and_readable_cjk(tmp_path):
    path = tmp_path / 'out.jsonl'
    jsonl_writer.write(str(path), [_unit('Hi.', '嗨。')], 'en-US', 'zh-CN')

    raw = path.read_bytes()
    assert not raw.startswith(b'\xef\xbb\xbf')
    assert '嗨。' in raw.decode('utf-8')
