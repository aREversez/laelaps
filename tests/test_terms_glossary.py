import openpyxl

from language_tools.terms import glossary
from language_tools.terms.model import TermEntry


def _entry(src_term, tgt_term, **kw):
    return TermEntry(src_lang='en-US', tgt_lang='zh-CN', src_term=src_term, tgt_term=tgt_term, **kw)


# ------------------------------------------------------------- round trip

def test_csv_round_trip(tmp_path):
    entries = [
        _entry('cloud', '云', status='approved', domain='tech', note='首选译法'),
        _entry('big data', '大数据', status='forbidden', note='禁止使用旧译名'),
    ]
    path = str(tmp_path / 'glossary.csv')
    glossary.write(path, entries)
    back = glossary.read(path, 'en-US', 'zh-CN')
    assert len(back) == 2
    assert back[0].src_term == 'cloud'
    assert back[0].tgt_term == '云'
    assert back[0].status == 'approved'
    assert back[0].domain == 'tech'
    assert back[0].note == '首选译法'
    assert back[1].status == 'forbidden'
    assert back[1].note == '禁止使用旧译名'
    # write() doesn't persist a language column -- read() stamps whatever
    # pair the caller asks for, same "file-level, not per-row" design.
    assert back[0].src_lang == 'en-US'
    assert back[0].tgt_lang == 'zh-CN'


def test_xlsx_round_trip(tmp_path):
    entries = [_entry('API', '接口', status='forbidden', note='不要翻成“阿匹爱”')]
    path = str(tmp_path / 'glossary.xlsx')
    glossary.write(path, entries)
    back = glossary.read(path, 'en-US', 'zh-CN')
    assert len(back) == 1
    assert back[0].src_term == 'API'
    assert back[0].tgt_term == '接口'
    assert back[0].status == 'forbidden'


def test_empty_entry_list_round_trips_to_empty(tmp_path):
    path = str(tmp_path / 'glossary.csv')
    glossary.write(path, [])
    assert glossary.read(path, 'en-US', 'zh-CN') == []


# --------------------------------------------------------------- header

def test_missing_required_header_raises(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('foo,bar\ncloud,云\n', encoding='utf-8')
    try:
        glossary.read(str(path), 'en-US', 'zh-CN')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'src_term' in str(e) and 'tgt_term' in str(e)


def test_header_matching_is_case_insensitive_and_order_independent(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('TGT_TERM,SRC_TERM,STATUS\n云,cloud,approved\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'cloud'
    assert entries[0].tgt_term == '云'


def test_header_accepts_source_target_alias(tmp_path):
    """Real-world glossary made in another tool: 'source'/'target'
    instead of this tool's own 'src_term'/'tgt_term' -- see
    HEADER_ALIASES docstring for why rejecting this outright is a false
    negative.
    """
    path = tmp_path / 'glossary.csv'
    path.write_text('source,target,status\ncloud,云,approved\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 1
    assert entries[0].src_term == 'cloud'
    assert entries[0].tgt_term == '云'
    assert entries[0].status == 'approved'


def test_header_accepts_source_term_target_term_alias(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('Source_Term,Target_Term\ncloud,云\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].src_term == 'cloud'
    assert entries[0].tgt_term == '云'


def test_header_accepts_chinese_alias(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('原文术语,译文术语,备注\ncloud,云,首选译法\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].src_term == 'cloud'
    assert entries[0].tgt_term == '云'
    assert entries[0].note == '首选译法'


def test_header_alias_matching_is_case_insensitive(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('SOURCE,TARGET\ncloud,云\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].src_term == 'cloud'


def test_header_still_rejects_genuinely_unrecognized_columns(tmp_path):
    # Broadening HEADER_ALIASES must not turn this into a
    # match-anything scheme -- 'foo'/'bar' still isn't recognized as
    # either src_term or tgt_term by any alias.
    path = tmp_path / 'glossary.csv'
    path.write_text('foo,bar\ncloud,云\n', encoding='utf-8')
    try:
        glossary.read(str(path), 'en-US', 'zh-CN')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'src_term' in str(e) and 'tgt_term' in str(e)


def test_header_only_file_is_empty_not_an_error(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('src_term,tgt_term\n', encoding='utf-8')
    assert glossary.read(str(path), 'en-US', 'zh-CN') == []


# ------------------------------------------------------------- data rows

def test_blank_rows_are_skipped(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('src_term,tgt_term\ncloud,云\n,\napi,接口\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert len(entries) == 2


def test_missing_status_defaults_to_approved(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('src_term,tgt_term\ncloud,云\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].status == 'approved'


def test_unrecognized_status_falls_back_to_approved_and_warns(tmp_path, capsys):
    path = tmp_path / 'glossary.csv'
    path.write_text('src_term,tgt_term,status\ncloud,云,maybe\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].status == 'approved'
    assert 'unrecognized status' in capsys.readouterr().out


def test_status_matching_is_case_insensitive(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text('src_term,tgt_term,status\ncloud,云,FORBIDDEN\n', encoding='utf-8')
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].status == 'forbidden'


# ------------------------------------------------------------- encoding

def test_gb18030_csv_decoded(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_bytes('src_term,tgt_term\ncloud,云\n'.encode('gb18030'))
    entries = glossary.read(str(path), 'en-US', 'zh-CN')
    assert entries[0].tgt_term == '云'


# ------------------------------------------------------- unsupported ext

def test_unsupported_extension_raises_on_read(tmp_path):
    path = tmp_path / 'glossary.tsv'
    path.write_text('src_term\ttgt_term\ncloud\t云\n', encoding='utf-8')
    try:
        glossary.read(str(path), 'en-US', 'zh-CN')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'unsupported' in str(e)


def test_unsupported_extension_raises_on_write(tmp_path):
    path = str(tmp_path / 'glossary.tsv')
    try:
        glossary.write(path, [_entry('cloud', '云')])
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'unsupported' in str(e)


# ------------------------------------------------------------ xlsx shape

def test_xlsx_write_emits_expected_header(tmp_path):
    path = str(tmp_path / 'glossary.xlsx')
    glossary.write(path, [_entry('cloud', '云')])
    wb = openpyxl.load_workbook(path)
    header = [c.value for c in next(wb.active.iter_rows(min_row=1, max_row=1))]
    assert header == glossary.COLUMNS
