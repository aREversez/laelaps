import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.qa_check.page import QaCheckPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'qa_check.svg')

register(ToolSpec(
    id='qa_check',
    name='QA 检查',
    description='对已有的翻译记忆库 (tmx/sdltm) 跑质量检查，生成审阅报告',
    icon=_ICON,
    page_factory=QaCheckPage,
))
