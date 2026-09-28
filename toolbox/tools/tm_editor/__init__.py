import os

from toolbox.i18n import tr
from toolbox.registry import ToolSpec, register
from toolbox.tools.tm_editor.page import TmEditorPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                      'resources', 'icons', 'tm_editor.svg')

register(ToolSpec(
    id='tm_editor',
    name=tr('条目编辑'),
    description=tr('打开或新建翻译记忆库（tmx/sdltm），浏览、增删改单条记录'),
    icon=_ICON,
    group=tr('术语与记忆库'),
    order=31,
    page_factory=TmEditorPage,
))
