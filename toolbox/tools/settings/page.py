"""全局设置工具页 (DESIGN.md 15.4 P2).

A deliberately narrow surface for the handful of *cross-tool* preferences
that deserve one place to look at and change -- not a dumping ground for
every page's own form state (those keep living in their own
``restore_settings()``/``save_settings()`` soft contract, unchanged).
Today that's exactly one item: a shared 默认输出目录.

Scope note from the backlog: 界面缩放/字体 was flagged the lowest-priority
item and gated on first confirming the QSS font sizes are all relative /
can be driven by one global multiplier -- that assessment hasn't happened,
so it's intentionally out of this page rather than half-implemented.

The value persists the instant it changes (via ``toolbox.settings``), so it
survives a restart without depending on the window-close ``save_settings``
hook -- which is the right call for a global preference the user set
precisely so it *would* stick.
"""
import os

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QVBoxLayout,
    QWidget,
)

from toolbox import settings
from toolbox.widgets import page_shell, section


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer, _, _ = page_shell(
            self,
            '设置',
            '跨工具共享的全局偏好',
            spacing=18,
        )

        body = QWidget()
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText('（未设置）')
        self.output_dir_edit.editingFinished.connect(self._save_output_dir)
        self.output_dir_edit.setToolTip(
            '各工具页“选择输出位置/浏览…”对话框在你从没记过它自己“上次目录”时的兜底起点')
        browse_btn = QPushButton('浏览…')
        browse_btn.setObjectName('primaryButton')
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self.output_dir_edit, 1)
        dir_row.addWidget(browse_btn)
        vbox.addLayout(dir_row)

        hint = QLabel(
            '说明：各工具页仍各自记住“上次目录”；这里的默认输出目录只在某个工具页'
            '从没记过“上次目录”时兜底使用，两者不冲突。留空表示不启用。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #6B7280; font-size: 12px;')
        vbox.addWidget(hint)

        outer.addWidget(section('默认输出目录', body))

        # Load the persisted value once, at construction (a global pref is
        # this page's own whole subject, so it doesn't wait for the shell's
        # restore_settings hook the way per-tool form state does).
        self.output_dir_edit.setText(settings.get_default_output_dir())

    def _save_output_dir(self):
        settings.set_default_output_dir(self.output_dir_edit.text().strip())

    def _browse_output_dir(self):
        start = self.output_dir_edit.text().strip() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, '选择默认输出目录', start)
        if not path:
            return
        self.output_dir_edit.setText(path)
        settings.set_default_output_dir(path)
