# TvBox JS Spider Node Runtime Design

## Summary

Add first-class support for TvBox JavaScript spider plugins when a system `node`
runtime is available. JavaScript plugins should share the existing spider plugin
manager, dynamic home tabs, poster-grid browsing, search, detail, and playback
flow already used by Python spider plugins.

The first release uses the system-installed Node.js executable only. It does not
download, bundle, or install Node.js. If Node.js is missing, JavaScript plugins
fail to load with a clear error while Python plugins and the rest of the app keep
working.

## Goals

- Load local and remote TvBox JavaScript spider plugins through the existing
  plugin manager.
- Reuse the existing plugin configuration table, ordering, enable state,
  refresh, config text, logs, and dynamic plugin tabs.
- Support the core TvBox JS spider flow:
  - browse home content
  - browse category content
  - search content
  - load detail content
  - resolve playback content
- Support common TvBox JS module styles:
  - `default export`
  - `__jsEvalReturn`
- Provide enough JavaScript bridge helpers for common plugins:
  - `req` / `http`
  - `local.get`, `local.set`, `local.delete`
  - `console.log` and `console.error`
  - local `lib/*` asset mapping for common quickjs-compatible libraries
- Keep JS runtime errors isolated to the failing plugin.

## Non-Goals

- Bundling, downloading, or managing a Node.js runtime.
- Installing npm dependencies for plugins.
- Supporting TvBox JS `proxy`, `live`, `action`, `sniffer`, or `isVideo` in the
  first release.
- Sandboxing untrusted JavaScript beyond process isolation.
- Replacing or rewriting the existing Python spider plugin runtime.
- Changing the database schema solely to distinguish Python and JavaScript
  plugins.

## Architecture

Use the existing `SpiderPluginLoader` as the single plugin loading entry point.
After resolving a local or remote source to a file path, the loader determines
the runtime by file suffix or source-content detection:

- `.js` uses the new Node-backed JavaScript runtime.
- `.py` and `secspider/1` packages continue through the existing Python loader.
- suffixless remote sources are detected from source content before caching.

The JavaScript runtime is exposed to the rest of the app as a Python object with
the same method surface as the existing TvBox Python `Spider` compatibility
class:

- `init(extend="")`
- `homeContent(filter)`
- `categoryContent(tid, pg, filter, extend)`
- `detailContent(ids)`
- `searchContent(key, quick, pg=1, category="")`
- `playerContent(flag, id, vipFlags)`
- `getName()`
- `destroy()`

This keeps `LoadedSpiderPlugin`, `SpiderPluginController`, dynamic tab assembly,
and playback mapping largely unchanged. The controller should not need to know
whether the loaded spider came from Python or JavaScript.

## Runtime Selection

Do not add a `runtime` column in the first release. The existing
`source_type` continues to mean only `local` or `remote`. The concrete runtime is
derived from the resolved source file:

- A local `*.js` file is loaded as JavaScript.
- A remote URL ending in `.js` is cached as `plugin_<id>.js` and loaded as
  JavaScript.
- A remote URL ending in `.py` is cached as `plugin_<id>.py` and loaded as
  Python.
- A remote indirect URL is followed once using the existing indirect URL rule,
  and the final fetched source determines the cached suffix.
- A suffixless remote source uses content heuristics:
  - Python markers include `from base.spider import Spider`, `class Spider`, or
    `//@format:secspider/1`.
  - JavaScript markers include `export default`, `__jsEvalReturn`,
    `function home`, `async function home`, or exported `home/category/detail`
    functions.

If detection is ambiguous, loading fails with an explicit unsupported plugin
format message.

## Node Bridge

Add a small bridge under `src/atv_player/plugins/js_bridge/`, for example
`tvbox_spider_runner.mjs`. The Python `NodeSpider` starts this script as a
long-lived child process:

```text
node tvbox_spider_runner.mjs --plugin /path/to/plugin.js --cache-dir /path/to/cache --plugin-id 7
```

Python and Node communicate over newline-delimited JSON on stdin/stdout. Each
request includes an integer `id`, a `method`, and an `args` array:

```json
{"id": 1, "method": "home", "args": [false]}
{"id": 2, "method": "play", "args": ["线路", "/play/1", []]}
```

Each response returns the same `id`, an `ok` flag, and either `result` or
`error`:

```json
{"id": 1, "ok": true, "result": "{\"class\":[],\"list\":[]}"}
{"id": 2, "ok": false, "error": "play is not defined"}
```

Bridge method mapping:

- Python `init(extend)` calls JS `init(extend)`, when present.
- Python `homeContent(filter)` calls JS `home(filter)`.
- Python `categoryContent(tid, pg, filter, extend)` calls
  JS `category(tid, pg, filter, extend)`.
- Python `detailContent(ids)` calls JS `detail(ids[0])`.
- Python `searchContent(key, quick, pg, category)` calls
  JS `search(key, quick, pg, category)` when accepted, with fallback to
  `search(key, quick, pg)` for older plugins.
