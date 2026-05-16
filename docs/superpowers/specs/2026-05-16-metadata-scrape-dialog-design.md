# Metadata Scrape Dialog Design

## Summary

为播放器新增一个独立的 `刮削` 对话框，交互风格对齐现有 `弹幕源`：

- 允许修改搜索词与年份
- 允许选择单个 provider，或选择 `全部` 并发搜索
- 搜索结果按 provider 分组展示
- 搜索完成后默认高亮第一条结果，但不会自动写回
- 只有用户手动点击 `应用结果` 才会更新当前详情

另外新增“手动刮削绑定”持久化：

- 绑定键只使用 `标题 + 年份`
- 绑定值保存用户手动选中的 `provider + provider_id`
- 下次打开同名同年份视频时，优先复用该绑定结果，而不是重新依赖自动搜索首条结果

这条新链路必须复用现有 metadata provider、detail cache、merge 规则，不复制第二套 metadata 体系。

## Goals

- 在 `PlayerWindow` 中新增 `刮削` 入口与对话框。
- 支持 `全部` provider 并发搜索，并按 provider 分组展示结果。
- 允许用户修改 `标题`、`年份`、`搜索来源` 后重新搜索。
- 搜索完成后默认选中首条结果，但必须手动点击 `应用结果` 才写回。
- 应用结果后立即刷新当前播放器窗口里的海报、详情、扩展字段、标题和日志。
- 将手动选择的 metadata 结果按 `标题 + 年份` 持久化，供后续同名同年份视频自动复用。
- 在现有自动 metadata hydration 前优先命中这份手动绑定。

## Non-Goals

- 本轮不做自动最佳匹配写回。
- 本轮不把绑定键扩展到 `vod_id`、来源类型或剧集级维度。
- 本轮不新增用户可配置的 provider 排序。
- 本轮不改变现有 metadata 字段 merge 优先级。
- 本轮不在主窗口、列表页或全局搜索页增加刮削入口。

## Current Problem

当前播放器只有“自动 metadata enhancement”能力，没有“手动指定刮削结果”的交互入口。

现状限制：

- `MetadataHydrator` 只能按 provider 顺序自动搜索，并取首个匹配结果继续拉详情。
- 用户无法像 `弹幕源` 一样手动修改搜索词、切换 provider、查看候选结果并指定应用目标。
- 现有 detail cache 只缓存 provider 搜索与详情结果，不记录“用户最终手动确认了哪一条”。
- 即使用户发现自动命中不准确，也无法把正确结果绑定到同名视频供后续复用。

## Approach Options

### Option A: Add a thin manual scrape workflow on top of existing metadata providers

做法：

- 在 `PlayerWindow` 新增 `刮削` 对话框
- 新增独立 `MetadataScrapeService`
- 新增独立 `MetadataBindingRepository`
- 现有自动 hydration 保留，只在开始前增加“优先命中手动绑定”逻辑

优点：

- 最大化复用现有 provider、cache 和 merge 逻辑
- 对现有自动增强链路侵入小
- 用户心智与 `弹幕源` 对话框保持一致

缺点：

- `PlayerWindow` 会再承担一组新对话框状态
- 需要新增一份绑定仓库

### Option B: Fold manual scraping into `MetadataHydrator`

做法：

- 让 `MetadataHydrator` 同时承担自动增强与手动候选查询/应用

优点：

- 理论上只有一条 metadata 主链路

缺点：

- `MetadataHydrator` 角色会从后台增强膨胀成 UI 交互工作流
- 需要更大范围重构，不适合本轮目标

### Option C: Build a fully separate metadata scraping stack

做法：

- 单独实现新的 provider 聚合、缓存和字段写回规则

优点：

- 边界表面上最独立

缺点：

- 会复制现有 metadata 体系
- 长期维护成本更高

## Decision

采用 **Option A**。

原因：

- 用户需求本质上是在现有 metadata 能力上增加一个“像弹幕源一样的手动确认入口”，不是重写整个 metadata 架构。
- 现有 provider、cache、merge 规则已经成熟，复用它们比复制一套链路更稳妥。
- 手动绑定与自动增强可以自然并存：手动绑定决定“优先取谁”，现有 merge 规则继续决定“字段如何覆盖”。

## Design

### 1. UI entry points

播放器新增一个 `刮削` 入口，和 `弹幕源`、`弹幕设置` 保持同级：

- 工具栏新增 `刮削` 按钮
- 视频上下文菜单新增 `刮削`

本轮不新增快捷键，避免和现有播放器快捷键继续竞争。

按钮只在当前存在活动播放会话时可用。

