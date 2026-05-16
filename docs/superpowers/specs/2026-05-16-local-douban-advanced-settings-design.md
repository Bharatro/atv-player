# Local Douban Metadata Fallback And Advanced Settings Design

## Summary

在现有 metadata hydration 方案上补两项能力：

- 豆瓣 metadata `search(title)` 和 `get_detail(id)` 改为“本地豆瓣优先，`alist-tvbox` API fallback”。
- 主窗口顶部在“直播源管理”后新增“高级设置”按钮，对话框中可配置 `豆瓣 Cookie` 和 `TMDB API Key`。
- 高级设置中的媒体增强能力增加全局开关，关闭后播放器详情页不再进行后台 metadata 增强。

本轮目标是先把本地豆瓣抓取接进现有 `DoubanProvider` 链路，并把后续要用到的 metadata 凭据持久化进本地配置。`TMDB API Key` 本轮只提供配置入口，不接入真实 TMDB provider。

## Goals

- `search(title)` 和 `get_detail(id)` 都优先使用本地豆瓣抓取。
- 本地豆瓣触发风控时，自动回退到现有 `alist-tvbox /api/movies` 能力。
- 不把本地豆瓣抓取逻辑直接塞进 `MainWindow` 或 `MetadataHydrator`。
- 为后续接入 TMDB 和更多 provider 预留稳定配置入口。
- 支持用户全局关闭媒体增强，并在关闭时彻底停用 hydration 链路。
- 保持现有 metadata 缓存和播放器异步刷新链路不变。

## Non-Goals

