# Metadata Hydration Design

## Summary

播放器在打开插件详情页或内置远程详情页后，需要自动在后台补全并刷新媒体元数据，而不是把元数据获取耦合进播放地址解析。第一阶段只覆盖 `plugin` 和内置远程详情来源，采用“独立后台 hydration + 文件系统缓存 + 本地豆瓣优先 + 插件自定义 metadata 优先”的方案，最终仍然把结果统一写回现有 `VodItem` 和 `detail_fields`。

## Goals

- 为播放器详情页建立独立的元数据增强链路，不阻塞播放器打开。
- 统一插件来源和内置远程来源的元数据补全行为。
- 让 metadata provider 可以按优先级扩展，而不需要改播放器 UI 协议。
- 保持 `VodItem` 作为播放器详情唯一渲染模型。
- 与现有文件系统缓存风格保持一致。

## Non-Goals

- 第一阶段不覆盖本地媒体扫描和海报墙预抓。
- 第一阶段不接入 `direct parse`、`yt-dlp` 入口。
- 第一阶段不实现真实的 `TMDB`、`爱奇艺`、`腾讯视频`、`B站` metadata provider。
- 不新增第二套播放器详情对象，也不重构现有 `PlayerSession` 状态机。
- 不引入 sqlite 元数据缓存。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/ui/main_window.py`
- `src/atv_player/ui/player_window.py`
- `src/atv_player/plugins/controller.py`
- 新增 `src/atv_player/metadata/` 子模块

主要验证：

- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`
- `tests/test_spider_plugin_controller.py`
- 新增 `tests/test_metadata_*.py`

## Current Problem

当前仓库里已经有海报墙、播放器详情页、插件详情字段和若干异步详情回写能力，但还没有真正独立的媒体元数据系统：

- `VodItem` 已经承载封面、简介、年份、演员、评分、豆瓣 ID 等字段，但来源不统一。
- 插件可以通过 `ext/detail_fields` 把结构化字段显示到播放器详情区，但没有统一 metadata provider 协议。
- 播放器已经支持“先打开，再异步刷新标题、海报、元数据”的会话更新模式，但这个模式目前主要服务于播放地址和 `yt-dlp` 详情回写。
- 现有 `vod_content`、`vod_remarks`、`detail_fields` 的语义没有被 metadata 系统统一约束。

结果是：

- 详情页打开后没有稳定的二次元数据增强。
- 插件和内置远程源无法共享元数据补全链路。
- 后续想接 `TMDB`、`爱奇艺`、`腾讯视频`、`B站` 时，没有一个可扩展的 provider 框架。

## Approach Options

### Option A: Resolve metadata before opening the player

在 `controller.build_request()` 阶段先跑 metadata provider，拿到增强后的 `VodItem` 再打开播放器。

优点：

- 请求模型简单。
- 不需要给播放器增加新异步链路。

缺点：

- 会拖慢打开播放器。
- 不符合“先打开详情，再后台补全”的目标。
- 插件和远程详情页的占位打开体验会退化。

### Option B: Reuse `playback_loader` for metadata hydration

把 metadata 补全塞进现有 `playback_loader`，在加载播放地址时顺手增强详情。

优点：

- 改动表面上较少。

缺点：

- 播放地址解析和元数据增强职责混在一起。
- 切换清晰度、切换分集等播放加载动作可能重复触发 metadata。
- 很多场景只需要更新详情，不该依赖播放地址加载。

### Option C: Add a dedicated metadata hydration pipeline

播放器打开 session 后，单独起一条后台 metadata hydration 任务，完成后只刷新详情区和海报。

优点：

- 符合现有播放器“打开后异步刷新详情”的模式。
- 不阻塞打开，不影响播放地址加载。
- provider 边界清晰，后续扩展时调用方不需要改动。

缺点：

- 需要给 `OpenPlayerRequest`、`PlayerSession`、`PlayerWindow` 新增小型接缝。

## Decision

采用 **Option C**。

原因：

- 它同时满足“后台自动补全”“不阻塞播放器打开”“不和播放解析耦合”“provider 可扩展”四个目标。
- 现有 `PlayerWindow` 已经支持异步刷新 `session.vod`、标题、海报和 metadata 区，因此新链路可以直接复用这个更新模型。
- 这个方案能让第一阶段只落地 `DoubanProvider` 和 `CustomPluginProvider`，但接口设计已经足够承接第二阶段 provider。

## Design

### 1. New metadata module

新增 `src/atv_player/metadata/` 子模块，负责搜索、详情获取、缓存、合并和后台 hydration。

推荐文件边界：

- `metadata/models.py`
  - `MetadataQuery`
  - `MetadataContext`
  - `MetadataMatch`
  - `MetadataRecord`
- `metadata/base.py`
  - `MetadataProvider`
- `metadata/cache.py`
  - 文件系统缓存读写
- `metadata/hydrator.py`
  - `MetadataHydrator`
  - provider 调度和合并
- `metadata/providers/douban.py`
  - `DoubanProvider`