- Python `playerContent(flag, id, vipFlags)` calls JS `play(flag, id, vipFlags)`.
- Python `getName()` uses JS `getName()` when present, then falls back to the
  configured display name or source filename handled by the existing loader
  path.

The bridge accepts both string JSON payloads and plain JavaScript objects. If a
plugin returns an object, the bridge serializes it with `JSON.stringify` so the
existing controller receives the same shape as Python plugins.

## JavaScript Compatibility Helpers

The Node bridge should install a minimal global environment before importing the
plugin:

- `http(url, options)` returns a Promise resolving to a response object.
- `req(url, options)` is available for compatibility; in Node it returns the
  same response shape through an awaited Promise path rather than trying to
  block the event loop.
- `local.get(rule, key)`, `local.set(rule, key, value)`, and
  `local.delete(rule, key)` persist values under the app plugin cache directory,
  namespaced by plugin id and optional rule.
- `console.log`, `console.warn`, and `console.error` forward structured log
  events to Python stderr handling so they can be recorded in plugin logs.
- `lib/*` imports resolve to bundled compatibility assets copied from or adapted
  from the referenced quickjs implementation, including common libraries such as
  `cat.js`, `cheerio.min.js`, `crypto-js.js`, `gbk.js`, and `similarity.js`.

Because Node supports async execution naturally, plugin functions may be sync or
async. The bridge always awaits the function result.

## Source Fetching and Caching

Remote plugin fetching continues to use the existing Python download path so
network proxy handling, indirect URL support, refresh behavior, and fallback to
non-empty cached files remain consistent.

Caching changes:

- Cache files keep the detected suffix: `plugin_<id>.py` or `plugin_<id>.js`.
- Existing Python caches remain valid.
- Empty cache files are ignored.
- If a JS remote refresh fails and a previous non-empty JS cache exists, the
  loader falls back to that cache and records the refresh failure in plugin logs
  using the existing path.

## Plugin Manager UI

Reuse the existing plugin manager. Update labels and filters so it no longer
sounds Python-only:

- Warning text: "支持 TvBox Python/JavaScript 爬虫。远程插件会执行本地代码，请只加载受信任来源。"
- Local file chooser title: "选择爬虫插件"
- Local file filter: `Plugin Files (*.py *.js *.txt)`
- Remote prompt label: "插件文件 URL"
- Source type display remains "本地" or "远程"; runtime is not a separate column
  in the first release.

No new management dialog is needed.

## Error Handling

When loading a JavaScript plugin:

- Check `shutil.which("node")`.
- If missing, raise a user-facing error such as `未找到 Node.js 运行环境，无法加载 JavaScript 插件`.
- If the Node process exits during initialization or method execution, report the
  captured stderr message when available.
- If a method times out, terminate the child process, mark the plugin call as
  failed, and restart lazily on the next call.
- If `search` is missing, mark `search_enabled=False` just like Python plugins
  whose `searchContent` is not implemented.

Recommended default method timeout: 20 seconds. This is long enough for normal
network-backed plugin calls while preventing a hung JavaScript process from
blocking the UI indefinitely.

## Security Model

JavaScript plugins are trusted local code. They execute in a separate Node
process, which improves lifecycle control and crash isolation, but they are not
sandboxed. The plugin manager warning must clearly state that remote plugins
execute local code.

This matches the existing trusted-code model for Python spider plugins and keeps
the first release focused on compatibility rather than sandbox design.

## Testing

Use test-first implementation. Primary tests:

- `SpiderPluginLoader` loads a local `.js` plugin through the Node runtime.
- JS plugin loading fails clearly when `node` is unavailable.
- Remote `.js` sources are cached with a `.js` suffix.
- Remote JS refresh failure falls back to a previous non-empty `.js` cache.
- Suffixless remote JS source detection chooses the JS runtime.
- A minimal `default export` fixture supports `home`, `category`, `detail`,
  `search`, and `play`.
- A minimal `__jsEvalReturn` fixture supports the same core methods.
- JS object return values are serialized and mapped by the existing
  `SpiderPluginController`.
- Missing JS `search` disables search for that plugin.
- Plugin manager labels and file filter accept `.js` without removing `.py`.

Tests that invoke Node should skip when `node` is not available, except for the
explicit missing-Node test where `shutil.which` is monkeypatched to return
`None`.

## Implementation Boundaries

Expected production files:

- `src/atv_player/plugins/loader.py`
- `src/atv_player/plugins/node_spider.py`
- `src/atv_player/plugins/js_bridge/tvbox_spider_runner.mjs`
- `src/atv_player/plugins/js_bridge/lib/*`
- `src/atv_player/ui/plugin_manager_dialog.py`
- packaging configuration if needed to include bridge assets in wheels and
  PyInstaller builds

Expected tests:

- `tests/test_spider_plugin_loader.py`
- `tests/test_spider_plugin_controller.py`
- `tests/test_plugin_manager_dialog.py`
- focused new bridge tests if keeping them clearer in a separate test module