### 2. Scrape dialog layout

新增 `刮削` 对话框，布局参考 `弹幕源`：

- 顶部输入区
  - `标题`
  - `年份`
  - `搜索来源`
- 中间结果区
  - 左侧：provider 分组列表
  - 右侧：当前 provider 的候选结果列表
- 底部状态区
  - 状态文案
- 底部操作区
  - `重新搜索`
  - `恢复默认搜索词`
  - `应用结果`

字段默认值：

- `标题`：当前 `session.vod.vod_name`
- `年份`：当前 `session.vod.vod_year`
- `搜索来源`：默认 `全部`

若当前条目没有标题：

- 打开对话框允许查看
- 但禁止触发搜索
- 状态区提示 `当前条目缺少标题`

### 3. Search provider options

provider 选择需要显式支持：

- `全部`
- `本地豆瓣`
- `TMDB`
- `alist-tvbox豆瓣`
- `豆瓣`
- `插件`，仅当当前会话存在插件 metadata provider 时显示

选择 `全部` 时：

- 并发搜索所有当前可用 provider

选择单个 provider 时：

- 只搜索该 provider

### 4. Search interaction rules

打开对话框时：

- 仅填充默认搜索参数
- 不自动触发搜索
- 如果当前会话里已经搜索过一次且搜索参数未变，可以复用本次会话内的已有结果

点击 `重新搜索` 时：

- 读取当前标题、年份、provider 选择
- 启动异步搜索
- 若 provider=`全部`，并发请求多个 provider
- 所有 provider 返回后统一刷新 UI
- 搜索完成后默认高亮第一条候选，但不自动应用

点击 `恢复默认搜索词` 时：

- 标题、年份恢复到当前会话初始值
- provider 保持用户当前选择
- 立即重新执行一次搜索

点击 `应用结果` 时：

- 必须存在当前选中的候选项
- 若无选中项则不执行任何写回
- 拉取该候选项 detail
- 使用现有 `merge_metadata_record(...)` 将 detail 合并进当前 `session.vod`
- 刷新：
  - 海报
  - metadata 文本
  - 扩展字段
  - 窗口标题
  - 日志
- 将该候选对应的 `provider + provider_id` 写入手动绑定仓库

### 5. Search result presentation

搜索结果以 provider 分组显示。

左侧 provider 列表：

- 文案格式：`来源名 (结果数)`

右侧候选列表：

- 每条候选至少显示 `标题`
- 如有年份则追加 `年份`
- 如 provider 提供可展示的附加信息，可增加简短摘要

默认选择规则：

- 搜索完成后，如果存在至少一条结果，默认高亮“结果列表中的第一条”
- 该默认高亮只是减少点击次数，不代表自动确认
- 只有用户手动点击 `应用结果` 才算真正选择

### 6. `MetadataScrapeService`

新增一个薄服务层，职责限定为：

- 接收 `MetadataQuery` 与 provider 过滤条件
- 并发调用多个 provider 的 `search`
- 将结果整理为按 provider 分组的 UI 数据
- 根据用户选中的候选项调用 provider `get_detail`
- 复用现有 `MetadataCache` 保存 search/detail 结果

该服务不负责：

- 管理播放器 UI 状态
- 持久化用户绑定
- 自定义字段 merge 规则

### 7. Candidate and group models

需要新增适合 UI 展示的数据模型，例如：

- `MetadataScrapeCandidate`
  - `provider`
  - `provider_label`
  - `provider_id`
  - `title`
  - `year`
  - `subtitle`
  - `raw`
- `MetadataScrapeGroup`
  - `provider`
  - `provider_label`
  - `items`

这些模型仅用于对话框交互，不替代现有 `MetadataMatch`。

原因：

- `MetadataMatch` 是 provider 层协议对象
- UI 需要额外的展示字段与分组信息

### 8. Manual binding persistence

新增 `MetadataBindingRepository`，负责持久化“手动刮削绑定”。

绑定键：

- 仅使用 `标题 + 年份`
- 标题归一化：
  - 去首尾空白
  - 压缩连续空白
  - 大小写归一
- 年份归一化：
  - 只保留四位年份

绑定值：

- `provider`
- `provider_id`
- `matched_title`
- `matched_year`
- `updated_at`

本轮明确不加入：

- `vod_id`
- `source_kind`
- `source_key`
- 剧集级键

这是用户明确选择的跨来源复用策略。

### 9. Auto reuse in `MetadataHydrator`

`MetadataHydrator` 增加一个前置步骤：