- `metadata/providers/plugin.py`
  - `CustomPluginProvider`

播放器和控制器都只依赖 `MetadataHydrator` 暴露的入口，不直接拼 provider 逻辑。

### 2. Core models

`MetadataQuery` 表示一次搜索输入，至少包含：

- `title`
- `original_title`
- `year`
- `source_kind`
- `source_key`
- `vod_id`
- `type_name`
- `category_name`

`MetadataContext` 表示一次 hydration 的上下文，至少包含：

- 当前 `VodItem`
- 当前来源信息
- 可选当前 `PlayItem`

`MetadataMatch` 表示一次 provider 命中，至少包含：

- `provider`
- `provider_id`
- `title`
- `year`
- `score`
- `raw`

`MetadataRecord` 表示统一详情结果，至少包含：

- `poster`
- `backdrop`
- `title`
- `original_title`
- `year`
- `actors`
- `genres`
- `overview`
- `aliases`
- `season`
- `episode`
- `imdb_id`
- `tmdb_id`
- `douban_id`
- `rating`
- `detail_fields`

`MetadataRecord` 不直接暴露给 UI。它只作为统一 provider 输出，再被合并回现有 `VodItem`。

### 3. Provider interface

`MetadataProvider` 统一接口如下：

- `can_enrich(context: MetadataContext) -> bool`
- `search(candidate: MetadataQuery) -> list[MetadataMatch]`
- `get_detail(match: MetadataMatch) -> MetadataRecord`

允许 provider 既是“搜索型 provider”，也可以是“直出型 provider”：

- 搜索型 provider：先 `search`，再 `get_detail`
- 直出型 provider：`search` 可以直接返回单个确定命中，或用上下文构造稳定命中

对外调度逻辑一律由 `MetadataHydrator` 负责，调用方不关心 provider 是哪一类。

### 4. First-phase providers

#### 4.1 `CustomPluginProvider`

角色：

- 插件来源专用 provider
- 第一阶段最高优先级 provider

职责：

- 读取插件详情已有 metadata payload
- 读取插件 `ext/detail_fields`
- 把插件明确提供的 metadata 标准化为 `MetadataRecord`

行为：

- 不做模糊搜索
- 只对 `source_kind == "plugin"` 且上下文有插件 metadata 能力时启用

它可以提供：

- `poster`
- `title`
- `year`
- `actors`
- `aliases`
- `season`
- `episode`
- `imdb_id`
- `tmdb_id`
- `rating`
- `detail_fields`
- `overview`

#### 4.2 `DoubanProvider`

角色：

- 第一阶段主搜索型 provider
- 对插件来源和内置远程来源都可用

职责：

- 如果当前 `VodItem.dbid` 已有值，优先按豆瓣 ID 直取详情
- 否则按标题和年份搜索本地豆瓣数据
- 输出统一 `MetadataRecord`

它可以提供：

- `poster`
- `title`
- `original_title`
- `aliases`
- `year`
- `actors`
- `genres`
- `overview`
- `douban_id`
- `rating`
- `imdb_id`
- `detail_fields`

#### 4.3 Deferred providers

第二阶段预留但第一阶段不实现真实逻辑：

- `TMDBProvider`
- `IQiyiProvider`
- `TencentProvider`
- `BilibiliProvider`

第一阶段只保留 provider 注册位和调用顺序扩展点，不写网络实现。

### 5. Provider priority

第一阶段优先级固定如下：

- 插件来源：`CustomPluginProvider > DoubanProvider > 原始 VodItem`
- 内置远程来源：`DoubanProvider > 原始 VodItem`

这里的“原始 `VodItem`”不是 provider，只表示最终没有命中时保留现有内容。

### 6. Request and session integration

新增独立 metadata hydration 接缝，不复用 `playback_loader`。

建议在请求和会话层补两个入口：

- `OpenPlayerRequest.metadata_hydrator`
- `PlayerSession.metadata_hydrator`

形态保持和现有异步能力一致，推荐为“接收当前 session 或上下文并原地更新/返回增强结果”的可调用对象。

流程：

1. `MainWindow` 或插件控制器正常构建 `OpenPlayerRequest`
2. 对于支持范围内的来源，为请求挂上 `metadata_hydrator`
3. `MainWindow._create_player_session()` 把该回调写入 `PlayerSession`
4. `PlayerWindow.open_session()` 后台触发一次 metadata hydration
5. 成功后只更新当前 session 的详情对象和 UI

### 7. Triggering rules

第一阶段触发条件：

- 来源属于 `plugin` 或内置远程详情来源
- 当前 session 首次打开时触发

不触发的来源：

- `direct_parse`
- `yt-dlp`
- 本地媒体入口

触发限制：

- 每个 session 只自动触发一次
- 切换分集不重新做整片级 metadata scrape
- 用户后续如果需要“刷新元数据”按钮，再单独增加 bypass cache 路径

### 8. Cache design

元数据缓存采用文件系统缓存，不使用 sqlite。

缓存根目录：

- `app_cache_dir()/metadata/`

子目录建议：

