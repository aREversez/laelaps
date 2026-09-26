from language_tools.terms import glossary
from language_tools.terms import tbx
from language_tools.terms.model import TermEntry


def _entry(src_term, tgt_term, **kw):
    return TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term=src_term, tgt_term=tgt_term,
                      **kw)


def test_round_trip_preserves_term_status_domain_note(tmp_path):
    entries = [
        _entry('machine translation', '机器翻译', status='approved', status_declared=True,
               domain='localization'),
        _entry('fuzzy match', '模糊匹配错误', status='forbidden', status_declared=True,
               note='old term, do not use'),
        _entry('unreviewed term', '未审核术语', status='approved', status_declared=False),
    ]
    path = str(tmp_path / 'glossary.tbx')
    tbx.write(path, entries)
    back = tbx.read(path, 'en-US', 'zh-CN')
    assert len(back) == 3
    assert back[0].src_term == 'machine translation'
    assert back[0].tgt_term == '机器翻译'
    assert back[0].status == 'approved'
    assert back[0].status_declared is True
    assert back[0].domain == 'localization'
    assert back[1].status == 'forbidden'
    assert back[1].note == 'old term, do not use'
    # a never-actually-set status should NOT come back asserting it's the
    # officially preferred term -- see write()'s docstring.
    assert back[2].status == 'approved'
    assert back[2].status_declared is False


def test_write_emits_tbx_basic_dialect_element_names(tmp_path):
    path = str(tmp_path / 'glossary.tbx')
    tbx.write(path, [_entry('click', '点击')])
    content = open(path, encoding='utf-8').read()
    assert '<termEntry' in content
    assert '<langSet' in content
    assert '<tig>' in content
    assert '<conceptEntry' not in content
    assert '<langSec' not in content


def test_read_accepts_tbx3_dialect_element_names_and_namespace(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tbx xmlns="urn:iso:std:iso:30042:ed-2" type="TBX-Basic" style="dca">\n'
        '  <text><body>\n'
        '    <conceptEntry id="c1">\n'
        '      <langSec xml:lang="en"><termSec><term>address bar</term></termSec></langSec>\n'
        '      <langSec xml:lang="zh"><termSec><term>地址栏</term></termSec></langSec>\n'
        '    </conceptEntry>\n'
        '  </body></text>\n'
        '</tbx>\n', encoding='utf-8')
    entries = tbx.read(str(path), 'en', 'zh')
    assert len(entries) == 1
    assert entries[0].src_term == 'address bar'
    assert entries[0].tgt_term == '地址栏'


def test_read_tolerates_region_less_language_tags(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en"><tig><term>save</term></tig></langSet>\n'
        '    <langSet xml:lang="zh"><tig><term>保存</term></tig></langSet>\n'
        '  </termEntry>\n'
        '</body></text></martif>\n', encoding='utf-8')
    # requested with region subtags the file doesn't have
    entries = tbx.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'save'


def test_read_maps_official_and_shorthand_administrative_status(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en-US"><tig><term>bad term</term></tig></langSet>\n'
        '    <langSet xml:lang="zh-CN"><tig><term>坏词</term>'
        '<termNote type="administrativeStatus">forbidden</termNote></tig></langSet>\n'
        '  </termEntry>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en-US"><tig><term>good term</term></tig></langSet>\n'
        '    <langSet xml:lang="zh-CN"><tig><term>好词</term>'
        '<termNote type="administrativeStatus">deprecatedTerm-admn-sts</termNote></tig>'
        '</langSet>\n'
        '  </termEntry>\n'
        '</body></text></martif>\n', encoding='utf-8')
    entries = tbx.read(str(path), 'en-US', 'zh-CN')
    by_src = {e.src_term: e for e in entries}
    assert by_src['bad term'].status == 'forbidden'  # shorthand 'forbidden'
    assert by_src['good term'].status == 'forbidden'  # official picklist value


def test_read_drops_extra_synonyms_and_warns(tmp_path, capsys):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en-US">'
        '<tig><term>legacy system</term></tig>'
        '<tig><term>heritage system</term></tig>'
        '</langSet>\n'
        '    <langSet xml:lang="zh-CN"><tig><term>旧系统</term></tig></langSet>\n'
        '  </termEntry>\n'
        '</body></text></martif>\n', encoding='utf-8')
    entries = tbx.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'legacy system'  # first tig only
    captured = capsys.readouterr()
    assert 'synonym' in captured.out


def test_read_skips_concept_missing_one_language(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en-US"><tig><term>english only</term></tig></langSet>\n'
        '  </termEntry>\n'
        '  <termEntry>\n'
        '    <langSet xml:lang="en-US"><tig><term>complete pair</term></tig></langSet>\n'
        '    <langSet xml:lang="zh-CN"><tig><term>完整词对</term></tig></langSet>\n'
        '  </termEntry>\n'
        '</body></text></martif>\n', encoding='utf-8')
    entries = tbx.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'complete pair'


def test_read_domain_from_subject_field_descrip(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>\n'
        '  <termEntry>\n'
        '    <descrip type="subjectField">finance</descrip>\n'
        '    <langSet xml:lang="en-US"><tig><term>ledger</term></tig></langSet>\n'
        '    <langSet xml:lang="zh-CN"><tig><term>分类账</term></tig></langSet>\n'
        '  </termEntry>\n'
        '</body></text></martif>\n', encoding='utf-8')
    entries = tbx.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].domain == 'finance'


def test_read_empty_body_returns_empty_list(tmp_path):
    path = tmp_path / 'in.tbx'
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body></body></text></martif>\n',
        encoding='utf-8')
    assert tbx.read(str(path), 'en-US', 'zh-CN') == []


def test_write_empty_entries_produces_valid_empty_file(tmp_path):
    path = str(tmp_path / 'empty.tbx')
    tbx.write(path, [])
    assert tbx.read(path, 'en-US', 'zh-CN') == []


def test_glossary_dispatches_tbx_extension(tmp_path):
    entries = [_entry('cloud', '云', status='approved', domain='tech')]
    path = str(tmp_path / 'glossary.tbx')
    glossary.write(path, entries)
    back = glossary.read(path, 'en-US', 'zh-CN')
    assert len(back) == 1
    assert back[0].src_term == 'cloud'
    assert back[0].domain == 'tech'
