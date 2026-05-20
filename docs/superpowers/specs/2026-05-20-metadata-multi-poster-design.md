# Metadata Multi Poster Design

## Summary

为 metadata 增强链路增加“多来源海报保留”能力：

- `VodItem` 不再只保留单个海报字符串
- metadata merge 期间把多个 provider 返回的海报去重后存入数组
- 播放器右侧详情区海报支持手动左右切换查看

默认主海报选择规则保持现状，仍由现有 provider 优先级决定 `vod_pic`。多海报数组只作为“可切换查看的候选海报集合”使用，不改变播放封面、历史记录或卡片列表的既有主海报语义。

## Goals

- 在 metadata merge 后保留多个来源的海报，而不是只留下最后一个主海报结果。
- 保持 `vod_pic` 的现有主海报语义和 provider 优先级规则不变。
- 让播放器详情区在存在多张海报时支持手动切换查看。
- 单海报场景保持当前体验，不引入额外 UI 噪音。
- 与原始详情/增强详情切换能力兼容。

## Non-Goals

- 不做自动轮播。
- 不做悬停暂停、缩略图条或分页圆点。
- 不改变视频 overlay、音频封面挂载、历史记录写入对主海报的使用方式。
- 不把多海报 UI 扩展到主窗口海报网格、历史页或其他列表页。
- 不调整现有 metadata provider 的文本字段 merge 优先级。

## Current Problem

当前 metadata merge 逻辑对海报字段只有单值语义：

- `MetadataRecord.poster` 进入 `merge_metadata_record(...)`
- 通过 provider 优先级决定是否覆盖 `vod.vod_pic`
- 旧海报一旦被更高优先级 provider 替换，就不会再保留

这会导致两个问题：

- 来自多个站点的海报无法并存，用户无法在详情区切换比较不同来源的封面
- UI 层如果想支持多海报，只能重新推断来源顺序，职责会泄漏到展示层

## Approach Options

### Option A: Replace `vod_pic` with a poster array everywhere

做法：

- 让 `VodItem` 只保留海报数组
- 所有现有代码都改为从数组第一项读取主海报

优点：

- 模型最纯粹
- 没有双轨字段

缺点：

- 改动面过大
- 会影响播放器、卡片列表、历史记录、音频封面等大量既有路径
- 风险与当前需求不匹配

### Option B: Keep `vod_pic` as primary poster and add a poster array

做法：

- `VodItem` 保留 `vod_pic`
- 新增 `poster_candidates: list[str]`
- merge 时维护海报数组，同时继续按现有规则维护 `vod_pic`

优点：

- 能满足当前需求
- 对现有依赖 `vod_pic` 的路径侵入最小
- UI 可直接消费数组，不必自行推断

缺点：

- 模型存在“主海报 + 候选海报”双轨语义
- 需要明确两者之间的一致性规则

### Option C: Build poster list only inside player UI

做法：

- 不改 `VodItem`
- 播放器根据 metadata 来源临时拼多海报列表

优点：

- 数据模型改动最少

缺点：

- 规则会泄漏到 UI 层
- 原始/增强详情切换时更难维护一致性
- 很难在非 UI 层精确测试 merge 结果

## Decision

采用 **Option B**。

原因：

- 当前需求只是“保留多个来源海报并在播放器详情区切换查看”，不是全面重构海报模型。
- 现有代码中大量逻辑都把 `vod_pic` 当作主海报使用，包括默认视频封面、音频封面挂载、历史记录和浏览卡片。保留它能把改动控制在 metadata merge 和详情区 UI。
- 新增 `poster_candidates` 后，数据层可以清楚表达“主海报”和“候选海报集合”的关系，避免在 UI 层重新发明 merge 规则。

## Design

### 1. Data model

在 `VodItem` 中新增：

- `poster_candidates: list[str] = field(default_factory=list)`

语义：

- 保存当前 `VodItem` 可用的海报候选列表
- 按“主海报优先，其他来源随后”的顺序排列
- 列表内容为已清洗、已去重、非空的海报 URL 或本地路径

一致性规则：

- `vod_pic` 继续代表当前首选主海报
- 如果 `poster_candidates` 非空，则其第一项必须等于 `vod_pic`
- 如果 `vod_pic` 为空，则 `poster_candidates` 也应为空

### 2. Merge behavior

metadata merge 处理海报时分成两个动作：

1. 维护主海报 `vod_pic`
2. 维护候选海报数组 `poster_candidates`

#### 2.1 主海报规则

继续沿用现有 `poster` provider 优先级：

- `tmdb`
- `bangumi`
- `official_douban`
- `local_douban`
- `douban`
- `plugin`
- `iqiyi`

也就是说：

- 更高优先级 provider 的海报仍可覆盖 `vod_pic`
- 更低优先级 provider 不能覆盖已有高优先级主海报

#### 2.2 候选数组规则

每次拿到 `record.poster` 时：

- 空字符串直接忽略
- 标准化为清洗后的字符串
- 按 URL 或路径完整字符串去重
- 若该海报成为新的 `vod_pic`，则把它移动到数组第一位
- 若该海报未成为新的 `vod_pic`，则追加到数组尾部

结果约束：

