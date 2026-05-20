# Metadata Original Detail Toggle Design

## Summary

为播放器右侧详情区增加一个无文字的轻量开关，让用户可以在：

- 元数据增强后的详情
- 增强前保留的原始详情

之间切换显示。

自动元数据增强和手动刮削应用都必须保留“增强前”的详情快照。默认显示增强后详情；只有当原始详情与增强后详情存在可见差异时，开关才显示。

## Goals

- 保留当前播放会话在增强前的原始详情数据。
- 支持自动 metadata hydration 后切回查看原始详情。
- 支持手动 metadata scrape apply 后切回查看原始详情。
- 在播放器右侧详情区提供一个无文字、小尺寸、低干扰的切换控件。
- 切换只影响详情显示，不影响播放、当前索引、选集、弹幕和历史记录。

## Non-Goals

- 不把“显示原始详情”的选择做成全局持久化设置。
- 不修改 metadata provider、cache、merge 的优先级规则。
- 不把原始详情快照写入历史记录或数据库。
- 不新增文字标签、tab 或额外说明文案。
- 不扩展到主窗口、卡片列表或其他详情展示区域。

## Current Problem

当前播放器里的自动增强和手动刮削都会直接覆盖 `session.vod`：

- 增强前的 `vod_content`
- 增强前的 `detail_fields`
- 增强前的基础字段，如标题、年份、地区、演员等

一旦覆盖，界面上就无法再查看增强前的原始详情。对于用户来说，这会带来两个问题：

- 无法回看站内原始简介、原始扩展字段是否被增强结果替换掉
- 无法快速对比“原始详情”和“增强详情”的差异

## Approach Options

### Option A: Store one original-detail snapshot per player session

做法：

- 在 `PlayerSession` 中保存一份原始 `VodItem` 快照
- 打开会话时建立快照
- 自动增强和手动刮削只更新 `session.vod`
- UI 渲染时根据开关决定读取 `session.vod` 还是原始快照

优点：

- 侵入面最小
- 不污染 `VodItem` 基础模型
- 与现有 hydration / scrape apply 流程兼容

缺点：

- 需要明确“何时冻结原始快照，何时允许未增强的晚到详情更新快照”

### Option B: Add `original_*` fields directly onto `VodItem`

做法：

- 给 `VodItem` 的各个详情字段增加 `original_` 版本

优点：

- 数据跟随对象传播

缺点：

- 模型污染严重
- 所有构造、复制、replace、merge 路径都要同步维护
- 容易遗漏字段

### Option C: Track field-level diffs instead of a snapshot

做法：

- 增强时仅记录被覆盖的字段差异
- 界面切换时根据 diff 反向构造原始视图

优点：

- 不必保存第二份完整对象

缺点：

- 实现复杂
- 对异步详情更新、二次刮削、字段替换顺序更脆弱

## Decision

采用 **Option A**。

原因：

- 需求本质上是“同一会话保留两套详情视图”，快照模型最直接。
- 现有代码已经把详情展示集中在 `PlayerWindow` 渲染层，增加“当前显示哪份 vod”的选择比改动 metadata 数据模型更稳。
- 当前增强链路已经可能异步晚到，保留一份会话级原始快照更容易处理先后顺序。

## Design

### 1. Session data model

在 `PlayerSession` 新增两类会话态：

- `original_vod`
  - 保存增强前原始详情快照
- `show_original_metadata`
  - 当前会话是否切到原始详情视图

语义约束：

- `original_vod` 只代表“本次会话里未经过 metadata 增强写回的详情状态”
- 默认 `show_original_metadata = False`
- 新会话打开时总是默认显示增强后详情

### 2. Snapshot lifecycle

#### On session open

- `open_session(...)` 时，用当前 `session.vod` 建立 `original_vod` 初始快照

#### On non-metadata detail resolution

如果播放器后续通过现有详情解析链路拿到更完整但尚未增强的详情：

- 正常更新 `session.vod`
- 同时更新 `original_vod`

前提是：

