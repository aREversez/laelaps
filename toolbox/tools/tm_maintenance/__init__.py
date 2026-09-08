import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.tm_maintenance.page import TmMaintenancePage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'tm_maintenance.svg')

register(ToolSpec(
    id='tm_maintenance',
    name='语料维护',
    description='翻译记忆库 (tmx/sdltm) 清理、合并、统计',
    icon=_ICON,
    page_factory=TmMaintenancePage,
))
