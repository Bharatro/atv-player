# TvBox JS Spider Node Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TvBox JavaScript spider plugin support through the existing plugin manager when a system `node` runtime is available.

**Architecture:** Keep `SpiderPluginLoader` as the unified loader and select Python or JavaScript by resolved source suffix/content. Add a `NodeSpider` Python adapter that exposes the same spider methods as Python plugins and talks to a long-lived Node bridge over newline-delimited JSON. Reuse `SpiderPluginController`, dynamic tabs, playback mapping, plugin persistence, refresh, logs, and manager UI.

**Tech Stack:** Python 3.12, PySide6, pytest, subprocess, Node.js ESM, newline-delimited JSON, PyInstaller data collection.

---

## File Structure

- Create `src/atv_player/plugins/node_spider.py`
  - Owns Node executable detection, child process lifecycle, JSON request/response protocol, timeouts, method wrappers, and `destroy()`.
- Create `src/atv_player/plugins/js_bridge/tvbox_spider_runner.mjs`
  - Loads a TvBox JS spider module, installs compatibility globals, maps requested methods to JS functions, serializes results, and emits JSON responses.
- Create `src/atv_player/plugins/js_bridge/lib/*.js`
  - Vendored compatibility assets from `/home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib`.
- Modify `src/atv_player/plugins/loader.py`
  - Detect plugin format, preserve remote cache suffix, and instantiate `NodeSpider` for JS sources.
- Modify `src/atv_player/ui/plugin_manager_dialog.py`
  - Update Python-only labels and file filters to include JavaScript.
- Modify `build.py`
  - Add the JS bridge directory to PyInstaller data files.
- Modify `tests/test_spider_plugin_loader.py`
  - Add JS loader, missing Node, remote cache, and format detection tests.
- Create `tests/test_node_spider_runtime.py`
  - Test `NodeSpider` process protocol with a fake process and test the real Node bridge with skip-if-no-node fixtures.
- Modify `tests/test_spider_plugin_controller.py`
  - Add a JS-backed controller integration test that uses the same mapping as Python plugins.
- Modify `tests/test_plugin_manager_dialog.py`
  - Assert updated labels and local file filter support `.js`.
- Modify `tests/test_build.py`
  - Assert PyInstaller includes the JS bridge assets.

## Task 1: Add `NodeSpider` Process Adapter

**Files:**
- Create: `src/atv_player/plugins/node_spider.py`
- Test: `tests/test_node_spider_runtime.py`

- [ ] **Step 1: Write failing tests for missing Node and JSON method calls**

Add this file:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_node_spider_runtime.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'atv_player.plugins.node_spider'`.

- [ ] **Step 3: Implement minimal `NodeSpider`**

Create `src/atv_player/plugins/node_spider.py`:

```python
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any


