from __future__ import annotations

import json
import queue
from pathlib import Path

import pytest

from atv_player.plugins.node_spider import NodeSpider


class FakeStdin:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, value: str) -> int:
        self.lines.append(value)
        return len(value)

    def flush(self) -> None:
        return None


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = queue.Queue()
        for line in lines:
            self._lines.put(line)

    def readline(self) -> str:
        try:
            return self._lines.get_nowait()
        except queue.Empty:
            return ""


class FakeStderr:
    def readline(self) -> str:
        return ""


class FakeProcess:
    def __init__(self, lines: list[str]) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(lines)
        self.stderr = FakeStderr()
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        return 0


def test_node_spider_reports_missing_node(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("atv_player.plugins.node_spider.shutil.which", lambda name: None)

    with pytest.raises(ValueError, match="未找到 Node.js 运行环境"):
        NodeSpider(plugin_path=tmp_path / "plugin.js", cache_dir=tmp_path / "cache", plugin_id=1)


def test_node_spider_calls_bridge_methods(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess(
        [
            json.dumps({"id": 1, "ok": True, "result": "JS插件"}) + "\n",
            json.dumps({"id": 2, "ok": True, "result": {"class": [], "list": []}}) + "\n",
            json.dumps({"id": 3, "ok": True, "result": True}) + "\n",
        ]
    )
    popen_calls: list[list[str]] = []

    def fake_popen(command, **kwargs):
        popen_calls.append(command)
        return fake_process

    monkeypatch.setattr("atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node")
    monkeypatch.setattr("atv_player.plugins.node_spider.subprocess.Popen", fake_popen)

    spider = NodeSpider(plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=7, timeout_seconds=1)

    assert spider.getName() == "JS插件"
    assert spider.homeContent(False) == {"class": [], "list": []}
    assert spider.supports_search() is True
    assert popen_calls[0][0] == "/usr/bin/node"
    assert "--plugin" in popen_calls[0]
    assert str(plugin_path) in popen_calls[0]
    assert json.loads(fake_process.stdin.lines[0]) == {"id": 1, "method": "getName", "args": []}
    assert json.loads(fake_process.stdin.lines[1]) == {"id": 2, "method": "home", "args": [False]}
    assert json.loads(fake_process.stdin.lines[2]) == {"id": 3, "method": "hasMethod", "args": ["search"]}


def test_node_spider_raises_bridge_error(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess([json.dumps({"id": 1, "ok": False, "error": "boom"}) + "\n"])

    monkeypatch.setattr("atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node")
    monkeypatch.setattr("atv_player.plugins.node_spider.subprocess.Popen", lambda command, **kwargs: fake_process)

    spider = NodeSpider(plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=7, timeout_seconds=1)

    with pytest.raises(RuntimeError, match="boom"):
        spider.homeContent(False)
