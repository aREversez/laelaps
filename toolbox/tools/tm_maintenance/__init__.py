import os

from toolbox.i18n import tr
from toolbox.registry import ToolSpec, register
from toolbox.tools.tm_maintenance.page import TmMaintenancePage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'tm_maintenance.svg')

register(ToolSpec(
    id='tm_maintenance',
    name=tr('语料维护'),
    description=tr('翻译记忆库 (tmx/sdltm) 清理、合并、统计'),
    icon=_ICON,
    group=tr('转换'),
    order=12,
    page_factory=TmMaintenancePage,
))
