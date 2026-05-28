from __future__ import annotations

import json
import queue
import shutil
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
    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: None
    )

    with pytest.raises(ValueError, match="未找到 Node.js 运行环境"):
        NodeSpider(
            plugin_path=tmp_path / "plugin.js",
            cache_dir=tmp_path / "cache",
            plugin_id=1,
        )


def test_node_spider_calls_bridge_methods(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess(
        [
            json.dumps({"id": 1, "ok": True, "result": "JS插件"}) + "\n",
            json.dumps({"id": 2, "ok": True, "result": {"class": [], "list": []}})
            + "\n",
            json.dumps({"id": 3, "ok": True, "result": True}) + "\n",
        ]
    )
    popen_calls: list[list[str]] = []

    def fake_popen(command, **kwargs):
        popen_calls.append(command)
        return fake_process

    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node"
    )
    monkeypatch.setattr("atv_player.plugins.node_spider.subprocess.Popen", fake_popen)

    spider = NodeSpider(
        plugin_path=plugin_path,
        cache_dir=tmp_path / "cache",
        plugin_id=7,
        timeout_seconds=1,
    )

    assert spider.getName() == "JS插件"
    assert spider.homeContent(False) == {"class": [], "list": []}
    assert spider.supports_search() is True
    assert popen_calls[0][0] == "/usr/bin/node"
    assert "--plugin" in popen_calls[0]
    assert str(plugin_path) in popen_calls[0]
    assert json.loads(fake_process.stdin.lines[0]) == {
        "id": 1,
        "method": "getName",
        "args": [],
    }
    assert json.loads(fake_process.stdin.lines[1]) == {
        "id": 2,
        "method": "home",
        "args": [False],
    }
    assert json.loads(fake_process.stdin.lines[2]) == {
        "id": 3,
        "method": "hasMethod",
        "args": ["search"],
    }


def test_node_spider_raises_bridge_error(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.js"
    plugin_path.write_text("export default {}", encoding="utf-8")
    fake_process = FakeProcess(
        [json.dumps({"id": 1, "ok": False, "error": "boom"}) + "\n"]
    )

    monkeypatch.setattr(
        "atv_player.plugins.node_spider.shutil.which", lambda name: "/usr/bin/node"
    )
    monkeypatch.setattr(
        "atv_player.plugins.node_spider.subprocess.Popen",
        lambda command, **kwargs: fake_process,
    )

    spider = NodeSpider(
        plugin_path=plugin_path,
        cache_dir=tmp_path / "cache",
        plugin_id=7,
        timeout_seconds=1,
    )

    with pytest.raises(RuntimeError, match="boom"):
        spider.homeContent(False)


pytestmark_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not installed"
)


@pytestmark_node
def test_node_bridge_loads_default_export_fixture(tmp_path: Path) -> None:
    plugin_path = tmp_path / "default-plugin.mjs"
    plugin_path.write_text(
        """
export default {
  init(ext) { this.ext = ext },
  getName() { return `默认:${this.ext}` },
  home(filter) { return { class: [{ type_id: "hot", type_name: "热门" }], list: [] } },
  category(tid, pg, filter, extend) {
    return { list: [{ vod_id: `${tid}-${pg}`, vod_name: "分类" }], total: 1 }
  },
  detail(id) {
    return {
      list: [{
        vod_id: id,
        vod_name: "详情",
        vod_play_from: "默认线",
        vod_play_url: "第1集$/play/1"
      }]
    }
  },
  search(key, quick, pg) {
    return { list: [{ vod_id: key, vod_name: key }], total: 1 }
  },
  play(flag, id, vipFlags) {
    return {
      parse: 0,
      url: `https://media.example${id}.m3u8`,
      header: { Referer: "https://site.example" }
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(
        plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=1
    )

    spider.init("ext")

    assert spider.getName() == "默认:ext"
    assert spider.homeContent(False)["class"][0]["type_name"] == "热门"
    assert spider.categoryContent("hot", "2", False, {})["list"][0]["vod_id"] == "hot-2"
    assert spider.detailContent(["abc"])["list"][0]["vod_name"] == "详情"
    assert spider.searchContent("关键字", False, "1")["list"][0]["vod_name"] == "关键字"
    assert (
        spider.playerContent("默认线", "/play/1", [])["url"]
        == "https://media.example/play/1.m3u8"
    )
    spider.destroy()


@pytestmark_node
def test_node_bridge_loads_js_eval_return_fixture_and_local_cache(
    tmp_path: Path,
) -> None:
    plugin_path = tmp_path / "eval-plugin.mjs"
    plugin_path.write_text(
        """
export function __jsEvalReturn() {
  return {
    init(ext) { local.set("rule", "ext", ext) },
    getName() { return `缓存:${local.get("rule", "ext")}` },
    home() {
      return JSON.stringify({
        class: [],
        list: [{ vod_id: "1", vod_name: "首页" }]
      })
    },
    category() { return { list: [], total: 0 } },
    detail(id) {
      return {
        list: [{
          vod_id: id,
          vod_name: "详情",
          vod_play_from: "默认",
          vod_play_url: "正片$https://media.example/a.m3u8"
        }]
      }
    },
    play(flag, id) { return { parse: 0, url: id } }
  }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(
        plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=2
    )

    spider.init("abc")

    assert spider.getName() == "缓存:abc"
    assert spider.homeContent(False)["list"][0]["vod_name"] == "首页"
    spider.destroy()
