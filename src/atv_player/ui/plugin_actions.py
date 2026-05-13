from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QInputDialog, QMessageBox


@dataclass(slots=True, frozen=True)
class PluginActionResult:
    changed: bool
    plugin_id: int | None = None


class PluginActions:
    def __init__(self, plugin_manager) -> None:
        self.plugin_manager = plugin_manager

    def list_plugins(self):
        return list(self.plugin_manager.list_plugins())

    def get_plugin(self, plugin_id: int):
        return next((plugin for plugin in self.list_plugins() if int(plugin.id) == int(plugin_id)), None)

    def prompt_display_name(self, parent, current: str) -> str:
        value, accepted = QInputDialog.getText(parent, "编辑名称", "显示名称", text=current)
        return value.strip() if accepted else ""

    def prompt_config_text(self, parent, current: str) -> str | None:
        value, accepted = QInputDialog.getMultiLineText(parent, "编辑配置", "配置文本", current)
        return value if accepted else None

    def _warning(self, parent, title: str, exc: Exception) -> PluginActionResult:
        QMessageBox.warning(parent, title, str(exc))
        return PluginActionResult(changed=False, plugin_id=None)

    def apply_rename(self, plugin_id: int, display_name: str) -> PluginActionResult:
        self.plugin_manager.rename_plugin(plugin_id, display_name)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def apply_config(self, plugin_id: int, config_text: str) -> PluginActionResult:
        self.plugin_manager.set_plugin_config(plugin_id, config_text)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def apply_toggle_enabled(self, plugin_id: int, enabled: bool) -> PluginActionResult:
        self.plugin_manager.set_plugin_enabled(plugin_id, enabled)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def apply_refresh(self, plugin_id: int) -> PluginActionResult:
        self.plugin_manager.refresh_plugin(plugin_id)
        return PluginActionResult(changed=True, plugin_id=plugin_id)

    def refresh_plugin(self, parent, plugin_id: int) -> PluginActionResult:
        try:
            return self.apply_refresh(plugin_id)
        except Exception as exc:
            return self._warning(parent, "刷新失败", exc)

    def rename_plugin(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        display_name = self.prompt_display_name(parent, plugin.display_name or "").strip()
        if not display_name:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            return self.apply_rename(plugin_id, display_name)
        except Exception as exc:
            return self._warning(parent, "编辑名称失败", exc)

    def edit_plugin_config(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        config_text = self.prompt_config_text(parent, plugin.config_text)
        if config_text is None:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            return self.apply_config(plugin_id, config_text)
        except Exception as exc:
            return self._warning(parent, "编辑配置失败", exc)

    def toggle_plugin_enabled(self, parent, plugin_id: int) -> PluginActionResult:
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return PluginActionResult(changed=False, plugin_id=None)
        try:
            return self.apply_toggle_enabled(plugin_id, not bool(plugin.enabled))
        except Exception as exc:
            return self._warning(parent, "更新插件状态失败", exc)
