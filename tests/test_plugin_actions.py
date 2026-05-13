from types import SimpleNamespace

from atv_player.ui.plugin_actions import PluginActionResult, PluginActions
import atv_player.ui.plugin_actions as plugin_actions_module


class FakePluginManager:
    def __init__(self) -> None:
        self.plugins = [
            SimpleNamespace(id=1, display_name="插件一", enabled=True, config_text="token=1\n"),
            SimpleNamespace(id=2, display_name="插件二", enabled=False, config_text="token=2\n"),
        ]
        self.rename_calls: list[tuple[int, str]] = []
        self.config_calls: list[tuple[int, str]] = []
        self.toggle_calls: list[tuple[int, bool]] = []
        self.refresh_calls: list[int] = []

    def list_plugins(self):
        return list(self.plugins)

    def rename_plugin(self, plugin_id: int, display_name: str) -> None:
        self.rename_calls.append((plugin_id, display_name))

    def set_plugin_config(self, plugin_id: int, config_text: str) -> None:
        self.config_calls.append((plugin_id, config_text))

    def set_plugin_enabled(self, plugin_id: int, enabled: bool) -> None:
        self.toggle_calls.append((plugin_id, enabled))

    def refresh_plugin(self, plugin_id: int) -> None:
        self.refresh_calls.append(plugin_id)


def test_plugin_actions_rename_returns_changed_result_for_trimmed_name(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_display_name", lambda parent, current: "  新名称  ")

    result = actions.rename_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.rename_calls == [(1, "新名称")]


def test_plugin_actions_rename_returns_unchanged_when_prompt_is_empty(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_display_name", lambda parent, current: "")

    result = actions.rename_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=False, plugin_id=None)
    assert manager.rename_calls == []


def test_plugin_actions_edit_config_returns_changed_result(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    monkeypatch.setattr(actions, "prompt_config_text", lambda parent, current: "cookie=1\n")

    result = actions.edit_plugin_config(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.config_calls == [(1, "cookie=1\n")]


def test_plugin_actions_toggle_uses_inverse_enabled_state() -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)

    result = actions.toggle_plugin_enabled(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=True, plugin_id=1)
    assert manager.toggle_calls == [(1, False)]


def test_plugin_actions_refresh_returns_changed_result() -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)

    result = actions.refresh_plugin(parent=None, plugin_id=2)

    assert result == PluginActionResult(changed=True, plugin_id=2)
    assert manager.refresh_calls == [2]


def test_plugin_actions_shows_warning_and_returns_unchanged_on_manager_error(monkeypatch) -> None:
    manager = FakePluginManager()
    actions = PluginActions(manager)
    warning_messages: list[str] = []

    def raise_refresh(plugin_id: int) -> None:
        raise RuntimeError("boom")

    manager.refresh_plugin = raise_refresh
    monkeypatch.setattr(
        plugin_actions_module.QMessageBox,
        "warning",
        lambda parent, title, message: warning_messages.append(message),
    )

    result = actions.refresh_plugin(parent=None, plugin_id=1)

    assert result == PluginActionResult(changed=False, plugin_id=None)
    assert warning_messages == ["boom"]