- 本轮不实现真实 `TMDBProvider`。
- 不新增更多 metadata 设置项，例如 provider 顺序、手动刷新策略、调试开关。
- 不改造豆瓣首页分类浏览接口；`/tg-db` 仍只服务现有“豆瓣电影”页面。
- 不在高级设置对话框里加入“测试连接”“立即验证 Cookie”“自动获取 Cookie”。
- 关闭媒体增强时不清空已保存的 `豆瓣 Cookie` / `TMDB API Key`。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/app.py`
- `src/atv_player/api.py`
- `src/atv_player/metadata/providers/douban.py`
- 新增本地豆瓣抓取客户端模块
- `src/atv_player/ui/main_window.py`
- 新增高级设置对话框

主要验证：

- `tests/test_storage.py`
- `tests/test_api_client.py`
- `tests/test_metadata_douban_provider.py`
- `tests/test_main_window_ui.py`
- 新增高级设置对话框测试

## Current Problem

当前 metadata hydration 已经能在播放器详情页异步增强元数据，但豆瓣来源仍完全依赖 `alist-tvbox /api/movies`：

- 无法优先利用本地豆瓣抓取拿到更完整或更及时的数据。
- 用户无法在应用内配置豆瓣 Cookie，因此无法主动降低风控概率。
- 后续要接入 TMDB 时，没有现成的 metadata 级别凭据配置入口。
- 主窗口现有的顶部动作区只有“插件管理”“直播源管理”“退出登录”，缺少 metadata 高级配置入口。

## Approach Options

### Option A: Keep fallback logic inside `DoubanProvider`

做法：

- `DoubanProvider.search()` 和 `get_detail()` 直接内部发本地豆瓣请求。
- 捕获风控后再调用 `ApiClient.search_douban_metadata()` / `get_douban_metadata_detail()`。

优点：

- 改动表面上最少。

缺点：

- provider 同时承担抓取、风控识别、HTTP 配置、fallback 编排，职责会继续膨胀。
- 后续接入更多 fallback 或 TMDB 时，很难继续保持清晰边界。

### Option B: Introduce a dedicated local Douban client and let `DoubanProvider` orchestrate

做法：

- 新增本地豆瓣客户端，负责搜索、详情、Cookie 注入和风控判定。
- `DoubanProvider` 只负责编排：
  - 先调本地豆瓣客户端
  - 遇到风控或本地无命中时，再调 `alist-tvbox` fallback

优点：

- 抓取逻辑和 provider 合并逻辑分层明确。
- 更适合后续继续扩展本地豆瓣详情页解析或引入代理策略。

缺点：

- 比 Option A 多一个模块和一组测试。

### Option C: Add a generic metadata source router now

做法：

- 立即把本地豆瓣、`alist-tvbox`、TMDB 都抽成 source，并引入统一路由器。

优点：

- 框架最完整。

缺点：

- 对当前需求明显过度设计。
- 本轮还没有真实 TMDB provider，会先引入空壳抽象。

## Decision

采用 **Option B**。

原因：

- 这轮需求已经同时涉及本地豆瓣抓取、风控识别、fallback、配置注入和 UI 入口。
- 如果继续把逻辑压进 `DoubanProvider`，会让 provider 从“metadata 适配器”变成“抓取服务总控”，后续只会更难维护。
- 本地豆瓣客户端的边界清晰，便于后续单测，也能让 `DoubanProvider` 继续维持“统一输出 `MetadataRecord`”的职责。

## Design

### 1. AppConfig and persistence

在 `AppConfig` 中新增三个字段：

- `metadata_enhancement_enabled: bool = True`
- `metadata_douban_cookie: str = ""`
- `metadata_tmdb_api_key: str = ""`

`SettingsRepository` 同步：

- 初始化建表时补默认列
- 老库迁移时 `ALTER TABLE` 补列
- `load_config()` / `save_config()` 完整 round-trip

约束：

- `metadata_enhancement_enabled` 默认值为 `True`
- 不做复杂格式校验
- 保存时统一 `strip()`
- 空字符串表示未配置

### 2. Advanced settings dialog

新增 `AdvancedSettingsDialog`，职责单一：编辑并保存 metadata 高级配置。

UI：

- 位置：主窗口顶部按钮区，“直播源管理”后新增“高级设置”
- 独立区域：`媒体增强配置`
- 字段：
  - `启用媒体增强`：复选框，全局开关
  - `豆瓣 Cookie`：多行文本框
  - `TMDB API Key`：单行输入框
- 按钮：
  - `保存`
  - `取消`

行为：

- 打开时读取当前 `AppConfig`
- `启用媒体增强` 未勾选时，`豆瓣 Cookie` 和 `TMDB API Key` 输入框置灰，但保留当前值
- 点击保存时回写配置并调用现有 `save_config`
- 点击取消时不落盘

本轮不做：

- 测试 Cookie 是否有效
- 校验 TMDB Key
- 展示 provider 状态或请求日志

### 3. Local Douban client

新增一个本地豆瓣客户端模块，例如：

- `src/atv_player/metadata/providers/local_douban_client.py`

职责：

- 发起本地豆瓣搜索和详情请求
- 注入 Cookie / Referer / User-Agent
- 识别风控页面
- 输出 provider 易于消费的原始结构

建议接口：

- `search(title: str, year: str = "") -> list[dict[str, object]]`
- `get_detail(douban_id: int | str) -> dict[str, object] | None`

风控判定规则按用户确认的实现：

- 如果 HTML 包含 `有异常请求从你的 IP 发出`
- 或 HTML 包含 `https://sec.douban.com/`

则视为被风控，抛出专用异常，例如 `DoubanBlockedError`。

普通“无结果”不算风控：

- 搜索页没有命中时返回空列表
- 详情页没解析到有效内容时返回 `None`

### 4. DoubanProvider orchestration

`DoubanProvider` 继续是 metadata provider，但内部改为双来源编排。

#### Search flow

1. 如果 `MetadataQuery` 里已有 `vod_dbid`，仍然直接构造确定匹配，不走搜索。
2. 否则先调用本地豆瓣客户端 `search(title, year)`。
3. 若本地豆瓣成功且有结果：
   - 转成 `MetadataMatch` 列表返回
4. 若本地豆瓣返回空：
   - 继续调用 `ApiClient.search_douban_metadata()` 作为 fallback
5. 若本地豆瓣抛出 `DoubanBlockedError`：
   - 直接 fallback 到 `ApiClient.search_douban_metadata()`

说明：

- “无结果”也继续 fallback，因为目标是“本地优先”，不是“本地唯一”。
- `year` 参数继续向本地豆瓣和 fallback 透传；即使 fallback 当前未真正用到，也保留接口一致性。

#### Detail flow