- 当前这次更新不是 metadata hydration 或手动 scrape apply 产生的增强结果

这样可以保证“原始详情”不是打开瞬间的半成品，而是增强前最终可见的站内详情。

#### On metadata hydration

自动增强成功后：

- 只更新 `session.vod`
- 不再修改 `original_vod`

#### On metadata scrape apply

手动刮削应用成功后：

- 只更新 `session.vod`
- 不再修改 `original_vod`

### 3. Visibility rules for the toggle

无文字开关只在以下条件同时满足时显示：

- 当前存在活动播放会话
- 原始详情快照存在
- 原始详情与增强后详情有至少一个可见字段差异
- 详情面板本身处于显示状态

“可见字段差异”包括：

- 标题、类型、年代、地区、语言、评分、导演、演员、豆瓣 ID
- 简介
- 当前详情视图会显示的 `detail_fields`

如果两份详情完全等价：

- 隐藏开关
- 强制回到增强后视图状态

### 4. UI design

开关位置：

- 放在右侧详情区标题行，与现有 `metadata_heading` 同一行的右侧

控件形式：

- 小尺寸
- 无文字
- 可 check
- 选中态表示“当前显示原始详情”

视觉要求：

- 不新增标题说明文字
- 尺寸和强调度低于主要播放控制按钮
- 样式跟随当前主题

交互要求：

- 鼠标点击即可切换
- 不需要 tooltip 之外的额外说明
- 默认未选中

tooltip 建议：

- 未选中时：`显示原始详情`
- 选中时：`显示增强后详情`

### 5. Rendering rules

详情区渲染不再固定读取 `session.vod`，而是先得到一个“当前详情视图对应的 vod”：

- `show_original_metadata = False` 时读 `session.vod`
- `show_original_metadata = True` 时读 `original_vod`

以下渲染全部统一切换来源：

- metadata 文本区
- 扩展字段区
- 详情区里依赖 `vod` 的基础字段

本轮不切换：

- 海报
- 选集标题
- 窗口标题
- 播放项对象

原因：

- 需求明确指向“详情数据”
- 如果连海报和窗口标题一起回切，会把“原始详情视图”扩大成“整条媒体状态回滚”，超出本轮范围

### 6. Behavior during updates

#### When hydration succeeds

- 如果当前正在显示增强后详情，界面立即刷新为新结果
- 如果当前正在显示原始详情，界面也应保留在原始视图，但开关状态和差异判定要重新计算

#### When scrape apply succeeds

- 与 hydration 同样规则

#### When a new session opens

- 重置为增强后详情视图
- 重新计算开关是否显示

#### When no enhanced result exists

- 隐藏开关
- 详情区行为与当前实现保持一致

## Error Handling

- 原始快照缺失时，回退到增强后详情并隐藏开关
- 异步增强失败时，不改变当前视图状态
- 异步详情解析晚到时，只要它不是 metadata 增强结果，就允许同步刷新原始快照
- 任何切换失败都不能影响播放流程

## Testing

需要覆盖以下场景：

- 自动增强后显示无文字开关，并且可切到原始简介
- 手动刮削应用后显示无文字开关，并且可切到原始简介和原始扩展字段
- 原始与增强后无差异时隐藏开关
- 切换详情视图不影响当前播放索引和播放状态
- 新会话打开时重置为增强后详情视图
- 晚到的非增强详情解析会刷新原始快照
- 晚到的 metadata 增强不会污染原始快照

## Risks

- 当前 `PlayerWindow` 里 `session.vod` 被多条链路直接覆盖，必须准确区分“普通详情更新”和“metadata 增强更新”
- 如果只切换简介而遗漏 `detail_fields`，用户会看到混合视图
- 若错误地在手动刮削后重写原始快照，会让“原始详情”失真

## Decisions

- 使用会话级 `VodItem` 快照保存原始详情
- 使用无文字轻量开关，不使用 tab，不加文字标签
- 默认显示增强后详情
- 开关只作用于当前播放器会话
- 只切换详情区数据，不回切海报、窗口标题和选集标题
