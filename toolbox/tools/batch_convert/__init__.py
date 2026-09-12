import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.batch_convert.page import BatchConvertPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'batch_convert.svg')

register(ToolSpec(
    id='batch_convert',
    name='批量转换',
    description='一次性转换多个双语文件/语料库文件为 sdltm/tmx/csv',
    icon=_ICON,
    page_factory=BatchConvertPage,
))
