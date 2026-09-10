import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.term_management.page import TermManagementPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'term_management.svg')

register(ToolSpec(
    id='term_management',
    name='术语管理',
    description='维护双语术语表，并对照已有翻译记忆库检查禁用译法',
    icon=_ICON,
    page_factory=TermManagementPage,
))
