import os

from toolbox.i18n import tr
from toolbox.registry import ToolSpec, register
from toolbox.tools.batch_convert.page import BatchConvertPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'batch_convert.svg')

register(ToolSpec(
    id='batch_convert',
    name=tr('批量转换'),
    description=tr('一次性转换多个双语文件/语料库文件为 sdltm/tmx/csv'),
    icon=_ICON,
    group=tr('转换'),
    order=11,
    page_factory=BatchConvertPage,
))
