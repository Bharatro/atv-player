# Metadata Episode Title Enhancement Design

## Goal

让爱奇艺、腾讯 metadata provider 的剧集列表同时参与剧集标题改写，并覆盖两条链路：

- `plugin` 播放时的自动剧集标题增强
- 手动 metadata 刮削“应用结果”后的当前播放列表标题改写

自动增强优先级固定为：

- 腾讯
- 爱奇艺
- TMDB

手动刮削应用时优先级固定为：

- 当前用户选中的 provider
- 腾讯
- 爱奇艺
- TMDB

评分、海报等 metadata 字段规则不在本轮调整范围内。

## Current State

### 1. Automatic episode title enhancement

`AppCoordinator._build_episode_title_enhancer_factory()` 当前只在 `plugin` 播放链路启用剧集标题增强，并且只使用 TMDB：

- 通过 TMDB 搜索剧集
- 拉取 season detail
- 构建 `titles_by_index`
- 使用 `apply_episode_title_index_map()` 写回 playlist

### 2. Manual metadata scrape apply

`PlayerWindow._apply_selected_metadata_scrape_result()` 当前只会：

- 用 `metadata_scrape_service.apply()` 更新 `VodItem`
- 保存手动绑定
- 刷新海报、元数据、扩展字段

它不会同步改写当前 session 的 `playlist` 标题。

### 3. Provider capabilities

- 爱奇艺 metadata provider 已能从搜索结果拿到 `albumInfo`，其中存在 `videos` 结构，但当前只用于 metadata 匹配和 detail 字段，不输出剧集标题映射能力。
- 腾讯 metadata provider 已能从 `playSites/episodeSites[].episodeInfoList` 取到剧集 URL，但当前同样只用于 metadata 匹配和 detail 字段。

## Options

### Option A: Add a shared episode-title resolver layer on top of metadata providers

新增一个统一的“剧集标题解析器”层，负责：

- 从腾讯、爱奇艺、TMDB 生成统一的按索引标题映射
- 统一处理 provider 优先级与回退
- 同时服务于自动增强与手动刮削应用

优点：

- 自动与手动链路使用同一套决策逻辑
- Provider 顺序和回退规则集中管理
- 后续若接入更多 provider，不需要在两个入口分别复制逻辑

缺点：

- 需要新增一层抽象与相关测试

### Option B: Duplicate logic in automatic and manual paths

分别在：

- `app.py` 自动增强链路
- `player_window.py` 手动刮削应用链路

各写一套腾讯/爱奇艺/TMDB 标题解析和回退逻辑。

优点：

- 初始改动看起来更直接

缺点：

- 两条链路会快速漂移
- 后续维护成本高

### Option C: Keep TMDB automatic enhancement and only patch manual apply

只在手动应用刮削结果时尝试使用当前 provider 改标题，自动增强仍然维持 TMDB。

优点：

- 改动最小

缺点：

- 不满足“爱奇艺和腾讯都有剧集列表”的自动增强诉求
- 用户会看到自动与手动行为不一致

## Recommendation

选择 Option A。

原因：

- 这次需求明确要求两条链路都支持
- Provider 优先级是核心规则，应该只定义一次
- 现有 `apply_episode_title_index_map()` 和 PlayerWindow 的成功刷新路径已经足够复用，新增共享解析层的收益明显高于成本

## Design

### 1. New shared episode-title resolver

新增一个共享模块，负责从 metadata provider 命中结果中解析剧集标题。

职责：

- 定义统一的 provider 顺序
- 根据 `VodItem`、`MetadataMatch` 或手动 `MetadataScrapeCandidate` 解析剧集标题
- 输出 `titles_by_index` 或直接输出改写后的 playlist
- 对 provider 失败、剧集列表缺失、集数不足等情况做回退

建议接口：

- 输入：
  - `playlist`
  - `vod`
  - provider 候选序列
  - 可选的“首选 provider 命中对象”
- 输出：
  - `list[PlayItem] | None`

实现上应复用：

- `seed_original_titles()`
- `apply_episode_title_index_map()`
- `infer_playlist_episode_number()`
- 现有 playlist reorder 规则

### 2. Provider-specific title extraction

#### 腾讯

腾讯 provider 直接从搜索结果 raw payload 提取：

- `playSites[].episodeInfoList`
- `episodeSites[].episodeInfoList`

标题文本优先使用每集自己的 `title`。

映射规则：

- 使用当前 playlist 的 `infer_playlist_episode_number()` 结果定位 episode number
- 从腾讯剧集列表中按顺序或按标题里的集号映射到 `titles_by_index`
- 输出统一格式：
  - 单季：`第{episode_number}集 {episode_title}`
  - 多季：`第{season_number}季 第{episode_number}集 {episode_title}`