1. 根据当前 `MetadataContext` 生成 `标题 + 年份` 绑定键
2. 查询 `MetadataBindingRepository`
3. 若命中：
   - 优先尝试读取 detail cache
   - cache 未命中时，按命中的 `provider + provider_id` 拉 detail
   - detail 成功则先 merge 到 `VodItem`
4. 然后继续现有 provider 链路，让其他 provider 只负责补字段，而不是重新决定“主命中结果”

约束：

- 手动绑定决定“优先取哪条详情”
- 现有字段 merge 规则仍决定“哪些字段最终覆盖”

### 10. Invalid binding handling

若手动绑定命中后拉 detail 失败：

- 不中断整个 hydration
- 回退到现有自动 search 流程
- 删除这条失效绑定

失效场景包括：

- provider 不再可用
- `provider_id` 已无效
- detail 解析异常
- provider 配置缺失导致无法取 detail

这样可以避免坏绑定长期阻塞自动增强。

### 11. Logging and status text

状态区与日志文案：

- 搜索中：
  - `刮削搜索中（全部）...`
  - `刮削搜索中（TMDB）...`
- 搜索失败：
  - `刮削搜索失败: ...`
- 应用失败：
  - `刮削应用失败: ...`
- 应用成功：
  - 继续沿用现有 `元数据已更新: ...`
  - 额外追加：
    - `已绑定手动刮削结果: <标题> (<来源>)`

并发搜索时：

- 单个 provider 失败不应让整个搜索流程失败
- 最终状态区可以显示“部分来源失败”的摘要，但不阻止用户使用已返回结果

### 12. Caching behavior

手动刮削必须复用现有 metadata cache：

- search 结果按 provider + title + year 缓存
- detail 结果按 provider + provider_id 缓存

手动绑定不是 search cache 的别名：

- binding 记录的是“用户最终确认选择了谁”
- cache 记录的是“provider 返回过什么”

两者职责不同，不能互相替代。

## Data Storage

在现有 app 数据库中新增一张独立表：

- `metadata_bindings`

表字段：

- `query_key TEXT PRIMARY KEY`
- `normalized_title TEXT NOT NULL`
- `normalized_year TEXT NOT NULL`
- `provider TEXT NOT NULL`
- `provider_id TEXT NOT NULL`
- `matched_title TEXT NOT NULL DEFAULT ''`
- `matched_year TEXT NOT NULL DEFAULT ''`
- `updated_at INTEGER NOT NULL`

原因：

- 绑定属于用户偏好/确认结果，应该和 `AppConfig`、历史记录一样进入持久化层
- 不适合写入 cache 目录的临时 JSON

## Testing

### 1. Repository tests

覆盖：

- 按 `标题 + 年份` 写入与读取绑定
- 标题与年份归一化一致时可命中
- 更新已有绑定时会覆盖旧值
- 删除失效绑定成功

### 2. Service tests

覆盖：

- `全部` 模式下并发搜索多个 provider 并正确分组
- 单 provider 过滤只搜索目标 provider
- 单个 provider 失败不会让整个结果失败
- `apply` 只对选中候选拉 detail
- `apply` 后正确调用现有 merge 规则

### 3. Hydrator tests

覆盖：

- 命中手动绑定时优先走绑定 detail
- 绑定命中 detail cache 时不重复请求 provider
- 绑定 detail 失败时回退到原自动 search 流程
- 绑定失效时会被清理

### 4. Player window UI tests

覆盖：

- 存在新的 `刮削` 按钮与对话框
- 对话框默认填充标题、年份、provider
- `重新搜索` 会异步触发搜索
- 搜索完成后默认高亮首条，但不会自动更新 metadata
- 点击 `应用结果` 后刷新 metadata、poster、detail fields、log
- 应用成功后会写入绑定
- 重新打开同名同年份视频时，自动复用绑定结果

## Risks

- `标题 + 年份` 作为全局绑定键可能把同名同年份但不同作品错误合并到同一绑定。
- `全部` 并发搜索会引入更多异步状态，若 UI 刷新时序处理不好，容易出现旧结果覆盖新结果。
- `PlayerWindow` 已较大，继续叠加对话框状态会增加维护压力。

这些风险里，第一条是用户显式接受的策略；第二、三条需要通过服务分层和测试覆盖控制。

## Rollout

按以下顺序落地：

1. 新增 `MetadataBindingRepository` 与数据库迁移
2. 新增 `MetadataScrapeService` 与候选分组模型
3. 让 `MetadataHydrator` 支持手动绑定优先复用
4. 为 `PlayerWindow` 增加 `刮削` 对话框与异步搜索/应用逻辑
5. 补全 service、hydrator、UI 测试