class NodeSpider:
    def __init__(
        self,
        plugin_path: Path,
        cache_dir: Path,
        plugin_id: int,
        *,
        node_executable: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        executable = node_executable or shutil.which("node")
        if not executable:
            raise ValueError("未找到 Node.js 运行环境，无法加载 JavaScript 插件")
        self.plugin_path = Path(plugin_path)
        self.cache_dir = Path(cache_dir)
        self.plugin_id = int(plugin_id)
        self.node_executable = executable
        self.timeout_seconds = timeout_seconds
        self._request_id = 0
        self._process: subprocess.Popen[str] | None = None
        self._stdout_lines: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()

    def init(self, extend: str = "") -> None:
        self._call("init", extend)

    def homeContent(self, filter):
        return self._call("home", filter)

    def categoryContent(self, tid, pg, filter, extend):
        return self._call("category", tid, pg, filter, extend)

    def detailContent(self, ids):
        first_id = ids[0] if ids else ""
        return self._call("detail", first_id)

    def searchContent(self, key, quick, pg=1, category=""):
        return self._call("search", key, quick, pg, category)

    def playerContent(self, flag, id, vipFlags):
        return self._call("play", flag, id, vipFlags)

    def getName(self):
        try:
            return str(self._call("getName") or "")
        except RuntimeError:
            return ""

    def supports_search(self) -> bool:
        return bool(self._call("hasMethod", "search"))

    def destroy(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    def _bridge_path(self) -> Path:
        return Path(__file__).resolve().parent / "js_bridge" / "tvbox_spider_runner.mjs"

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.node_executable,
            str(self._bridge_path()),
            "--plugin",
            str(self.plugin_path),
            "--cache-dir",
            str(self.cache_dir),
            "--plugin-id",
            str(self.plugin_id),
        ]
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._stdout_lines = queue.Queue()
        self._stderr_lines = queue.Queue()
        threading.Thread(target=self._read_stdout, args=(self._process,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self._process,), daemon=True).start()
        return self._process

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            self._stdout_lines.put(line)
        self._stdout_lines.put(None)

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for line in iter(process.stderr.readline, ""):
            self._stderr_lines.put(line.rstrip())

    def _call(self, method: str, *args: Any):
        with self._lock:
            process = self._ensure_process()
            if process.stdin is None:
                raise RuntimeError("Node.js 插件进程不可写入")
            self._request_id += 1
            request_id = self._request_id
            process.stdin.write(json.dumps({"id": request_id, "method": method, "args": list(args)}, ensure_ascii=False) + "\n")
            process.stdin.flush()
            try:
                line = self._stdout_lines.get(timeout=self.timeout_seconds)
            except queue.Empty as exc:
                self.destroy()
                raise TimeoutError(f"JavaScript 插件调用超时: {method}") from exc
            if line is None:
                error = self._latest_stderr() or f"JavaScript 插件进程已退出: {method}"
                raise RuntimeError(error)
            response = json.loads(line)
            if response.get("id") != request_id:
                raise RuntimeError(f"JavaScript 插件响应 id 不匹配: {response.get('id')}")
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error") or "JavaScript 插件调用失败"))
            return response.get("result")

    def _latest_stderr(self) -> str:
        messages: list[str] = []
        while True:
            try:
                messages.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "\n".join(message for message in messages if message).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_node_spider_runtime.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/plugins/node_spider.py tests/test_node_spider_runtime.py
git commit -m "feat: add node spider process adapter"
```

## Task 2: Add Node Bridge Script and Real JS Fixtures

**Files:**
- Create: `src/atv_player/plugins/js_bridge/tvbox_spider_runner.mjs`
- Create: `src/atv_player/plugins/js_bridge/lib/cat.js`
- Create: `src/atv_player/plugins/js_bridge/lib/cheerio.min.js`
- Create: `src/atv_player/plugins/js_bridge/lib/crypto-js.js`
- Create: `src/atv_player/plugins/js_bridge/lib/gbk.js`
- Create: `src/atv_player/plugins/js_bridge/lib/similarity.js`
- Modify: `tests/test_node_spider_runtime.py`

- [ ] **Step 1: Add failing real-Node integration tests**

Append to `tests/test_node_spider_runtime.py`:

```python
import shutil


pytestmark_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@pytestmark_node
def test_node_bridge_loads_default_export_fixture(tmp_path: Path) -> None:
    plugin_path = tmp_path / "default-plugin.mjs"
    plugin_path.write_text(
        """
export default {
  init(ext) { this.ext = ext },
  getName() { return `默认:${this.ext}` },
  home(filter) { return { class: [{ type_id: "hot", type_name: "热门" }], list: [] } },
  category(tid, pg, filter, extend) { return { list: [{ vod_id: `${tid}-${pg}`, vod_name: "分类" }], total: 1 } },
  detail(id) { return { list: [{ vod_id: id, vod_name: "详情", vod_play_from: "默认线", vod_play_url: "第1集$/play/1" }] } },
  search(key, quick, pg) { return { list: [{ vod_id: key, vod_name: key }], total: 1 } },
  play(flag, id, vipFlags) { return { parse: 0, url: `https://media.example${id}.m3u8`, header: { Referer: "https://site.example" } } }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=1)

    spider.init("ext")

    assert spider.getName() == "默认:ext"
    assert spider.homeContent(False)["class"][0]["type_name"] == "热门"
    assert spider.categoryContent("hot", "2", False, {})["list"][0]["vod_id"] == "hot-2"
    assert spider.detailContent(["abc"])["list"][0]["vod_name"] == "详情"
    assert spider.searchContent("关键字", False, "1")["list"][0]["vod_name"] == "关键字"
    assert spider.playerContent("默认线", "/play/1", [])["url"] == "https://media.example/play/1.m3u8"
    spider.destroy()


@pytestmark_node
def test_node_bridge_loads_js_eval_return_fixture_and_local_cache(tmp_path: Path) -> None:
    plugin_path = tmp_path / "eval-plugin.mjs"
    plugin_path.write_text(
        """
export function __jsEvalReturn() {
  return {
    init(ext) { local.set("rule", "ext", ext) },
    getName() { return `缓存:${local.get("rule", "ext")}` },
    home() { return JSON.stringify({ class: [], list: [{ vod_id: "1", vod_name: "首页" }] }) },
    category() { return { list: [], total: 0 } },
    detail(id) { return { list: [{ vod_id: id, vod_name: "详情", vod_play_from: "默认", vod_play_url: "正片$https://media.example/a.m3u8" }] } },
    play(flag, id) { return { parse: 0, url: id } }
  }
}
""".strip(),
        encoding="utf-8",
    )
    spider = NodeSpider(plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=2)

    spider.init("abc")

    assert spider.getName() == "缓存:abc"
    assert spider.homeContent(False)["list"][0]["vod_name"] == "首页"
    spider.destroy()
```

- [ ] **Step 2: Run tests to verify the integration tests fail**

Run: `uv run pytest tests/test_node_spider_runtime.py -q`

Expected when `node` exists: FAIL with a bridge script error such as `Cannot find module ... tvbox_spider_runner.mjs`. Expected when `node` is absent: non-Node tests PASS and real-Node tests SKIP.

- [ ] **Step 3: Copy compatibility assets**

Run these commands from the repository root:

```bash
mkdir -p src/atv_player/plugins/js_bridge/lib
cp /home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib/cat.js src/atv_player/plugins/js_bridge/lib/cat.js
cp /home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib/cheerio.min.js src/atv_player/plugins/js_bridge/lib/cheerio.min.js
cp /home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib/crypto-js.js src/atv_player/plugins/js_bridge/lib/crypto-js.js
cp /home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib/gbk.js src/atv_player/plugins/js_bridge/lib/gbk.js
cp /home/harold/StudioProjects/TV/quickjs/src/main/assets/js/lib/similarity.js src/atv_player/plugins/js_bridge/lib/similarity.js
```

- [ ] **Step 4: Implement the bridge script**

Create `src/atv_player/plugins/js_bridge/tvbox_spider_runner.mjs`:

```javascript
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import path from "node:path";

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 2) {
    result[argv[i].replace(/^--/, "")] = argv[i + 1];
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
const pluginPath = args.plugin;
const cacheDir = args["cache-dir"];
const pluginId = args["plugin-id"];

if (!pluginPath || !cacheDir || !pluginId) {
  throw new Error("missing required bridge arguments");
}

function cachePath(rule, key) {
  const safeRule = String(rule || "default").replace(/[^a-zA-Z0-9_.-]/g, "_");
  const safeKey = String(key || "").replace(/[^a-zA-Z0-9_.-]/g, "_");
  return path.join(cacheDir, "js-local", String(pluginId), safeRule, `${safeKey}.txt`);
}

globalThis.local = {
  get(rule, key) {
    try {
      return require("node:fs").readFileSync(cachePath(rule, key), "utf-8");
    } catch {
      return "";
    }
  },
  set(rule, key, value) {
    const file = cachePath(rule, key);
    require("node:fs").mkdirSync(path.dirname(file), { recursive: true });
    require("node:fs").writeFileSync(file, String(value ?? ""), "utf-8");
  },
  delete(rule, key) {
    try {
      require("node:fs").unlinkSync(cachePath(rule, key));
    } catch {
    }
  },
};

async function http(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    url: response.url,
    headers: Object.fromEntries(response.headers.entries()),
    content: text,
    text,
    json: () => JSON.parse(text),
  };
}

globalThis.http = http;
globalThis.req = http;

const originalConsole = globalThis.console;
globalThis.console = {
  log: (...items) => originalConsole.error(JSON.stringify({ level: "info", message: items.map(String).join(" ") })),
  warn: (...items) => originalConsole.error(JSON.stringify({ level: "warning", message: items.map(String).join(" ") })),
  error: (...items) => originalConsole.error(JSON.stringify({ level: "error", message: items.map(String).join(" ") })),
};

const module = await import(pathToFileURL(pluginPath).href);
let spider = null;
if (typeof module.__jsEvalReturn === "function") {
  spider = await module.__jsEvalReturn();
} else if (typeof module.default === "function") {
  spider = await module.default();
} else if (module.default) {
  spider = module.default;
} else {
  spider = module;
}

if (!spider || typeof spider !== "object") {
  throw new Error("JavaScript plugin did not export a spider object");
}

function normalizeResult(value) {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

async function callMethod(method, args) {
  const map = {
    init: "init",
    home: "home",
    category: "category",
    detail: "detail",
    search: "search",
    play: "play",
    getName: "getName",
    destroy: "destroy",
  };
  if (method === "hasMethod") return typeof spider[args[0]] === "function";
  const jsName = map[method];
  const fn = jsName ? spider[jsName] : null;
  if (typeof fn !== "function") {
    if (method === "init" || method === "destroy") return null;
    throw new Error(`${method} is not defined`);
  }
  return normalizeResult(await fn.apply(spider, args));
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  const request = JSON.parse(line);
  try {
    const result = await callMethod(request.method, request.args || []);
    process.stdout.write(`${JSON.stringify({ id: request.id, ok: true, result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ id: request.id, ok: false, error: String(error?.message || error) })}\n`);
  }
}
```

- [ ] **Step 5: Fix CommonJS `require` usage in ESM bridge**

Edit the imports and local cache helpers in `tvbox_spider_runner.mjs` so the script uses `createRequire`:

```javascript
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
```

Place the import with the other imports and place `const require = ...` before `globalThis.local`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_node_spider_runtime.py -q`

Expected: PASS when `node` exists; otherwise PASS with the two real-Node tests skipped.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/plugins/js_bridge tests/test_node_spider_runtime.py
git commit -m "feat: add tvbox js bridge runner"
```

## Task 3: Teach Loader Runtime Detection and JS Remote Caching

**Files:**
- Modify: `src/atv_player/plugins/loader.py`
- Modify: `tests/test_spider_plugin_loader.py`

- [ ] **Step 1: Add failing loader tests**

Append to `tests/test_spider_plugin_loader.py`:

```python
JS_PLUGIN_SOURCE = """
export default {
  getName() { return "JS短剧" },
  home() { return { class: [], list: [] } },
  category() { return { list: [], total: 0 } },
  detail(id) { return { list: [{ vod_id: id, vod_name: "详情", vod_play_from: "默认", vod_play_url: "正片$https://media.example/a.m3u8" }] } },
  play(flag, id) { return { parse: 0, url: id } }
}
"""


def test_loader_loads_local_js_plugin_with_node_runtime(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "js-plugin.js"
    plugin_path.write_text(JS_PLUGIN_SOURCE, encoding="utf-8")
    seen: dict[str, object] = {}

    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            seen["plugin_path"] = Path(plugin_path)
            seen["cache_dir"] = Path(cache_dir)
            seen["plugin_id"] = plugin_id

        def init(self, extend=""):
            seen["extend"] = extend

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

        def searchContent(self, key, quick, pg=1, category=""):
            return {"list": []}

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=51,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
        config_text="site=https://example.com",
    )

    loaded = loader.load(config)

    assert loaded.plugin_name == "JS短剧"
    assert loaded.search_enabled is True
    assert seen["plugin_path"] == plugin_path
    assert seen["cache_dir"] == tmp_path / "cache" / "spider-cache"
    assert seen["plugin_id"] == 51
    assert seen["extend"] == "site=https://example.com"


def test_loader_caches_remote_js_source_with_js_suffix(monkeypatch, tmp_path: Path) -> None:
    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)

    def fake_get(url: str, timeout: float = 15.0, follow_redirects: bool = False) -> httpx.Response:
        return httpx.Response(200, text=JS_PLUGIN_SOURCE, request=httpx.Request("GET", url))

    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache", get=fake_get)
    config = SpiderPluginConfig(
        id=52,
        source_type="remote",
        source_value="https://example.com/plugin.js",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.plugin_name == "JS短剧"
    assert loaded.config.cached_file_path.endswith("plugin_52.js")
    assert Path(loaded.config.cached_file_path).read_text(encoding="utf-8") == JS_PLUGIN_SOURCE


def test_loader_detects_suffixless_remote_js_source(monkeypatch, tmp_path: Path) -> None:
    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            self.plugin_path = Path(plugin_path)

        def init(self, extend=""):
            return None

        def getName(self):
            return "JS短剧"

        def supports_search(self):
            return True

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(
        cache_dir=tmp_path / "cache",
        get=lambda url, **kwargs: httpx.Response(200, text=JS_PLUGIN_SOURCE, request=httpx.Request("GET", url)),
    )
    config = SpiderPluginConfig(
        id=53,
        source_type="remote",
        source_value="https://example.com/plugin",
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config, force_refresh=True)

    assert loaded.config.cached_file_path.endswith("plugin_53.js")


def test_loader_disables_search_for_js_plugin_without_search_method(monkeypatch, tmp_path: Path) -> None:
    plugin_path = tmp_path / "no-search.js"
    plugin_path.write_text("export default { home() { return { class: [], list: [] } } }", encoding="utf-8")

    class FakeNodeSpider:
        def __init__(self, plugin_path, cache_dir, plugin_id):
            return None

        def init(self, extend=""):
            return None

        def getName(self):
            return "无搜索JS"

        def supports_search(self):
            return False

    monkeypatch.setattr("atv_player.plugins.loader.NodeSpider", FakeNodeSpider)
    loader = SpiderPluginLoader(cache_dir=tmp_path / "cache")
    config = SpiderPluginConfig(
        id=54,
        source_type="local",
        source_value=str(plugin_path),
        display_name="",
        enabled=True,
        sort_order=0,
    )

    loaded = loader.load(config)

    assert loaded.search_enabled is False
```

- [ ] **Step 2: Run loader tests to verify they fail**

Run: `uv run pytest tests/test_spider_plugin_loader.py::test_loader_loads_local_js_plugin_with_node_runtime tests/test_spider_plugin_loader.py::test_loader_caches_remote_js_source_with_js_suffix tests/test_spider_plugin_loader.py::test_loader_detects_suffixless_remote_js_source tests/test_spider_plugin_loader.py::test_loader_disables_search_for_js_plugin_without_search_method -q`

Expected: FAIL because `atv_player.plugins.loader.NodeSpider` does not exist or remote cache still uses `.py`.

- [ ] **Step 3: Modify loader imports and helper methods**

In `src/atv_player/plugins/loader.py`, add:

```python
from atv_player.plugins.node_spider import NodeSpider
```

Add helper methods inside `SpiderPluginLoader`:

```python
    def _detect_source_language(self, source_path: Path) -> str:
        suffix = source_path.suffix.lower()
        if suffix == ".js" or suffix == ".mjs":
            return "js"
        if suffix == ".py":
            return "python"
        text = source_path.read_text(encoding="utf-8", errors="replace")
        if self._detect_package_format(source_path) == "secspider/1":
            return "python"
        if any(marker in text for marker in ("from base.spider import Spider", "class Spider")):
            return "python"
        if any(marker in text for marker in ("export default", "__jsEvalReturn", "function home", "async function home")):
            return "js"
        raise ValueError("插件格式不支持")

    def _source_cache_suffix(self, url: str, source_text: str) -> str:
        path_suffix = Path(urlparse(url).path).suffix.lower()
        if path_suffix in {".py", ".js", ".mjs"}:
            return ".js" if path_suffix == ".mjs" else path_suffix
        first_lines = "\n".join(source_text.splitlines()[:16])
        if first_lines.strip().startswith("//@format:secspider/1"):
            return ".py"
        if any(marker in source_text for marker in ("from base.spider import Spider", "class Spider")):
            return ".py"
        if any(marker in source_text for marker in ("export default", "__jsEvalReturn", "function home", "async function home")):
            return ".js"
        raise ValueError("插件格式不支持")
```

Also add `urlparse` to the existing urllib import:

```python
from urllib.parse import urlparse
```

- [ ] **Step 4: Update `load()` runtime branch**

In `SpiderPluginLoader.load()`, replace the module-loading block after `source_path` resolution with:

```python
        source_language = self._detect_source_language(source_path)
        if source_language == "js":
            spider = NodeSpider(
                plugin_path=source_path,
                cache_dir=self._cache_dir / "spider-cache",
                plugin_id=config.id,
            )
            spider_cls = type(spider)
        else:
            try:
                package_format = self._detect_package_format(source_path)
                if package_format == "secspider/1":
                    module = self._load_secspider_module(module_name, source_path)
                else:
                    module = self._load_plain_module(module_name, source_path)
            except ModuleNotFoundError as exc:
                raise ValueError(f"缺少依赖: {exc.name}") from exc
            except SecSpiderFormatError as exc:
                raise ValueError("插件格式不支持") from exc
            except SecSpiderSignatureError as exc:
                raise ValueError("插件签名校验失败") from exc
            except SecSpiderKeyError as exc:
                raise ValueError("插件密钥不可用") from exc
            except SecSpiderDecryptError as exc:
                raise ValueError("插件解密失败") from exc
            except SecSpiderHashError as exc:
                raise ValueError("插件源码校验失败") from exc
            spider_cls = getattr(module, "Spider", None)
            if spider_cls is None:
                raise ValueError("缺少 Spider 类")
            spider = spider_cls()
```

Keep the existing initialization, plugin name, and `LoadedSpiderPlugin` return path below this block. Update search detection to:

```python
        supports_search = getattr(spider, "supports_search", None)
        search_enabled = (
            bool(supports_search())
            if callable(supports_search)
            else type(spider).searchContent is not CompatSpider.searchContent
        )
```

- [ ] **Step 5: Update remote source cache suffix**

Change `_resolve_source_path()` remote cache handling so it downloads before choosing the suffix when refresh is needed:

```python
        if config.source_type == "local":
            return Path(config.source_value)
        cached = Path(config.cached_file_path) if config.cached_file_path else None
        if not force_refresh and cached is not None and cached.is_file() and cached.stat().st_size > 0:
            logger.info(
                "Use cached spider plugin id=%s path=%s",
                config.id,
                cached,
                extra={"log_category": "plugin", "log_source": "app"},
            )
            return cached
        try:
            logger.info(
                "Download spider plugin id=%s source=%s force_refresh=%s",
                config.id,
                config.source_value,
                force_refresh,
                extra={"log_category": "plugin", "log_source": "app"},
            )
            source_text = self._resolve_remote_source_text(config.source_value).strip("\ufeff")
            cache_path = self._cache_dir / f"plugin_{config.id}{self._source_cache_suffix(config.source_value, source_text)}"
            cache_path.write_text(source_text, encoding="utf-8")
            return cache_path
        except Exception:
            fallback_paths = [path for path in (cached, self._cache_dir / f"plugin_{config.id}.js", self._cache_dir / f"plugin_{config.id}.py") if path is not None]
            for fallback_path in fallback_paths:
                if fallback_path.is_file() and fallback_path.stat().st_size > 0:
                    logger.warning(
                        "Spider plugin refresh failed, fallback to cache id=%s path=%s",
                        config.id,
                        fallback_path,
                        extra={"log_category": "plugin", "log_source": "app"},
                    )
                    return fallback_path
            raise
```

- [ ] **Step 6: Run loader tests**

Run: `uv run pytest tests/test_spider_plugin_loader.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/plugins/loader.py tests/test_spider_plugin_loader.py
git commit -m "feat: load tvbox js spider plugins"
```

## Task 4: Verify Controller Mapping With JS-Backed Spider

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Add controller test using `NodeSpider`**

Append to `tests/test_spider_plugin_controller.py`:

```python
import shutil


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_controller_maps_node_spider_detail_and_player_content(tmp_path: Path) -> None:
    plugin_path = tmp_path / "controller-plugin.mjs"
    plugin_path.write_text(
        """
export default {
  home() { return { class: [{ type_id: "tv", type_name: "剧集" }], list: [] } },
  category(tid, pg) { return { list: [{ vod_id: "/detail/1", vod_name: "剧集1", vod_pic: "poster" }], total: 1 } },
  detail(id) {
    return {
      list: [{
        vod_id: id,
        vod_name: "JS剧集",
        vod_pic: "poster-detail",
        vod_play_from: "备用线$$$极速线",
        vod_play_url: "第1集$/play/1#第2集$https://media.example/2.m3u8$$$第3集$/play/3"
      }]
    }
  },
  play(flag, id) { return { parse: 0, url: `https://stream.example${id}.m3u8`, header: { Referer: "https://site.example" } } }
}
""".strip(),
        encoding="utf-8",
    )
    from atv_player.plugins.node_spider import NodeSpider

    spider = NodeSpider(plugin_path=plugin_path, cache_dir=tmp_path / "cache", plugin_id=77)
    controller = SpiderPluginController(plugin_id=77, plugin_name="JS剧集", spider=spider, search_enabled=False)

    request = controller.build_request("/detail/1")

    assert request.detail.title == "JS剧集"
    assert request.playlist[0].title == "备用线 | 第1集"
    assert request.playlist[0].vod_id == "/play/1"
    assert request.playlist[1].url == "https://media.example/2.m3u8"
    resolved = controller.resolve_play_item(request.playlist[0])
    assert resolved.url == "https://stream.example/play/1.m3u8"
    assert resolved.headers["Referer"] == "https://site.example"
    spider.destroy()
```

- [ ] **Step 2: Run the new controller test**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_maps_node_spider_detail_and_player_content -q`

Expected: PASS when `node` exists; otherwise SKIP.

- [ ] **Step 3: Run focused plugin controller tests**

Run: `uv run pytest tests/test_spider_plugin_controller.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_spider_plugin_controller.py
git commit -m "test: cover js spider controller mapping"
```

## Task 5: Update Plugin Manager UI Text and File Filter

**Files:**
- Modify: `src/atv_player/ui/plugin_manager_dialog.py`
- Modify: `tests/test_plugin_manager_dialog.py`

- [ ] **Step 1: Add failing UI tests**

Append to `tests/test_plugin_manager_dialog.py`:

```python
def test_plugin_manager_copy_mentions_javascript(plugin_manager_dialog) -> None:
    dialog = plugin_manager_dialog

    assert "Python/JavaScript" in dialog.warning_label.text()


def test_plugin_manager_local_picker_accepts_js(monkeypatch, plugin_manager_dialog) -> None:
    seen: dict[str, str] = {}

    def fake_get_open_file_name(parent, title, directory, file_filter):
        seen["title"] = title
        seen["filter"] = file_filter
        return "/tmp/plugin.js", ""

    monkeypatch.setattr(
        "atv_player.ui.plugin_manager_dialog.QFileDialog.getOpenFileName",
        fake_get_open_file_name,
    )

    assert plugin_manager_dialog._pick_local_plugin_path() == "/tmp/plugin.js"
    assert seen["title"] == "选择爬虫插件"
    assert "*.js" in seen["filter"]
    assert "*.py" in seen["filter"]
```

- [ ] **Step 2: Run UI tests to verify they fail**

Run: `uv run pytest tests/test_plugin_manager_dialog.py::test_plugin_manager_copy_mentions_javascript tests/test_plugin_manager_dialog.py::test_plugin_manager_local_picker_accepts_js -q`

Expected: FAIL because current copy and file filter mention Python only.

- [ ] **Step 3: Update plugin manager copy**

In `src/atv_player/ui/plugin_manager_dialog.py`, change:

```python
        self.warning_label = QLabel("支持TvBox Python爬虫。远程插件会执行本地 Python 代码，请只加载受信任来源。")
```

to:

```python
        self.warning_label = QLabel("支持 TvBox Python/JavaScript 爬虫。远程插件会执行本地代码，请只加载受信任来源。")
```

Change `_pick_local_plugin_path()` to:

```python
    def _pick_local_plugin_path(self) -> str:
        path, _ = QFileDialog.getOpenFileName(self, "选择爬虫插件", "", "Plugin Files (*.py *.js *.txt)")
        return path.strip()
```

Change `_prompt_remote_url()` to:

```python
    def _prompt_remote_url(self) -> str:
        value, accepted = QInputDialog.getText(self, "添加远程插件", "插件文件 URL")
        return value.strip() if accepted else ""
```

- [ ] **Step 4: Run plugin manager tests**

Run: `uv run pytest tests/test_plugin_manager_dialog.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/plugin_manager_dialog.py tests/test_plugin_manager_dialog.py
git commit -m "feat: allow js spider plugin selection"
```

## Task 6: Include JS Bridge Assets in PyInstaller Builds

**Files:**
- Modify: `build.py`
- Modify: `tests/test_build.py`

- [ ] **Step 1: Add failing build test**

Add to `tests/test_build.py`:

```python
@pytest.mark.parametrize("target_platform,separator", [("linux", ":"), ("macos", ":"), ("windows", ";")])
def test_build_pyinstaller_command_collects_js_bridge_assets(
    monkeypatch, tmp_path, target_platform: str, separator: str
) -> None:
    runtime_path = tmp_path / "runtime-lib"
    runtime_path.write_bytes(b"lib")
    monkeypatch.setattr(build, "find_libmpv", lambda platform: [(runtime_path, ".")])

    command = build.build_pyinstaller_command(target_platform)

    add_data_values = [
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "--add-data"
    ]
    assert f"{build.JS_BRIDGE_DIR}{separator}atv_player/plugins/js_bridge" in add_data_values
```

- [ ] **Step 2: Run build test to verify it fails**

Run: `uv run pytest tests/test_build.py::test_build_pyinstaller_command_collects_js_bridge_assets -q`

Expected: FAIL with `AttributeError: module 'build' has no attribute 'JS_BRIDGE_DIR'`.

- [ ] **Step 3: Add bridge directory constant**

In `build.py`, add below `ICONS_DIR`:

```python
JS_BRIDGE_DIR = PROJECT_ROOT / "src" / "atv_player" / "plugins" / "js_bridge"
```

- [ ] **Step 4: Add PyInstaller data mapping**

In `build_pyinstaller_command()`, add another `--add-data` entry in the existing `command.extend([...])` block:

```python
            "--add-data",
            data_mapping(JS_BRIDGE_DIR, "atv_player/plugins/js_bridge", target.platform_id),
```

The block should include icons, JS bridge data, and libmpv:

```python
    command.extend(
        [
            "--add-data",
            data_mapping(ICONS_DIR, "atv_player/icons", target.platform_id),
            "--add-data",
            data_mapping(JS_BRIDGE_DIR, "atv_player/plugins/js_bridge", target.platform_id),
            "--add-binary",
            data_mapping(find_libmpv(target.platform_id)[0][0], ".", target.platform_id),
        ]
    )
```

- [ ] **Step 5: Run build tests**

Run: `uv run pytest tests/test_build.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_build.py
git commit -m "build: bundle js spider bridge assets"
```

## Task 7: Focused End-to-End Verification

**Files:**
- No planned production edits.
- Use tests from previous tasks.

- [ ] **Step 1: Run focused plugin test suite**

Run:

```bash
uv run pytest \
  tests/test_node_spider_runtime.py \
  tests/test_spider_plugin_loader.py \
  tests/test_spider_plugin_controller.py \
  tests/test_plugin_manager_dialog.py \
  tests/test_build.py \
  -q
```

Expected: PASS. Tests requiring real `node` may SKIP if the system does not have Node.js.

- [ ] **Step 2: Run lint on changed Python files**

Run:

```bash
uv run ruff check \
  src/atv_player/plugins/node_spider.py \
  src/atv_player/plugins/loader.py \
  src/atv_player/ui/plugin_manager_dialog.py \
  tests/test_node_spider_runtime.py \
  tests/test_spider_plugin_loader.py \
  tests/test_spider_plugin_controller.py \
  tests/test_plugin_manager_dialog.py \
  tests/test_build.py \
  build.py
```

Expected: PASS.

- [ ] **Step 3: Run formatting check**

Run:

```bash
uv run ruff format --check \
  src/atv_player/plugins/node_spider.py \
  src/atv_player/plugins/loader.py \
  src/atv_player/ui/plugin_manager_dialog.py \
  tests/test_node_spider_runtime.py \
  tests/test_spider_plugin_loader.py \
  tests/test_spider_plugin_controller.py \
  tests/test_plugin_manager_dialog.py \
  tests/test_build.py \
  build.py
```

Expected: PASS.

- [ ] **Step 4: Run type check on touched source files**

Run:

```bash
npx --yes pyright \
  src/atv_player/plugins/node_spider.py \
  src/atv_player/plugins/loader.py \
  src/atv_player/ui/plugin_manager_dialog.py \
  build.py
```

Expected: PASS.

- [ ] **Step 5: Commit any verification-only fixes**

If a verification command required a code or test adjustment, commit it:

```bash
git add src/atv_player/plugins src/atv_player/ui/plugin_manager_dialog.py tests build.py
git commit -m "fix: polish js spider runtime verification"
```

If no files changed after verification, do not create an empty commit.
