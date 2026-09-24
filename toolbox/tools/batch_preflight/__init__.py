import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.batch_preflight.page import BatchPreflightPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'batch_preflight.svg')

register(ToolSpec(
    id='batch_preflight',
    name='批量预检',
    description='批量转换前先体检：版式置信度、合并单元格、空表格、语言方向是否对',
    icon=_ICON,
    page_factory=BatchPreflightPage,
))
