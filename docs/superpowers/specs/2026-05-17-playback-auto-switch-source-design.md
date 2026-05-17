# Playback Auto Switch Source Design

## Summary

在现有高级设置已经包含 `播放设置` tab 和播放器已支持手动“换线路”的基础上，新增一个全局播放设置项：

- `播放失败自动切换线路`

该设置默认关闭，开启后仅在“当前线路首次打开失败”时自动切换到下一条线路继续尝试；如果所有线路都失败，则保留现有失败页和手动操作入口。

同时，本轮会把 `播放设置` tab 调整到高级设置对话框的最前面，排在 `元数据` 和 `网络代理` 前面。

## Goals

- 让用户可以在应用内开启“首开失败自动切线”，减少手动点“换线路”的次数。
- 只改变“首次打开当前线路失败”的行为，不影响已经成功开播后的错误处理。
- 复用现有线路切换顺序和失败页 UI，避免引入第二套切线机制。
- 保持配置持久化行为与当前 `AppConfig -> SettingsRepository -> AdvancedSettingsDialog` 结构一致。

## Non-Goals

- 本轮不处理“已经开始播放后中途报错”的自动切线。
- 本轮不新增弹窗、toast 或后台通知。
- 本轮不改变当前手动“重试”“换线路”的交互。
- 本轮不引入复杂的线路优先级、黑名单或跨会话失败记忆。

## Scope

主要改动：

- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/ui/player_window.py`

主要验证：

- `tests/test_storage.py`
- `tests/test_main_window_ui.py`
- `tests/test_player_window_ui.py`

## Current Problem

播放器当前已经具备：

- 高级设置中的 `播放设置` tab
- 多线路播放模型
- 首开失败时的失败页
- 失败页上的手动“换线路”按钮

但仍有两个缺口：

- 用户无法把“首开失败后自动换线路”设为全局偏好。
- 首开失败虽然已有手动 fallback，但重复点击“换线路”本质上仍是机械操作。

现有代码中，线路切换顺序已经明确：

- 先尝试当前分组中的下一条线路
- 当前分组耗尽后，再切到下一个分组的第一条线路

因此这轮最合理的做法，不是重做线路模型，而是在“首开失败”分支上增加一个受配置控制的自动策略。

## Approach Options

### Option A: Only auto-switch from the failed startup screen

做法：

- 首开失败进入现有 failed startup 状态后
- 如果设置开启，立即调用现有 `_switch_line_after_failure()`

优点：

- 改动最小。
- 完全复用现有“换线路”逻辑。

缺点：

- 容易遗漏不同失败路径之间的分支差异。
- 行为依赖各类失败是否都先进入同一个 failed startup 出口。

### Option B: Unify all first-open failures behind one auto-switch decision

做法：

- 将“首次打开当前线路失败”的几个主要出口统一收口到自动切线判断
- 自动切线仍复用现有 `_switch_line_after_failure()`
- 为本次打开流程记录已经自动尝试过的线路，避免循环

优点：

- 行为一致，覆盖更完整。
- 保持现有 UI 和线路顺序不变。

缺点：

- 需要更明确地区分“首开失败”和“开播后失败”。

### Option C: Full retry state machine

做法：

- 为每次打开建立完整状态机
- 管理自动切线、自动重试、线路耗尽等全部状态

优点：

- 扩展性最好。

缺点：

- 复杂度显著超出本轮范围。

## Decision

采用 **Option B**。

原因：

- 需求边界已经明确为“首次打开当前线路失败”。
- 现有播放器已有稳定的手动切线能力，自动逻辑应该建立在它之上。
- 统一失败出口后更容易保证行为一致，也更容易写回归测试。

## Design

### 1. Playback settings tab order and field

`AdvancedSettingsDialog` 中的 `QTabWidget` 顺序调整为：

- `播放设置`
- `元数据`
- `网络代理`

`播放设置` tab 中新增一项：

- `播放失败自动切换线路`
  - 控件：`QCheckBox`
  - 默认值：关闭

该项属于全局播放偏好，不依赖单个站点、单个播放源或当前播放器窗口状态。

### 2. Persisted config field

在 `AppConfig` 中新增字段：

- `playback_auto_switch_source_on_failure: bool = False`

`SettingsRepository` 同步：

- 建表时增加对应列
- 老库迁移时补列
- `load_config()` / `save_config()` 支持完整 round-trip

兼容性规则：

- 老用户升级后默认值为关闭
- 未识别值按关闭处理

### 3. Failure boundary

“当前线路首次打开失败”定义为：

- 当前条目正在执行首次打开流程，且还没有进入成功播放状态
- 在该阶段出现以下任一失败：
  - 解析失败
  - playback loader 失败
  - playback prepare 失败
  - 没有可用播放地址
  - mpv 首次打开失败

以下情况不属于本轮自动切线范围：

- 已经成功开播后中途报错
- 用户主动停止播放
- 自然播放结束

### 4. Auto-switch behavior

当命中“首开失败”且设置开启时：

1. 判断当前 session 是否存在可切换的下一条线路。
2. 判断本次打开流程中当前线路是否已经被自动尝试过。
3. 如果存在下一条线路且尚未自动尝试过，则直接复用现有 `_switch_line_after_failure()` 切到下一条线路。
4. 如果没有下一条线路可用，则展示现有失败页并停止自动行为。

线路顺序完全复用现有实现：

- 优先切当前分组中的下一条线路
- 当前分组耗尽后切到下一个分组的第一条线路

本轮不改变任何手动切线顺序或手动操作入口。

### 5. Loop prevention and state reset

为避免自动切线陷入循环，`PlayerWindow` 需要维护“本次打开流程已自动尝试的线路状态”。

状态语义：

- 仅记录本次打开流程中自动切换过的 `(source_group_index, source_index)` 组合
- 同一条线路在同一次打开流程中最多自动尝试一次

状态重置时机：

- 用户重新打开一个 session
- 用户主动切换线路
- 用户主动重试当前条目
- 某条线路成功开播

这样可以保证：

- 自动切线不会在几条线路之间来回循环
- 用户手动操作后仍然保留完全控制权

### 6. UI and logging behavior

自动切线发生时：

- 不新增弹窗
- 仍沿用现有播放器日志体系
- 保持现有失败页 / 封面 / 播放器状态切换方式

建议追加一条简洁日志，表明自动动作已经发生，例如：

- `播放失败，自动切换线路`

当所有线路都失败时：

- 保留最后一次失败原因
- 展示现有失败页
- 继续允许用户手动点击“重试”或“换线路”

## Testing

补充以下回归覆盖：

- `tests/test_storage.py`
  - 新配置字段可正确保存、加载
  - 老值或异常值回退为关闭
- `tests/test_main_window_ui.py`
  - 高级设置 tab 顺序中 `播放设置` 位于第一项
  - 新复选框可正确读写配置
- `tests/test_player_window_ui.py`
  - 首开失败且开关开启时，自动切到下一条线路
  - 当前分组耗尽后，会继续切到下一个分组第一条线路
  - 所有线路都失败时，停留在失败页且不循环
  - 开关关闭时，保持现有手动行为
  - 已经成功开播后中途失败时，不触发自动切线

## Risks And Mitigations

- Risk: 不同失败路径对“首开失败”的判定不一致，导致某些失败不会自动切线。
  Mitigation: 将自动切线判断收口到统一的首开失败辅助逻辑中，并为主要失败路径补测试。
- Risk: 自动切线与现有手动切线共享逻辑时，可能重复记录失败或触发多次 UI 刷新。
  Mitigation: 自动行为只调用现有切线入口，不复制一套线路切换实现，并通过日志测试约束行为。
- Risk: 线路全部失败时可能反复尝试同一条线路。
  Mitigation: 显式记录本次打开流程已自动尝试的线路组合，并在成功或用户手动操作时重置。