腾讯 provider 不新增评分逻辑，仍然只负责 metadata + episode title 数据。

#### 爱奇艺

爱奇艺 provider 扩展为保留剧集列表原始数据：

- 优先使用搜索结果内已有 `videos`
- 若当前结果没有足够的 `videos`，可复用现有 iQiyi 数据结构做有限扩展

同样输出统一格式：

- 单季：`第{episode_number}集 {episode_title}`
- 多季：`第{season_number}季 第{episode_number}集 {episode_title}`

#### TMDB

TMDB 维持现有 season detail 方案，但不再单独作为唯一实现，而是作为共享解析器中的一个 provider backend。

### 3. Automatic enhancement flow

`AppCoordinator._build_episode_title_enhancer_factory()` 改为：

1. 保留现有启用条件：
   - `source_kind == "plugin"`
   - metadata enhancement enabled
   - episode title enhancement enabled
2. 先尝试通过 metadata provider 候选获取剧集标题：
   - 腾讯
   - 爱奇艺
   - TMDB
3. 首个成功生成有效标题变体的 provider 即停止
4. 复用现有 playlist 重新排序与 UI 刷新逻辑

自动增强不依赖手动绑定；它始终按照固定优先级运行。

### 4. Manual scrape apply flow

`PlayerWindow._apply_selected_metadata_scrape_result()` / `_handle_metadata_scrape_apply_succeeded()` 增强为：

1. 先按现有逻辑应用 metadata 到 `VodItem`
2. 再尝试改写当前 session playlist 标题
3. provider 顺序为：
   - 当前用户选中的 provider
   - 腾讯
   - 爱奇艺
   - TMDB
4. 如果选中 provider 本身能提供有效剧集标题，则优先使用
5. 如果失败或无有效标题，再按剩余顺序回退
6. 若成功改写：
   - 更新 `session.playlist`
   - 更新 `session.playlists`
   - 更新当前 source group 的 playlist
   - 默认切到 `episode` 标题视图
   - 复用现有 playlist 渲染逻辑

手动应用失败不应影响 metadata 应用本身；标题改写只是附加增强。

### 5. Matching source objects

为了让共享解析器稳定工作，需要能拿到 provider 命中对象：

- 自动增强场景：解析器需要重新执行 provider search，获取最佳 `MetadataMatch`
- 手动应用场景：优先使用当前 `MetadataScrapeCandidate`

因此共享解析器应支持两种输入：

- `MetadataMatch`
- `MetadataScrapeCandidate`

两者都需要访问 `raw`，避免为标题改写再发无谓的 detail 请求。

### 6. Error handling

规则：

- 单个 provider 标题解析失败不应让整条链路失败
- 当前 provider 失败时记录日志并回退下一个 provider
- 全部 provider 都失败时：
  - 自动增强返回 `None`
  - 手动刮削应用只保留 metadata 更新，不报致命错误

日志原则：

- 自动增强失败沿用现有“剧集标题增强失败”日志样式
- 手动应用标题增强失败只写简短日志，不影响“已绑定手动刮削结果”

### 7. Testing

需要补充的测试分为四组：

#### Provider extraction tests

- 腾讯 provider 能从 `episodeInfoList` 生成可用的剧集标题映射
- 爱奇艺 provider 能从 `videos` 生成可用的剧集标题映射
- 无剧集列表时返回空映射

#### Automatic enhancement tests

- 自动增强按 `腾讯 > 爱奇艺 > TMDB` 优先命中
- 腾讯失败时回退到爱奇艺
- 腾讯和爱奇艺都失败时回退到 TMDB
- 成功后保持当前 item 选中与 playlist 重排规则

#### Manual apply tests

- 选中腾讯 candidate 时优先使用腾讯标题
- 选中爱奇艺 candidate 时优先使用爱奇艺标题
- 当前 provider 无有效标题时按 `腾讯 > 爱奇艺 > TMDB` 回退
- metadata 已更新但标题增强失败时不影响绑定和元数据刷新

#### Regression tests

- 现有 TMDB-only 剧集标题增强测试继续通过
- metadata scrape apply 现有 UI 与绑定测试继续通过

## Out of Scope

- 新增用户可配置的剧集标题来源排序
- 非 `plugin` 自动增强链路的扩展
- 基于网络详情页再抓取更完整剧集列表的重型补抓
- 修改 metadata 字段优先级、评分策略或海报策略

## Implementation Notes

- 尽量不要把标题增强逻辑继续堆在 `app.py` 或 `player_window.py`
- 优先抽出共享 helper/module，再让两条入口调用
- 共享解析器只应关心“如何得到标题映射”，UI 刷新仍留在 `PlayerWindow`
- 自动增强与手动应用都应复用统一的 provider 优先级常量，避免硬编码分散
