import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.alignment_check.page import AlignmentCheckPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'alignment_check.svg')

register(ToolSpec(
    id='alignment_check',
    name='对齐检查',
    description='对着一个双语文档（docx/xlsx/csv/tsv）预览句子对齐结果，不写文件',
    icon=_ICON,
    page_factory=AlignmentCheckPage,
))
