# Episode Title Enhancement Design

## Goal

在播放器右侧现有选集列表上方增加标题视图切换 tab，让用户可以在 `剧集标题` 和 `原始文件名` 之间切换。默认显示 `剧集标题`。该能力受高级设置中的总开关控制，不记住用户临时切换结果。

这个能力是来源无关的“剧集标题增强”，TMDB 只是其中一个来源。未来爱奇艺、腾讯、B 站和插件自定义标题都应复用同一套模型和 UI。

## Scope

本次设计覆盖：

- 高级设置新增“启用剧集标题增强”开关
- `PlayItem` 增加原始标题与增强标题字段
- 播放器右侧选集列表上方增加标题视图 tab
- 标题增强数据在 playlist 构建/替换时挂到 `PlayItem`
- 多来源标题增强的统一优先级与回退规则

本次设计不要求：

- 一次性实现所有站点的剧集标题抓取
- 重新设计历史记录、弹幕、播放索引逻辑
- 把“剧集标题增强”做成全局持久化视图偏好

## User Experience

### Entry conditions

- 高级设置开启“启用剧集标题增强”
- 当前播放列表中，至少有一个 `PlayItem` 同时具备：
  - `original_title`
  - 非空且与原始标题实质不同的 `episode_display_title`

只有满足以上条件时，播放器右侧选集列表上方才显示 tab。

### Tab behavior

- tab 固定两个：
  - `剧集标题`
  - `原始文件名`
- 默认选中 `剧集标题`
- 用户手动切换只影响当前打开的播放器会话
- 打开新会话时重新默认到 `剧集标题`
- tab 只切换列表展示文案，不切换 playlist 数据对象，不影响当前播放项和索引

### Visibility rules

- 开关关闭：不显示 tab
- 没有增强标题：不显示 tab
- 增强标题与原始标题等价：不显示 tab
- 替换 playlist 后重新计算 tab 是否显示

## Data Model

### AppConfig

新增布尔字段：

- `episode_title_enhancement_enabled: bool = False`

对应高级设置文案：

- `启用剧集标题增强`

### PlayItem

新增字段：

- `original_title: str = ""`
- `episode_display_title: str = ""`
- `episode_title_source: str = ""`

字段语义：

- `original_title`
  - 原始文件名或原始播放列表标题
  - 在 `PlayItem` 初次构建时写入
- `episode_display_title`
  - 增强后的剧集标题
  - 例如 `第1集 星门初启`
- `episode_title_source`
  - 标记增强标题来源
  - 例如 `plugin` / `iqiyi` / `tencent` / `bilibili` / `tmdb`

现有 `title` 保持兼容，但不作为 tab 切换的唯一依据。UI 显示优先读取新字段。

## Architecture

### Separation of responsibilities

职责划分如下：

- 标题增强来源层：
  - 负责产出“集号 -> 标题”的映射
  - 可以来自插件显式返回、站点原生数据、TMDB 季信息等
- playlist 构建/替换层：
  - 负责把增强标题映射写入 `PlayItem.episode_display_title`
  - 同时保留 `PlayItem.original_title`
- PlayerWindow：
  - 只负责根据 tab 选择显示哪一种标题
  - 不负责抓取或推断标题来源

### Source-neutral design

系统不引入 `tmdb_title` 这类来源绑定字段。所有增强标题统一落到：

- `episode_display_title`
- `episode_title_source`

这样未来接入爱奇艺、腾讯、B 站、插件自定义标题时，无需改 UI 和基础模型。

## Data Flow

### Build phase

1. 详情请求进入后，按现有逻辑构建 `PlayItem`
2. 每个 `PlayItem` 在最早构建时保存 `original_title`
3. 如果“剧集标题增强”开关关闭，流程结束
4. 如果开关开启，系统尝试为当前 playlist 收集剧集标题映射
5. 按统一优先级写入 `episode_display_title`
6. PlayerWindow 打开会话时检查当前 playlist 是否满足 tab 显示条件

### Replacement phase

以下会产生 replacement playlist 的场景也需要执行同样的数据流：

- 网盘替换 playlist
- 离线下载替换 playlist
- YouTube / 其他解析后回填 playlist
- 后续扩展的异步详情补齐

替换后的新 playlist 重新计算：

- `original_title`
- `episode_display_title`
- `episode_title_source`
- tab 是否显示
- 默认 tab 选中状态

## Priority Rules

当多个来源都能提供剧集标题时，采用以下优先级：

1. 插件显式返回的剧集标题
2. 站点原生详情页或播放器页可解析出的剧集标题
3. TMDB 季/集标题
4. 其他后备来源

只有更高优先级来源才允许覆盖已有 `episode_display_title`。

## Display Rules

PlayerWindow 中两种视图的文本选择规则：

### `剧集标题`

按以下顺序选择：

1. `episode_display_title`
2. `title`
3. `original_title`

### `原始文件名`

按以下顺序选择：

1. `original_title`
2. `title`

tab 只影响列表项文本，不影响：

- 当前 `PlayItem` 身份
- 播放 URL
- 播放索引
- 历史记录 key
- 弹幕搜索逻辑

## Failure Handling

- 任一来源查询失败，不影响播放
- 没拿到增强标题时，`episode_display_title` 留空
- 如果增强标题和原始标题实质相同，视为“没有增强”
- 异步增强晚到时，只刷新右侧列表显示
- 异步增强不得自动切换当前播放项
- 异步增强不得自动跳集

## Testing

需要覆盖以下测试场景：

- 开关关闭时不显示 tab
- 开关开启但没有增强标题时不显示 tab
- 开关开启且存在增强标题时显示 tab
- 默认选中 `剧集标题`
- 切换到 `原始文件名` 后只改变列表文案，不改变当前索引
- 打开新会话时恢复默认选中 `剧集标题`
- 替换 playlist 后 tab 状态正确重算
- 多来源并存时按优先级取增强标题
- 增强标题与原始标题相同时隐藏 tab
- 异步增强晚到时仅刷新显示，不影响当前播放状态

## Implementation Notes

建议实现顺序：

1. 配置项与高级设置开关
2. `PlayItem` 新字段与 playlist 构建阶段填充 `original_title`
3. PlayerWindow 标题视图 tab 与显示切换
4. 标题增强写入接口与优先级规则
5. 先接一条来源链路验证 UI，例如 TMDB
6. 再逐步接入爱奇艺、腾讯、B 站、插件自定义标题

## Risks

- 当前代码里存在多处 replacement playlist 逻辑，任何遗漏都会导致 tab 状态不一致
- 如果把显示逻辑散落在多个 UI 刷新函数里，后续会导致标题来源混乱
- 如果错误地复用 `title` 作为原始标题，后续增强覆盖后会丢失“原始文件名”视图

## Decisions

- tab 放在播放器右侧现有选集列表上方
- tab 切换的是同一条播放列表的标题视图，不是两套独立 playlist
- 默认显示 `剧集标题`
- 不记住用户切换结果
- 高级设置必须提供总开关
- 设计按 provider-neutral 建模，不能只绑定 TMDB
