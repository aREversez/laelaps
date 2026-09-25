"""Home tool: the toolbox's landing page -- a registry-driven grid of
tool tiles (see page.py). Registered like any other tool, with order=0
so it sorts to the top of the sidebar (heading its own 概览 section) and
the stack's default page -- main_window.py orders by ToolSpec.order and
never hardcodes anything about this (or any) specific tool."""
import os

from toolbox.registry import ToolSpec, register
from toolbox.tools.home.page import HomePage

_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                     'resources', 'icons', 'home.svg')

register(ToolSpec(
    id='home',
    name='首页',
    description='所有工具总览，点击卡片直达对应工具',
    icon=_ICON,
    group='概览',
    order=0,
    page_factory=HomePage,
))
