import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.batch_alignment_check.page import BatchAlignmentCheckPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'batch_alignment_check.svg')

register(ToolSpec(
    id='batch_alignment_check',
    name='批量对齐检查',
    description='一次性检查多个双语文档的句子对齐结果，不生成任何文件',
    icon=_ICON,
    group='检查',
    order=21,
    page_factory=BatchAlignmentCheckPage,
))
