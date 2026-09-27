"""Global settings tool (DESIGN.md 15.4 P2). Registered exactly like every
other tool -- ``group=''`` lands it under the shell's 其它 section, and a
large ``order`` sorts it to the very bottom of the sidebar and home grid.
main_window.py never special-cases it."""
import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.settings.page import SettingsPage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                     'resources', 'icons', 'settings.svg')

register(ToolSpec(
    id='settings',
    name='设置',
    description='跨工具共享的全局偏好，例如默认输出目录',
    icon=_ICON,
    group='',
    order=900,
    page_factory=SettingsPage,
))
