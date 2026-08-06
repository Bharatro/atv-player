# 弹弹Play 源改造为可配置自建网关

- 日期: 2026-07-30
- 状态: 设计已确认
- 分支: feat/danmaku

## 背景与动机

`dandan` 弹幕源把 base URL 硬编码为第三方代理 `https://api.danmaku.weeblify.app/ddp/v1`（`src/atv_player/danmaku/providers/dandan.py:14`），并用非标准的 `?path=<内层API路径>` 方式转发。该网关不在用户掌控之内，从用户实际运行环境（HTPC / TV 盒子 / CN 网络等）经常不可达；而 `search()` 对所有异常 `return []`（`dandan.py:46-47`），无日志、无提示，导致"弹弹Play 源从来搜不到结果"且无法诊断。

目标：把该源改为指向用户自建的 dandanplay 兼容服务器（参考实现：`/home/harold/workspace/danmu_api`，dandanplay 协议兼容，默认端口 9321，token 为 URL 首段，`/api/config` 免 token），并修掉静默吞错。

已做验证：在本机用真实 `httpx.get` 端到端跑通现有 provider 与完整 `DanmakuService`，返回 18 条结果——证明代码逻辑、解析、编排均正常，问题仅在硬编码网关的可达性 + 静默吞错。

## 设计

### 1. 配置（镜像 TMDB 写法）

- `AppConfig`（`src/atv_player/models.py`）新增 `dandan_base_url: str = ""`。token 直接拼进地址，如 `http://192.168.1.10:9321` 或 `http://host:9321/87654321`。
- `src/atv_player/storage.py`：config 表加列 `dandan_base_url TEXT NOT NULL DEFAULT ''`；迁移 `if "dandan_base_url" not in columns: ALTER TABLE config ADD COLUMN ...`（接在现有 line 569 起的迁移块之后）；行↔对象读写映射补该字段。
- `create_default_danmaku_service` 已收 `config_loader`；据此构造 `base_url_loader = lambda: (config_loader().dandan_base_url if config_loader else "")` 注入 provider。运行时改地址立即生效（与 `disabled_provider_ids_loader` 同为 live 闭包模式）。`app.py` 无需改动（`config_loader` 已传入）。

### 2. provider 改造（`src/atv_player/danmaku/providers/dandan.py`）

- 构造：`__init__(self, get=httpx.get, base_url_loader=None)`，`self._base_url_loader = base_url_loader or (lambda: "")`。删除模块常量 `_BASE_URL`。
- 重写 `_request_json(path)`：`base = self._base_url_loader().strip().rstrip("/")`；标准拼 URL `{base}/api/v2/...`（`search/anime`、`bangumi/{id}`、`comment/{id}`），query 用 `urllib.parse` 正确编码；丢掉 `params={"path": ...}` 转发花活。
- 三态行为：
  - 未配置（`base` 空）→ 源关闭：`search()` 立即 `return []`、`supports()` `return False`、`resolve()` `raise DanmakuResolveError("未配置弹弹Play服务器地址")`。不发请求、不报错、不刷日志。
  - 配置 + 正常 → 原 search→bangumi→comment 三步流，返回 `DanmakuRecord`（模型不变）。
  - 配置 + 失败 → `search()` `raise DanmakuSearchError(f"弹弹Play服务器连接失败: {reason}")`；`resolve()` `raise DanmakuResolveError(...)`。
- 不变：`DanmakuRecord`/`DanmakuSearchItem` 模型、`dandan://episode/{id}` 合成 URL、`_record`/`_episode_item`/`_expand_anime`/`_prefer_requested_episode` 解析逻辑、注册 / fixed_order / 标签、缓存、UI 选择器、proxy 逐址决策。

### 3. 错误显示位置（已确认）

- `resolve()` 抛错 → 经 `src/atv_player/ui/player_window.py:9202-9203`（`error_prefix="弹幕切换失败"`）显示为"弹幕切换失败: …"进**弹幕日志面板**（同"弹幕搜索中 / 弹幕下载成功"面板）。用户手动选弹弹Play源失败时可见。**零新增 UI。**
- `search()` 抛错 → 服务层 `_collect_search_results`（`service.py:662-668`）已 `logger.warning` 并跳过，dev 日志可见，不影响其它源。后台并发时静默可接受，用户选源时由 resolve 路径兜底提示。

### 4. 测试连接按钮（镜像 TMDB"测速"，`src/atv_player/ui/advanced_settings_dialog.py`）

弹幕源组（`danmaku_source_group`，line 145）下新增：

- `dandan_base_url_edit = QLineEdit()`，placeholder："`http://host:9321 或 http://host:9321/87654321；留空=关闭此源`"。
- `dandan_test_button = QPushButton("测试连接")` + 一个状态 label。
- 探测逻辑：新增模块级函数 `probe_dandan_server(get, base_url) -> tuple[bool, str]`（放 `dandan.py`，便于单测）。打 `{base}/api/v2/search/anime?keyword=test`，短超时（5s），判 HTTP 200 + JSON 含 `animes` 数组 → ✅"连接正常"；否则 ❌"连接失败: <HTTP 码 / 超时 / 原因>"。**用真实 search 端点而非 `/api/config`**，可同时校验 token 正确性。
- 异步执行：沿用 `tmdb_speed_test_button` 的 `_running` flag + 后台线程模式（`advanced_settings_dialog.py:164-165`），避免阻塞 UI。探测用普通 `httpx.get`（自建网关通常在 localhost / 内网，无需 proxy；运行时 search/resolve 仍走 proxy-aware get）。
- 保存：在弹幕源保存处（line ~1291 附近）读 `dandan_base_url_edit.text().strip()` → `config.dandan_base_url`。

### 5. 文件清单

- `src/atv_player/models.py` — 加 `dandan_base_url` 字段。
- `src/atv_player/storage.py` — 加列 + 迁移 + 读写映射。
- `src/atv_player/danmaku/providers/dandan.py` — 重写构造与 `_request_json`、三态、新增 `probe_dandan_server`。
- `src/atv_player/danmaku/service.py` — `create_default_danmaku_service` 注入 `base_url_loader`。
- `src/atv_player/ui/advanced_settings_dialog.py` — URL 输入 + 测试连接按钮 + 异步探测 + 保存。
- `src/atv_player/app.py` — 无需改。

### 6. 测试

- 更新 `tests/test_danmaku_dandan_provider.py`：fake `get` 现收完整 URL（`{base}/api/v2/...`）而非 `params={"path":...}`。
- 新增用例：未配置 → `search()` 返回 `[]`、`supports()` False；配置 → URL 拼对、解析正常；失败（fake 抛 `httpx.HTTPError`）→ `search()` 抛 `DanmakuSearchError`、`resolve()` 抛 `DanmakuResolveError`。
- 新增 `probe_dandan_server` 单测：200 + `animes` → `(True, ...)`；401 / 超时 / 非 JSON → `(False, 原因)`。

### 7. 不在 v1 范围

- danmu_api `/api/v2/match`（文件名直定集）自动匹配增强。
- `?format=xml` XML 旁路。
- 多个自建网关并存（一址一源，符合"改造现有 dandan"决策）。

## 风险与取舍

- 去掉 weeblify `?path=` 协议后，旧 weeblify 代理不再可用——刻意为之（即病根）。默认空 = 关闭，对未部署 danmu_api 的用户表现为"源关闭"，符合预期。
- token 折进 base_url：最省事，但用户需自己拼对；"测试连接"按钮 + placeholder 缓解。
