from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
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
        self.resize(640, 320)

        self.douban_cookie_edit = QPlainTextEdit()
        self.douban_cookie_edit.setPlaceholderText("填写豆瓣 Cookie；留空时跳过本地豆瓣抓取")
        self.tmdb_api_key_edit = QLineEdit()
        self.tmdb_api_key_edit.setPlaceholderText("填写 TMDB API Key")
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")

        self.douban_cookie_edit.setPlainText(config.metadata_douban_cookie)
        self.tmdb_api_key_edit.setText(config.metadata_tmdb_api_key)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("豆瓣 Cookie"))
        layout.addWidget(self.douban_cookie_edit)
        layout.addWidget(QLabel("TMDB API Key"))
        layout.addWidget(self.tmdb_api_key_edit)
        layout.addLayout(button_row)

        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

    def _save(self) -> None:
        self._config.metadata_douban_cookie = self.douban_cookie_edit.toPlainText().strip()
        self._config.metadata_tmdb_api_key = self.tmdb_api_key_edit.text().strip()
        self._save_config()
        self.accept()
