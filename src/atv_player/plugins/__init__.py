from __future__ import annotations

from dataclasses import dataclass
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from atv_player.danmaku.preferences import DanmakuSeriesPreferenceStore
from atv_player.models import SpiderPluginAction, SpiderPluginActionContext, SpiderPluginConfig
from atv_player.plugins.controller import SpiderPluginController
from atv_player.plugins.loader import LoadedSpiderPlugin, SpiderPluginLoader
from atv_player.plugins.repository import SpiderPluginRepository


@dataclass(slots=True)
class SpiderPluginDefinition:
    id: int
    title: str
    controller: object
    search_enabled: bool


def _default_plugin_name(source_type: str, source_value: str) -> str:
    if source_type == "remote":
        parsed = urlparse(source_value)
        path = unquote(parsed.path or "")
        name = Path(path).stem or Path(path).name.removesuffix(".py")
        if name:
            return name
    return Path(source_value).stem or Path(source_value).name.removesuffix(".py")


def _coerce_plugin_action(payload: object) -> SpiderPluginAction | None:
    if not isinstance(payload, dict):
        return None
    action_id = str(payload.get("id") or "").strip()
    label = str(payload.get("label") or "").strip()
    if not action_id or not label:
        return None
    return SpiderPluginAction(
        id=action_id,
        label=label,
        enabled=bool(payload.get("enabled", True)),
        visible=bool(payload.get("visible", True)),
        tooltip=str(payload.get("tooltip") or "").strip(),
    )


