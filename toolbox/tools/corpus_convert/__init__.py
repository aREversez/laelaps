import os

from toolbox.i18n import tr
from toolbox.registry import ToolSpec, register
from toolbox.tools.corpus_convert.page import CorpusConvertPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'corpus_convert.svg')

register(ToolSpec(
    id='corpus_convert',
    name=tr('语料转换'),
    description=tr('双语文件 (docx/xlsx/csv) ↔ 语料库格式 (sdltm/tmx) 互转'),
    icon=_ICON,
    group=tr('转换'),
    order=10,
    page_factory=CorpusConvertPage,
))