- `metadata/search/<provider>/`
- `metadata/detail/<provider>/`

文件命名：

- 使用稳定 hash，避免标题中的特殊字符和路径过长问题

缓存键：

- 搜索缓存：`provider + normalized_title + year`
- 详情缓存：`provider + provider_id`

TTL：

- 搜索结果：短 TTL，建议 1 到 3 天
- 详情结果：长 TTL，建议 7 到 30 天

缓存内容：

- 只缓存 provider 的标准化结果和最少量原始字段
- 不缓存 `VodItem` 合并结果，避免来源特定字段污染通用详情缓存

### 9. Merge rules

合并策略采用“核心基础字段保守合并，简介和评分按 provider 优先级覆盖，扩展信息进入 `detail_fields`”。

字段规则如下：

- `vod_name`
  - 默认只补空
- `vod_pic`
  - 默认只补空
- `vod_year`
  - 默认只补空
- `vod_actor`
  - 默认只补空
- `type_name`
  - 默认只补空
- `dbid`
  - provider 返回豆瓣 ID 且当前为空时写入
- `vod_content`
  - 允许按 provider 优先级替换现有简介
  - 只有新简介非空，且归一化后与旧简介明显不同，才执行替换
- `vod_remarks`
  - 明确按“评分槽位”处理
  - 只有 provider 返回评分型字段时才允许覆盖
  - 不允许把标签、更新状态、简介片段写入 `vod_remarks`

评分优先级：

- 插件来源：`CustomPluginProvider > DoubanProvider > 原始评分`
- 内置远程来源：`DoubanProvider > 原始评分`

简介优先级单独处理，不跟随其他标准字段优先级：

- 插件来源：`DoubanProvider > CustomPluginProvider > 原始简介`
- 内置远程来源：`DoubanProvider > 原始简介`

原因：

- 一部分插件返回的简介会夹带 `[展开全部]`、`[收起部分]`、站点提示文案或重复段落。
- 第一阶段里，豆瓣简介比插件简介更适合作为播放器详情的最终简介来源。

简介归一化要求：

- provider 写回前先去掉常见的展开/收起标记，例如 `[展开全部]`、`[收起部分]`
- 压缩重复空白和明显重复拼接的尾段
- 清洗后如果豆瓣简介非空，则允许覆盖现有简介
- 只有在豆瓣未命中或豆瓣简介为空时，才回退到插件简介

### 10. `detail_fields` policy

扩展信息统一进入 `detail_fields`。

适合放入 `detail_fields` 的信息包括：

- `IMDb ID`
- `TMDB ID`
- `别名`
- `季数`
- `集数`
- `类型` 拆分值
- provider 自定义扩展字段

合并规则：

- 按 `label` 归并
- 同名字段如果来自更高优先级 provider，则替换
- 不同名字段直接追加

这样既能保留插件自定义 metadata，又能让豆瓣等 provider 补充标准扩展字段，而不需要改播放器详情渲染协议。

### 11. UI update behavior

metadata hydration 完成后，只允许刷新详情相关 UI，不得影响当前播放流程。

允许刷新：

- 窗口标题
- 海报
- metadata 文本/HTML
- `detail_fields`

不得触发：

- 视频重载
- playlist 重建
- playback URL 重新解析
- 当前播放中断

### 12. Failure behavior

metadata hydration 失败属于非致命失败。

规则：

- provider 报错只写播放器日志
- 搜索无命中不弹窗
- 不覆盖当前 `VodItem`
- 不影响播放和播放器打开

日志示例：

- `元数据补全失败: 豆瓣搜索超时`
- `元数据补全失败: 插件 metadata 无效`
- `元数据未命中: 豆瓣`

### 13. Stale result protection

异步 hydration 结果必须带 request/session token。

要求：

- 当用户已经切到别的片子或打开了新 session 时，旧结果不得回写
- stale result 直接丢弃，不写日志，不刷新 UI

这部分应与现有播放器异步 loader 的 request-id 防护风格保持一致。

### 14. Testing

测试至少覆盖以下场景：

- 打开插件详情页后会自动触发 metadata hydration
- 打开内置远程详情页后会自动触发 metadata hydration
- hydration 成功后会刷新标题、海报、metadata 区和 `detail_fields`
- hydration 不会重载视频、不影响当前播放 URL
- stale async result 不会写回新 session
- 插件来源按 `CustomPluginProvider > DoubanProvider` 优先级工作
- 内置远程来源按 `DoubanProvider` 工作
- 文件系统缓存命中时不会重复调用 provider
- `vod_content` 会按优先级替换
- `vod_remarks` 只接受评分型覆盖
- `detail_fields` 同 label 替换、不同 label 追加
- provider 失败只写日志，不打断播放

## Result

完成后，播放器详情会拥有一条独立于播放地址解析的元数据增强链路。插件来源和内置远程来源在打开播放器后，都能自动后台补全并刷新封面、评分、简介、演员、别名和扩展 ID 字段，同时保持现有 `VodItem`/`detail_fields` 渲染协议不变，并与现有文件系统缓存风格一致。
