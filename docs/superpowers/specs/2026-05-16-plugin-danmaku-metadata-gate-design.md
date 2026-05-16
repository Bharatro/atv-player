# Plugin Danmaku Metadata Gate Design

## Summary

为爬虫插件来源增加一条媒体增强门控规则：

- 全局媒体增强开关开启时，插件来源并不自动启用 metadata enhancement
- 只有插件能力开关 `spider.danmaku()` 返回 `True` 时，插件来源才允许挂载 `metadata_hydrator`

目标是让“插件是否允许做媒体增强”与插件自身的弹幕能力绑定，而不是对所有插件一刀切启用。

## Goals

- 仅对 `source_kind == "plugin"` 的播放请求增加额外门控
- 使用已有插件能力开关 `spider.danmaku()`，不新增配置项
- 保持 `browse`、`emby`、`jellyfin`、`bilibili` 等非插件来源现有行为不变
- 保持全局媒体增强开关仍是第一层总开关

## Non-Goals

- 不改变插件弹幕解析逻辑本身
- 不把 `danmaku()` 能力位持久化到数据库
- 不改动 `MetadataHydrator`、provider 链或 merge 规则
- 不为插件新增单独的“媒体增强开关”

## Current Problem

当前插件播放请求在构建 `OpenPlayerRequest` 时，只要存在 `_metadata_hydrator_factory`，就会直接挂上 `metadata_hydrator`。

这意味着：

- 即使某个插件没有声明弹幕能力，仍然会启用媒体增强
- 插件来源的媒体增强启用条件和插件自身能力没有绑定
- 需求上希望“只有 `danmaku()` 为 `True` 的插件才允许开启媒体增强”，当前实现不满足

## Approach Options

### Option A: Gate in `SpiderPluginController` when building `OpenPlayerRequest`

做法：

- 在插件控制器构建播放请求时，只有 `self._danmaku_enabled` 为 `True` 才挂 `metadata_hydrator`

优点：

- 规则紧贴插件能力来源
- 改动面最小
- 只影响插件来源，不会误伤其他 source kind

缺点：

- 规则不在 `AppCoordinator` 统一入口

### Option B: Gate in `AppCoordinator._build_metadata_hydrator_factory()`

做法：

- 在 metadata factory 中对 `source_kind == "plugin"` 再判断插件能力位

优点：

- 看起来更集中

缺点：

- factory 当前拿不到插件控制器的 `_danmaku_enabled`
- 需要额外透传能力位，反而扩大改动面

### Option C: Gate in `PlayerWindow`

做法：

- 会话打开后再忽略 `metadata_hydrator`

优点：

- 表面实现简单

缺点：

- 时机过晚
- 请求对象已经构建完成，边界不干净

## Decision

采用 **Option A**。

原因：

- `spider.danmaku()` 的能力位已经在插件控制器里被解析成 `self._danmaku_enabled`
- 直接在插件请求构建处使用这个能力位，最符合职责边界
- 该规则只针对插件来源，不应该把其他 source kind 拉进同一套判定逻辑

## Design

### 1. Rule

插件来源启用媒体增强必须同时满足：

1. 全局媒体增强开关已开启
2. 插件能力开关 `spider.danmaku()` 返回 `True`

若任一条件不满足：

- 插件请求的 `metadata_hydrator` 设为 `None`
- 播放器详情页不进行插件来源的 metadata enhancement

### 2. Implementation location

唯一实现位置：

- `src/atv_player/plugins/controller.py`

具体落点：

- 构建 `OpenPlayerRequest` 的地方
- 当前已有：
  - `self._metadata_hydrator_factory`
  - `self._danmaku_enabled`

调整后逻辑应为：

- `self._metadata_hydrator_factory is not None` 且 `self._danmaku_enabled is True`
  - 才构建 `metadata_hydrator`
- 否则：
  - `metadata_hydrator = None`

### 3. Why this boundary is correct

- `AppCoordinator` 负责全局功能开关和 provider 链装配
- `SpiderPluginController` 负责“这个插件请求到底暴露哪些播放器能力”
- `danmaku()` 是插件能力声明，因此插件专属门控应落在控制器层，而不是放进全局工厂

### 4. Error handling

- `danmaku()` 为 `False` 不视为异常
- 不弹错误
- 不记为 metadata failure
- 只是正常关闭该插件请求的媒体增强能力

## Testing

新增或修改插件控制器测试，覆盖：

- `danmaku()` 返回 `True` 时，插件请求仍然挂载 `metadata_hydrator`
- `danmaku()` 返回 `False` 时，插件请求的 `metadata_hydrator is None`
- `danmaku_controller` 现有行为不变：
  - `True` 时仍可挂弹幕控制器
  - `False` 时仍为 `None`

## Risks

- 如果后续有人把“插件媒体增强能力”与“插件弹幕能力”解耦，这条规则会显得过强
- 但在当前需求里，这正是明确要求，不属于风险外溢

## Rollout

这是一个小范围行为调整，可一次性落地：

1. 修改插件请求构建逻辑
2. 补对应测试
3. 回归插件来源打开播放器相关测试