class SpiderPluginManager:
    def __init__(
        self,
        repository: SpiderPluginRepository,
        loader: SpiderPluginLoader,
        playback_history_repository=None,
    ) -> None:
        self._repository = repository
        self._loader = loader
        self._playback_history_repository = playback_history_repository
        self._playback_parser_service = None
        self._preferred_parse_key_loader = None
        self._base_url_loader = None
        self._danmaku_service = None
        self._danmaku_preference_store = DanmakuSeriesPreferenceStore()

    def list_plugins(self) -> list[SpiderPluginConfig]:
        return self._repository.list_plugins()

    def add_local_plugin(self, path: str) -> None:
        plugin = self._repository.add_plugin("local", path, Path(path).stem)
        self.refresh_plugin(plugin.id)

    def add_remote_plugin(self, url: str) -> None:
        name = _default_plugin_name("remote", url)
        plugin = self._repository.add_plugin("remote", url, name)
        self.refresh_plugin(plugin.id)

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        plugin = self._repository.get_plugin(plugin_id)
        self._repository.update_plugin(
            plugin_id,
            display_name=display_name,
            enabled=plugin.enabled,
            cached_file_path=plugin.cached_file_path,
            last_loaded_at=plugin.last_loaded_at,
            last_error=plugin.last_error,
            config_text=plugin.config_text,
        )

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        plugin = self._repository.get_plugin(plugin_id)
        self._repository.update_plugin(
            plugin_id,
            display_name=plugin.display_name,
            enabled=enabled,
            cached_file_path=plugin.cached_file_path,
            last_loaded_at=plugin.last_loaded_at,
            last_error=plugin.last_error,
            config_text=plugin.config_text,
        )

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        plugin = self._repository.get_plugin(plugin_id)
        self._repository.update_plugin(
            plugin_id,
            display_name=plugin.display_name,
            enabled=plugin.enabled,
            cached_file_path=plugin.cached_file_path,
            last_loaded_at=plugin.last_loaded_at,
            last_error=plugin.last_error,
            config_text=config_text,
        )

    def move_plugin(self, plugin_id: int, direction: int) -> None:
        self._repository.move_plugin(plugin_id, direction)

    def refresh_plugin(self, plugin_id: int) -> None:
        plugin = self._repository.get_plugin(plugin_id)
        try:
            loaded = self._loader.load(plugin, force_refresh=True)
        except Exception as exc:
            self._repository.update_plugin(
                plugin_id,
                display_name=plugin.display_name,
                enabled=plugin.enabled,
                cached_file_path=plugin.cached_file_path,
                last_loaded_at=plugin.last_loaded_at,
                last_error=str(exc),
                config_text=plugin.config_text,
            )
            self._repository.append_log(plugin.id, "error", str(exc))
            return
        self._repository.update_plugin(
            plugin_id,
            display_name=plugin.display_name,
            enabled=plugin.enabled,
            cached_file_path=loaded.config.cached_file_path,
            last_loaded_at=int(time.time()),
            last_error="",
            config_text=plugin.config_text,
        )

    def delete_plugin(self, plugin_id: int) -> None:
        self._repository.delete_plugin(plugin_id)

    def list_logs(self, plugin_id: int):
        return self._repository.list_logs(plugin_id)

    def _get_plugin(self, plugin_id: int) -> SpiderPluginConfig:
        return self._repository.get_plugin(plugin_id)

    def _load_plugin(self, plugin_id: int, *, force_refresh: bool = False) -> tuple[SpiderPluginConfig, LoadedSpiderPlugin]:
        plugin = self._get_plugin(plugin_id)
        return plugin, self._loader.load(plugin, force_refresh=force_refresh)

    def _plugin_title(self, plugin: SpiderPluginConfig, loaded: LoadedSpiderPlugin) -> str:
        return plugin.display_name or loaded.plugin_name or _default_plugin_name(
            plugin.source_type, plugin.source_value
        )

    def _append_plugin_log(self, plugin_id: int, level: str, message: str) -> None:
        self._repository.append_log(plugin_id, level, message)

    def _build_action_context(
        self,
        plugin: SpiderPluginConfig,
        loaded: LoadedSpiderPlugin,
        *,
        parent=None,
    ) -> SpiderPluginActionContext:
        return SpiderPluginActionContext(
            parent=parent,
            plugin_id=plugin.id,
            plugin_name=self._plugin_title(plugin, loaded),
            config_text=plugin.config_text,
            set_config_text=lambda text, plugin_id=plugin.id: self.set_plugin_config(plugin_id, text),
            refresh_plugin=lambda plugin_id=plugin.id: self.refresh_plugin(plugin_id),
            log=lambda level, message, plugin_id=plugin.id: self._append_plugin_log(plugin_id, level, message),
        )

    def list_plugin_actions(self, plugin_id: int) -> list[SpiderPluginAction]:
        plugin, loaded = self._load_plugin(plugin_id)
        get_actions = getattr(loaded.spider, "getManagerActions", None)
        if not callable(get_actions):
            return []
        actions: list[SpiderPluginAction] = []
        for payload in get_actions() or []:
            action = _coerce_plugin_action(payload)
            if action is None:
                self._repository.append_log(plugin.id, "error", f"插件动作声明无效: {payload!r}")
                continue
            if action.visible:
                actions.append(action)
        return actions

    def run_plugin_action(self, plugin_id: int, action_id: str, parent=None) -> None:
        actions = self.list_plugin_actions(plugin_id)
        action = next((item for item in actions if item.id == action_id), None)
        if action is None:
            raise ValueError(f"插件动作未注册: {action_id}")
        plugin, loaded = self._load_plugin(plugin_id)
        runner = getattr(loaded.spider, "runManagerAction", None)
        if not callable(runner):
            raise ValueError(f"插件不支持动作执行: {action_id}")
        context = self._build_action_context(plugin, loaded, parent=parent)
        try:
            runner(action_id, context)
        except Exception as exc:
            self._repository.append_log(plugin.id, "error", f"插件动作执行失败[{action_id}]: {exc}")
            raise

    def load_enabled_plugins(self, drive_detail_loader=None, offline_download_detail_loader=None) -> list[SpiderPluginDefinition]:
        definitions: list[SpiderPluginDefinition] = []
        for plugin in self._repository.list_plugins():
            if not plugin.enabled:
                continue
            try:
                loaded = self._loader.load(plugin)
            except Exception as exc:
                self._repository.update_plugin(
                    plugin.id,
                    display_name=plugin.display_name,
                    enabled=plugin.enabled,
                    cached_file_path=plugin.cached_file_path,
                    last_loaded_at=plugin.last_loaded_at,
                    last_error=str(exc),
                    config_text=plugin.config_text,
                )
                self._repository.append_log(plugin.id, "error", str(exc))
                continue
            title = self._plugin_title(plugin, loaded)
            controller = SpiderPluginController(
                loaded.spider,
                plugin_name=title,
                search_enabled=loaded.search_enabled,
                drive_detail_loader=drive_detail_loader,
                offline_download_detail_loader=offline_download_detail_loader,
                playback_parser_service=self._playback_parser_service,
                preferred_parse_key_loader=self._preferred_parse_key_loader,
                base_url_loader=self._base_url_loader,
                danmaku_service=self._danmaku_service,
                danmaku_preference_store=self._danmaku_preference_store,
                playback_history_loader=None
                if self._playback_history_repository is None
                else lambda vod_id, plugin_id=plugin.id: self._playback_history_repository.get_history(
                    "spider_plugin",
                    vod_id,
                    source_key=str(plugin_id),
                ),
                playback_history_saver=None
                if self._playback_history_repository is None
                else lambda vod_id, payload, source_name=title, plugin_id=plugin.id: self._playback_history_repository.save_history(
                    "spider_plugin",
                    vod_id,
                    payload,
                    source_key=str(plugin_id),
                    source_name=source_name,
                ),
            )
            definitions.append(
                SpiderPluginDefinition(
                    id=plugin.id,
                    title=title,
                    controller=controller,
                    search_enabled=loaded.search_enabled,
                )
            )
        return definitions


__all__ = [
    "LoadedSpiderPlugin",
    "SpiderPluginLoader",
    "SpiderPluginDefinition",
    "SpiderPluginManager",
]