1. 先调用本地豆瓣客户端 `get_detail(douban_id)`。
2. 若成功解析到详情：
   - 直接映射为 `MetadataRecord`
3. 若返回 `None`：
   - 调用 `ApiClient.get_douban_metadata_detail()` fallback
4. 若抛出 `DoubanBlockedError`：
   - 直接调用 fallback

### 5. ApiClient changes

`ApiClient` 保持现有 fallback API 角色，不负责本地豆瓣抓取。

调整点：

- `search_douban_metadata(title, year="")`
  - 保持 `GET /api/movies?q=...`
  - 不改为本地豆瓣
- `get_douban_metadata_detail(id)`
  - 保持 `GET /api/movies/{id}`

这样 `ApiClient` 的职责仍然是“桌面端到 alist-tvbox 后端”的 HTTP 封装。

### 6. App wiring

`AppCoordinator._build_metadata_hydrator_factory()` 负责把配置注入 metadata 组件。

具体做法：

- 从 `repo.load_config()` 读取：
  - `metadata_enhancement_enabled`
  - `metadata_douban_cookie`
  - `metadata_tmdb_api_key`
- 若 `metadata_enhancement_enabled == False`，直接返回 `None`
- 创建本地豆瓣客户端实例时注入 `metadata_douban_cookie`
- 创建 `DoubanProvider` 时传入：
  - 本地豆瓣客户端
  - 现有 `ApiClient`
  - 文件系统 cache

`metadata_tmdb_api_key` 本轮只保留在配置和注入通路中，不强制要求下游消费。

### 7. Main window integration

`MainWindow` 顶部按钮区顺序调整为：

- `插件管理`
- `直播源管理`
- `高级设置`
- `退出登录`

点击“高级设置”：

- 关闭可能冲突的弹层
- 弹出 `AdvancedSettingsDialog`
- 保存后无需重启应用
- 新配置在后续新建 metadata hydration 时生效

为了避免“对话框里保存了新 Cookie，但当前 metadata factory 仍拿着旧值”，`AppCoordinator` 需要保证：

- 关闭媒体增强后，后续播放器详情不再触发后台增强
- 保存高级设置后，主窗口内用于 metadata 的配置读取能看到最新值
- 推荐做法：metadata factory 内部在每次创建 provider 时重新读取当前 `AppConfig`，而不是在应用启动时把 Cookie 固定进闭包常量

## Error Handling

- 本地豆瓣风控：
  - 不向用户弹错误
  - provider 自动 fallback
- 本地豆瓣普通解析失败：
  - 视为无结果或无详情，继续 fallback
- fallback 也失败：
  - 保持现有 metadata hydration 失败行为，不阻塞播放器
- 高级设置保存失败：
  - 复用现有配置保存异常处理方式，显示错误提示

## Testing

### Unit tests

- `tests/test_storage.py`
  - 新配置字段 round-trip
  - 老库缺列迁移
- `tests/test_metadata_douban_provider.py`
  - 本地豆瓣成功时不走 fallback
  - 本地豆瓣风控时走 fallback
  - 本地豆瓣空结果时走 fallback
  - 详情接口风控时走 fallback

### UI tests

- `tests/test_main_window_ui.py`
  - 顶部出现“高级设置”按钮，位置在“直播源管理”后
  - 点击后弹对话框
  - “媒体增强配置”开关控制输入框可用状态
  - 保存后配置对象被更新

### Regression tests

- 保持现有 metadata hydration、播放器异步详情刷新、插件详情打开测试继续通过

## Risks

- 本地豆瓣页面结构可能变化，解析器需要尽量把选择器写得保守。
- Cookie 失效后会频繁 fallback，但这比直接报错更符合当前目标。
- 如果 metadata factory 把配置值过早捕获，保存后的新 Cookie 不会立刻生效，因此实现时必须避免“启动时一次性冻结配置”。

## Rollout

分两步落地：

1. 配置与 UI
   - `AppConfig`
   - `SettingsRepository`
   - `AdvancedSettingsDialog`
   - 主窗口按钮入口
2. 本地豆瓣抓取与 provider fallback
   - 本地豆瓣客户端
   - `DoubanProvider` 编排
   - 相关测试和回归验证
