"""全局设置工具页 (DESIGN.md 15.4 P2).

A deliberately narrow surface for the handful of *cross-tool* preferences
that deserve one place to look at and change -- not a dumping ground for
every page's own form state (those keep living in their own
``restore_settings()``/``save_settings()`` soft contract, unchanged).
Today that's two items: the UI language (界面语言) and a shared
默认输出目录.

Scope note from the backlog: 界面缩放/字体 was flagged the lowest-priority
item and gated on first confirming the QSS font sizes are all relative /
can be driven by one global multiplier -- that assessment hasn't happened,
so it's intentionally out of this page rather than half-implemented.

The value persists the instant it changes (via ``toolbox.settings``), so it
survives a restart without depending on the window-close ``save_settings``
hook -- which is the right call for a global preference the user set
precisely so it *would* stick.

界面语言 is applied at startup only (see ``toolbox/i18n.py`` for why), so
picking a language here saves it and says it applies after a restart rather
than half-retranslating a window whose pages were already built.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QVBoxLayout, QWidget,
)

from toolbox import i18n, settings
from toolbox.i18n import tr
from toolbox.widgets import compact_combo, page_shell, section


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer, _, _ = page_shell(
            self,
            tr('设置'),
            tr('跨工具共享的全局偏好'),
            spacing=18,
        )

        lang_body = QWidget()
        lang_vbox = QVBoxLayout(lang_body)
        lang_vbox.setContentsMargins(0, 0, 0, 0)
        lang_vbox.setSpacing(8)
        self.language_combo = QComboBox()
        self.language_combo.addItem(tr('跟随系统'), i18n.AUTO)
        for code, native_name in i18n.LANGUAGES:
            self.language_combo.addItem(native_name, code)
        self.language_combo.currentIndexChanged.connect(self._save_language)
        compact_combo(self.language_combo)
        lang_vbox.addWidget(self.language_combo, 0, Qt.AlignLeft)
        lang_hint = QLabel(tr('更改后需重新启动应用才会生效。'))
        lang_hint.setWordWrap(True)
        lang_hint.setStyleSheet('color: #6B7280; font-size: 12px;')
        lang_vbox.addWidget(lang_hint)
        outer.addWidget(section(tr('界面语言'), lang_body))

        body = QWidget()
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText(tr('（未设置）'))
        self.output_dir_edit.editingFinished.connect(self._save_output_dir)
        self.output_dir_edit.setToolTip(
            tr('各工具页“选择输出位置/浏览…”对话框在你从没记过它自己“上次目录”时的兜底起点'))
        browse_btn = QPushButton(tr('浏览…'))
        browse_btn.setObjectName('primaryButton')
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self.output_dir_edit, 1)
        dir_row.addWidget(browse_btn)
        vbox.addLayout(dir_row)

        hint = QLabel(
            tr('说明：各工具页仍各自记住“上次目录”；这里的默认输出目录只在某个工具页'
            '从没记过“上次目录”时兜底使用，两者不冲突。留空表示不启用。'))
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #6B7280; font-size: 12px;')
        vbox.addWidget(hint)

        outer.addWidget(section(tr('默认输出目录'), body))
        # Trailing stretch: page_shell's card fills the scroll viewport, so
        # without this a lone short section gets stretched to full height and
        # its title label absorbs the slack -- a cavernous accent bar with the
        # field floating at the bottom. The stretch keeps the card hugging its
        # content at the top like every other page.
        outer.addStretch(1)

        # Load the persisted value once, at construction (a global pref is
        # this page's own whole subject, so it doesn't wait for the shell's
        # restore_settings hook the way per-tool form state does).
        self.output_dir_edit.setText(settings.get_default_output_dir())
        # Shows the saved *choice* ('auto' or a code), not the language that
        # happens to be active this session -- the two differ until the
        # next restart, and 跟随系统 must read as "follow system", not as
        # whatever it resolved to. Signals blocked so restoring the
        # selection doesn't write the same value straight back.
        self.language_combo.blockSignals(True)
        idx = self.language_combo.findData(settings.get_ui_language() or i18n.AUTO)
        self.language_combo.setCurrentIndex(max(idx, 0))
        self.language_combo.blockSignals(False)

    def _save_language(self, _index):
        settings.set_ui_language(self.language_combo.currentData())

    def _save_output_dir(self):
        settings.set_default_output_dir(self.output_dir_edit.text().strip())

    def _browse_output_dir(self):
        start = self.output_dir_edit.text().strip() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, tr('选择默认输出目录'), start)
        if not path:
            return
        self.output_dir_edit.setText(path)
        settings.set_default_output_dir(path)
