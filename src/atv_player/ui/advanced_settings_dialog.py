from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from atv_player.models import AppConfig
from atv_player.network_proxy import ProxyConfig, ProxyDecider, ProxyRuleError


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
        self.resize(680, 440)

        self.settings_tabs = QTabWidget()
        self.metadata_tab = QWidget()
        self.network_proxy_tab = QWidget()
        self.metadata_group = QGroupBox("元数据增强配置")
        self.metadata_enabled_checkbox = QCheckBox("启用元数据增强")
        self.episode_title_enhancement_checkbox = QCheckBox("启用剧集标题增强")
        self.douban_cookie_edit = QPlainTextEdit()
        self.douban_cookie_edit.setPlaceholderText("填写豆瓣 Cookie；留空时跳过本地豆瓣抓取")
        self.tmdb_api_key_edit = QLineEdit()
        self.tmdb_api_key_edit.setPlaceholderText("填写 TMDB API Key")
        self.bangumi_access_token_edit = QLineEdit()
        self.bangumi_access_token_edit.setPlaceholderText("可选；留空时使用匿名访问")
        self.network_proxy_group = QGroupBox("网络代理配置")
        self.network_proxy_mode_combo = QComboBox()
        self.network_proxy_mode_combo.addItem("直连", "direct")
        self.network_proxy_mode_combo.addItem("系统代理", "system")
        self.network_proxy_mode_combo.addItem("HTTP", "http")
        self.network_proxy_mode_combo.addItem("HTTPS", "https")
        self.network_proxy_mode_combo.addItem("SOCKS5", "socks5")
        self.network_proxy_url_edit = QLineEdit()
        self.network_proxy_url_edit.setPlaceholderText("例如 socks5://user:pass@127.0.0.1:1080")
        self.network_proxy_bypass_rules_edit = QPlainTextEdit()
        self.network_proxy_bypass_rules_edit.setPlaceholderText("一行一条，例如 localhost 或 10.0.0.0/8")
        self.network_proxy_scope_label = QLabel(
            "覆盖范围：API、元数据、解析源、弹幕、海报、插件下载、HLS 上游请求、yt-dlp"
        )
        self.network_proxy_scope_label.setWordWrap(True)
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")

        self.metadata_enabled_checkbox.setChecked(config.metadata_enhancement_enabled)
        self.episode_title_enhancement_checkbox.setChecked(config.episode_title_enhancement_enabled)
        self.douban_cookie_edit.setPlainText(config.metadata_douban_cookie)
        self.tmdb_api_key_edit.setText(config.metadata_tmdb_api_key)
        self.bangumi_access_token_edit.setText(config.metadata_bangumi_access_token)
        self.network_proxy_mode_combo.setCurrentIndex(
            max(0, self.network_proxy_mode_combo.findData(config.network_proxy_mode))
        )
        self.network_proxy_url_edit.setText(config.network_proxy_url)
        self.network_proxy_bypass_rules_edit.setPlainText("\n".join(config.network_proxy_bypass_rules))

        metadata_layout = QFormLayout()
        metadata_layout.addRow(self.metadata_enabled_checkbox)
        metadata_layout.addRow(self.episode_title_enhancement_checkbox)
        metadata_layout.addRow("TMDB API Key", self.tmdb_api_key_edit)
        metadata_layout.addRow("Bangumi Access Token", self.bangumi_access_token_edit)
        metadata_layout.addRow("豆瓣 Cookie", self.douban_cookie_edit)
        self.metadata_group.setLayout(metadata_layout)
        metadata_tab_layout = QVBoxLayout(self.metadata_tab)
        metadata_tab_layout.addWidget(self.metadata_group)
        metadata_tab_layout.addStretch(1)

        network_proxy_layout = QFormLayout()
        network_proxy_layout.addRow("代理模式", self.network_proxy_mode_combo)
        network_proxy_layout.addRow("代理地址", self.network_proxy_url_edit)
        network_proxy_layout.addRow("直连规则", self.network_proxy_bypass_rules_edit)
        network_proxy_layout.addRow("覆盖范围", self.network_proxy_scope_label)
        self.network_proxy_group.setLayout(network_proxy_layout)
        network_proxy_tab_layout = QVBoxLayout(self.network_proxy_tab)
        network_proxy_tab_layout.addWidget(self.network_proxy_group)
        network_proxy_tab_layout.addStretch(1)

        self.settings_tabs.addTab(self.metadata_tab, "元数据")
        self.settings_tabs.addTab(self.network_proxy_tab, "网络代理")

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.settings_tabs)
        layout.addLayout(button_row)

        self.metadata_enabled_checkbox.toggled.connect(self._sync_metadata_inputs)
        self.network_proxy_mode_combo.currentIndexChanged.connect(self._sync_network_proxy_inputs)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self._sync_metadata_inputs(self.metadata_enabled_checkbox.isChecked())
        self._sync_network_proxy_inputs()

    def _sync_metadata_inputs(self, enabled: bool) -> None:
        self.episode_title_enhancement_checkbox.setEnabled(enabled)
        self.douban_cookie_edit.setEnabled(enabled)
        self.tmdb_api_key_edit.setEnabled(enabled)
        self.bangumi_access_token_edit.setEnabled(enabled)

    def _sync_network_proxy_inputs(self) -> None:
        manual_mode = self.network_proxy_mode_combo.currentData() in {"http", "https", "socks5"}
        self.network_proxy_url_edit.setEnabled(manual_mode)

    def _validated_network_proxy_values(self) -> tuple[str, str, list[str]] | None:
        mode = str(self.network_proxy_mode_combo.currentData() or "direct")
        proxy_url = self.network_proxy_url_edit.text().strip()
        bypass_rules = [
            line.strip()
            for line in self.network_proxy_bypass_rules_edit.toPlainText().splitlines()
            if line.strip()
        ]
        if mode in {"http", "https", "socks5"} and not proxy_url:
            QMessageBox.warning(self, "代理地址无效", "手动代理模式需要填写代理地址")
            return None
        scheme_errors = {
            "http": "HTTP 模式要求 http:// 代理地址",
            "https": "HTTPS 模式要求 https:// 代理地址",
            "socks5": "SOCKS5 模式要求 socks5:// 代理地址",
        }
        expected_prefix = f"{mode}://"
        if mode in scheme_errors and proxy_url and not proxy_url.startswith(expected_prefix):
            QMessageBox.warning(self, "代理地址无效", scheme_errors[mode])
            return None
        try:
            ProxyDecider(ProxyConfig(mode="direct", proxy_url="", bypass_rules=bypass_rules))
        except ProxyRuleError as exc:
            QMessageBox.warning(self, "直连规则无效", str(exc))
            return None
        return mode, proxy_url, bypass_rules

    def _save(self) -> None:
        proxy_values = self._validated_network_proxy_values()
        if proxy_values is None:
            return
        self._config.metadata_enhancement_enabled = self.metadata_enabled_checkbox.isChecked()
        self._config.episode_title_enhancement_enabled = self.episode_title_enhancement_checkbox.isChecked()
        self._config.metadata_douban_cookie = self.douban_cookie_edit.toPlainText().strip()
        self._config.metadata_tmdb_api_key = self.tmdb_api_key_edit.text().strip()
        self._config.metadata_bangumi_access_token = self.bangumi_access_token_edit.text().strip()
        self._config.network_proxy_mode, self._config.network_proxy_url, self._config.network_proxy_bypass_rules = proxy_values
        self._save_config()
        self.accept()