- `poster_candidates[0]` 始终对应当前 `vod_pic`
- 被覆盖掉的旧主海报不丢失，而是保留在后续位置
- 相同海报来自多个 provider 时只保留一份

示例：

1. 初始站内详情：`vod_pic = site-a`
   `poster_candidates = [site-a]`
2. 后续 TMDB 命中：`tmdb-a`
   `vod_pic = tmdb-a`
   `poster_candidates = [tmdb-a, site-a]`
3. 再命中 Bangumi：`bgm-a`
   `vod_pic` 仍为 `tmdb-a`
   `poster_candidates = [tmdb-a, site-a, bgm-a]`

### 3. Non-merge initialization paths

不是所有 `VodItem` 都经过 metadata merge 才产生，因此需要统一初始化规则：

- 任何直接构造 `VodItem(vod_pic=...)` 的路径默认允许 `poster_candidates` 为空
- 首次进入需要展示多海报能力的播放器详情区时，如果 `poster_candidates` 为空且 `vod_pic` 非空，可视为隐式单海报列表 `[vod_pic]`

这样可以避免为了兼容全项目所有 `VodItem` 构造点而做大范围补丁，同时保证播放器详情区总能拿到统一的“当前可展示海报列表”。

### 4. Player detail poster UI

播放器右侧详情区沿用现有 `poster_label`，在其附近增加两个轻量切换按钮：

- 上一张
- 下一张

显示规则：

- 只有当前 metadata 视图对应的海报列表长度大于 1 时显示
- 单张海报或无海报时隐藏

交互规则：

- 只支持手动点击切换
- 不自动轮播
- 到边界后循环切换
  - 第一张点击“上一张”跳到最后一张
  - 最后一张点击“下一张”跳到第一张

视觉要求：

- 保持低干扰，小尺寸
- 不新增文字标签
- 不压缩 metadata 文本区现有布局结构

### 5. Poster source selection

当前播放器里存在两类海报显示来源：

- 详情区海报 `poster_label`
- 视频 overlay / 音频封面使用的主海报来源

本轮只改变详情区海报：

- `poster_label` 根据“当前详情视图 + 当前手动索引”决定展示哪一张

本轮不改变视频封面相关逻辑：

- `_preferred_video_poster_source()` 继续优先使用当前 item override、session override、`vod_pic`、默认视频封面
- 音频封面挂载仍只使用主海报语义

这样可以保证多海报切换只影响详情查看，不影响播放中的封面一致性。

### 6. Original vs enhanced metadata compatibility

播放器已经支持：

- 增强后详情
- 原始详情快照

多海报能力必须跟随当前展示中的 metadata 视图，而不是只绑定 `session.vod`。

规则：

- 当前显示增强详情时，海报列表来自增强后的 `session.vod`
- 当前显示原始详情时，海报列表来自 `session.original_vod`

切换详情视图时：

- 重新计算可展示海报列表
- 重置当前海报索引为 0

原因：

- 原始详情和增强详情的主海报与候选海报集合都可能不同
- 重置索引可以避免切换后落在无效位置，或误以为“保留了上一视图的海报选择”

### 7. Session and refresh lifecycle

播放器需要维护一个会话级海报索引，例如：

- `current_metadata_poster_index`

行为：

- 打开新会话时重置为 `0`
- metadata hydrate 成功后重置为 `0`
- 手动 scrape apply 成功后重置为 `0`
- 切换原始/增强详情时重置为 `0`
- 只有用户点击左右按钮时才改变

边界条件：

- 当前索引超出新列表长度时，强制回到 `0`
- 无海报时清空详情区海报显示

### 8. Testing

需要补两类测试。

#### 8.1 Metadata merge tests

覆盖：

- 初始只有 `vod_pic` 时，新 provider 海报会进入候选数组
- 高优先级 provider 覆盖 `vod_pic` 时，旧主海报保留在数组后面
- 低优先级 provider 不能覆盖 `vod_pic`，但其海报仍会进入数组
- 重复海报不会重复加入数组
- `poster_candidates[0]` 始终与 `vod_pic` 一致

#### 8.2 Player window UI tests

覆盖：

- 单海报时左右按钮隐藏
- 多海报时左右按钮显示
- 点击下一张和上一张后，详情区海报来源发生切换
- 边界点击会循环切换
- 切换原始/增强详情时重置到各自列表第一张
- metadata 刷新后索引重置且展示增强后第一张主海报

## Risks and Constraints

- `VodItem` 的很多构造路径目前只设置 `vod_pic`，不会同步填 `poster_candidates`。如果实现时强行要求全量调用点都显式填充数组，会带来无关改动扩散。
- 播放器已有异步海报加载流程。手动切换海报时必须保证 request id 和最终显示结果一致，避免前一张晚到后覆盖当前选择。
- 原始详情快照如果直接深拷贝 `VodItem`，需要确保 `poster_candidates` 也一并被保留。

## Implementation Outline

1. 给 `VodItem` 增加 `poster_candidates` 字段。
2. 在 metadata merge 中抽出海报候选列表维护逻辑，并保证与 `vod_pic` 一致。
3. 让播放器基于“当前 metadata 视图”解析可展示海报列表，并维护当前索引。
4. 在详情区海报附近增加左右切换按钮和刷新逻辑。
5. 补充 merge 与 player window 的 focused tests。
