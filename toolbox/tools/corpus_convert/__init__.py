import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.corpus_convert.page import CorpusConvertPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'corpus_convert.svg')

register(ToolSpec(
    id='corpus_convert',
    name='语料转换',
    description='双语文件 (docx/xlsx/csv) ↔ 语料库格式 (sdltm/tmx) 互转',
    icon=_ICON,
    page_factory=CorpusConvertPage,
))
