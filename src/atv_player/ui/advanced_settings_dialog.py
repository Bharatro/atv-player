from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import AppConfig


class AdvancedSettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        save_config: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._save_config = save_config
        self.setWindowTitle("高级设置")
        self.resize(640, 360)

        self.metadata_group = QGroupBox("元数据增强配置")
        self.metadata_enabled_checkbox = QCheckBox("启用元数据增强")
        self.episode_title_enhancement_checkbox = QCheckBox("启用剧集标题增强")
        self.douban_cookie_edit = QPlainTextEdit()
        self.douban_cookie_edit.setPlaceholderText("填写豆瓣 Cookie；留空时跳过本地豆瓣抓取")
        self.tmdb_api_key_edit = QLineEdit()
        self.tmdb_api_key_edit.setPlaceholderText("填写 TMDB API Key")
        self.bangumi_access_token_edit = QLineEdit()
        self.bangumi_access_token_edit.setPlaceholderText("可选；留空时使用匿名访问")
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")

        self.metadata_enabled_checkbox.setChecked(config.metadata_enhancement_enabled)
        self.episode_title_enhancement_checkbox.setChecked(config.episode_title_enhancement_enabled)
        self.douban_cookie_edit.setPlainText(config.metadata_douban_cookie)
        self.tmdb_api_key_edit.setText(config.metadata_tmdb_api_key)
        self.bangumi_access_token_edit.setText(config.metadata_bangumi_access_token)

        metadata_layout = QFormLayout()
        metadata_layout.addRow(self.metadata_enabled_checkbox)
        metadata_layout.addRow(self.episode_title_enhancement_checkbox)
        metadata_layout.addRow("TMDB API Key", self.tmdb_api_key_edit)
        metadata_layout.addRow("Bangumi Access Token", self.bangumi_access_token_edit)
        metadata_layout.addRow("豆瓣 Cookie", self.douban_cookie_edit)
        self.metadata_group.setLayout(metadata_layout)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.metadata_group)
        layout.addLayout(button_row)

        self.metadata_enabled_checkbox.toggled.connect(self._sync_metadata_inputs)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self._sync_metadata_inputs(self.metadata_enabled_checkbox.isChecked())

    def _sync_metadata_inputs(self, enabled: bool) -> None:
        self.episode_title_enhancement_checkbox.setEnabled(enabled)
        self.douban_cookie_edit.setEnabled(enabled)
        self.tmdb_api_key_edit.setEnabled(enabled)
        self.bangumi_access_token_edit.setEnabled(enabled)

    def _save(self) -> None:
        self._config.metadata_enhancement_enabled = self.metadata_enabled_checkbox.isChecked()
        self._config.episode_title_enhancement_enabled = self.episode_title_enhancement_checkbox.isChecked()
        self._config.metadata_douban_cookie = self.douban_cookie_edit.toPlainText().strip()
        self._config.metadata_tmdb_api_key = self.tmdb_api_key_edit.text().strip()
        self._config.metadata_bangumi_access_token = self.bangumi_access_token_edit.text().strip()
        self._save_config()
        self.accept()
