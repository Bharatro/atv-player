# m3u Proxy Segment Prefetch Size Design

## Goal

在 `高级设置 -> 播放设置` 中新增配置项 `m3u代理分片预取大小`，用于控制本地 HLS 代理在请求当前分片后，额外向后预取多少个后续分片。

默认值为 `2`。

## User-Facing Behavior

- 新增播放设置字段：`m3u代理分片预取大小`
- 默认值：`2`
- 语义：当前分片之后，再预取多少个后续分片
- `0`：关闭预取
- `N > 0`：最多向后预取 `N` 个分片

示例：

- 当前播放索引是 `5`，配置是 `2`，则尝试预取 `6` 和 `7`
- 当前播放索引是 `5`，配置是 `1`，则只尝试预取 `6`
- 当前播放索引是 `5`，配置是 `0`，则不发起任何预取

## Scope

本次只调整共享 HLS 代理的分片预取行为，不改变以下内容：

- mpv 自身缓存逻辑
- DASH / ISO 的专用播放逻辑
- 广告过滤逻辑
- 预取线程模型

## Design

### 1. AppConfig

在 `AppConfig` 增加新字段：

- `m3u_proxy_segment_prefetch_size: int = 2`

该字段作为全局播放偏好配置，由高级设置保存并由 HLS 代理读取。

### 2. Storage

在 `SettingsRepository` 中新增数据库列：

- 列名：`m3u_proxy_segment_prefetch_size`
- 默认值：`2`

兼容策略：

- 新库在建表时直接包含该列
- 老库在初始化阶段通过 `ALTER TABLE` 补列
- 读取时做整数归一化，异常值回退到 `2`

归一化规则：

- 非整数：回退到 `2`
- 小于 `0`：钳制到 `0`
- 大于 `10`：钳制到 `10`

## 3. Advanced Settings UI

在 `高级设置 -> 播放设置` 中新增一个整数输入框：

- 标签：`m3u代理分片预取大小`
- 占位提示：`0 - 10`

保存时执行整数校验：

- 必须是整数
- 必须在 `0` 到 `10` 之间

校验失败时阻止保存，并沿用现有 `QMessageBox.warning` 交互模式。

### 4. Proxy Injection

`LocalHlsProxyServer` 在构造 `SegmentProxy` 时接收该配置值。

推荐方式：

- `LocalHlsProxyServer` 新增构造参数 `segment_prefetch_size: int = 2`
- 在 `AppCoordinator` 创建 `LocalHlsProxyServer` 时，从 `repo.load_config()` 读取该值并传入

该设置作为应用级共享代理行为，不按单次播放请求单独传参。

### 5. SegmentProxy Behavior

`SegmentProxy.schedule_prefetch()` 从固定预取后两个分片，改为按配置动态预取：

- 如果配置值 `<= 0`，直接返回
- 否则遍历 `current_index + 1` 到 `current_index + prefetch_size`
- 遇到超出分片总数时自动停止
- 已缓存的分片继续跳过，不重复预取

保留现有行为：

- 预取请求使用后台线程
- 预取请求不会递归触发下一轮整段预取
- 分片缓存和 in-flight 去重逻辑不变

## Alternatives Considered

### Option A: 全局配置字段并贯通现有设置链路

优点：

- 满足用户在高级设置中配置的需求
- 持久化、默认值、迁移和测试边界都清晰
- 与现有播放设置项风格一致

缺点：

- 需要同时修改模型、存储、UI 和代理构造路径

### Option B: 仅在 SegmentProxy 中改成可调常量

优点：

- 改动最小

缺点：

- 无法通过高级设置配置
- 不支持持久化
- 不符合当前需求

最终采用 Option A。

## Testing

新增或更新测试覆盖以下行为：

### Storage

- `AppConfig()` 默认值为 `2`
- 数据库存取该字段成功
- 缺失列时迁移成功
- 非法值读取时回退或钳制到合法范围

### Advanced Settings Dialog

- 能加载现有配置值
- 能保存用户输入的合法整数
- 输入非整数时报错并阻止保存
- 输入超出范围时报错并阻止保存

### SegmentProxy

- 默认值 `2` 时预取后续两个分片
- `1` 时只预取一个后续分片
- `0` 时不预取
- 预取不会超出分片列表尾部

### App Wiring

- `AppCoordinator` 创建本地 HLS 代理时，会把当前配置值传入

## Risks

- 设置值过大可能增加无效网络消耗和线程数量
  缓解：首版把上限限制在 `10`

- 启动时构造的共享代理若不接收配置，会继续使用旧的固定值
  缓解：增加应用层注入测试

## Out of Scope

- 运行中热更新已创建 HLS 代理的预取大小
- 为不同站点或不同播放源单独配置预取大小
- 动态根据网速或缓冲状态自动调整预取大小
