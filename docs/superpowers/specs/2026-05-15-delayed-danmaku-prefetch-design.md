# 延迟下一集弹幕预下载

## 概要

保留现有“下一集弹幕预下载”能力，但将“开播后立即预下载”改为“当前集开始播放 10 秒后再预下载”。接近片尾时的预下载保持立即触发，继续作为兜底与补偿路径。

这次调整只改变调度时机，不改变弹幕搜索、解析、缓存、排序、日志文案和 `SpiderPluginController` 的预下载执行语义。

## 目标

- 避免一开播就立刻触发下一集弹幕请求。
- 默认在当前集开播 10 秒后调度下一集预下载。
- 保留片尾阈值触发逻辑：
  - `duration_seconds > 15 * 60`
  - `duration_seconds - position_seconds < 150`
- 保证同一“下一集”仍然最多预下载一次。
- 如果用户在 10 秒内切集、停止播放或切换 session，旧延迟任务不能误触发到新的播放上下文。

## 非目标

- 不新增设置项。
- 不修改 `SpiderPluginController.prefetch_next_episode_danmaku(...)` 的缓存命中、后台线程和日志规则。
- 不调整片尾预下载阈值。
- 不为 B 站、direct_parse 或其他非 `SpiderPluginController` 控制器单独定制逻辑。

## 当前问题

当前 `PlayerController.on_item_started(...)` 会在当前集开始播放时立即调用 `_schedule_next_episode_danmaku_prefetch(...)`。这会导致：

- 当前集刚开始时就发出下一集弹幕请求。
- 触发过早，容易和当前集刚开始的弹幕搜索/下载日志交织。
- 当下一集存在异常源时，过早的后台请求会制造不必要的日志噪音。

片尾预下载本身没有问题，应该保留。

## 设计

### 调度职责保持在 `PlayerController`

延迟属于“何时触发”的问题，不属于弹幕控制器内部执行语义，因此继续由 `PlayerController` 负责调度，`SpiderPluginController` 只负责真正执行预下载。

这样可以保持职责边界清晰：

- `PlayerController`
  - 负责判断现在是否应该预下载
  - 负责 10 秒延迟
  - 负责片尾立即触发
  - 负责让过期任务失效
- `SpiderPluginController`
  - 负责预下载守门
  - 负责缓存命中
  - 负责后台解析线程

### 开播触发改为 10 秒延迟

`PlayerController.on_item_started(session, current_index)` 不再直接预下载，而是改为：

1. 计算 `next_index = current_index + 1`
2. 先做和现在一致的边界检查与能力探测
3. 为这次开播生成一个“延迟任务令牌”
4. 安排一个 10 秒后的回调
5. 回调真正执行时，再次确认：
   - 这个 session 仍然有效
   - 这次回调对应的令牌仍然是最新令牌
   - 目标 `next_index` 尚未被预下载过
6. 确认无误后，再调用现有 `_schedule_next_episode_danmaku_prefetch(...)`

### 片尾触发保持立即执行

`report_progress(...)` 中现有片尾条件保持不变。一旦命中，仍然直接调用 `_schedule_next_episode_danmaku_prefetch(...)`，不再额外等待 10 秒。

这有两个作用：

- 如果开播 10 秒后的延迟任务已经成功执行，片尾路径会被 `prefetched_next_danmaku_indices` 去重，立即返回。
- 如果延迟任务因为切集、停止、异常或未到时机而没有执行，片尾路径仍然能补上这次预下载。

### 过期延迟任务失效机制

为了避免 10 秒后的旧任务误触发到新的播放状态，需要在 `PlayerSession` 上增加一个轻量级版本号或令牌字段，例如：

- `pending_next_danmaku_prefetch_token: int = 0`

行为如下：

- 每次 `on_item_started(...)` 调度新的 10 秒任务时，先把 token 自增。
- 延迟回调捕获创建时的 token。
- 回调触发时，只有当捕获 token 仍然等于 session 当前 token 时，才允许继续执行。
- `stop_playback(...)` 或显式 session 结束路径中，也要让 token 失效，避免停止播放后 10 秒任务仍然触发。

这不是取消定时器本身，而是让旧任务即使被唤醒也变成 no-op。这样实现简单，也更适合当前代码结构。

### 去重逻辑保持现有集合

现有 `PlayerSession.prefetched_next_danmaku_indices` 继续作为“这一集的下一集是否已经预下载过”的最终去重机制，不新增第二套去重缓存。

调度层区分两件事：

- token 负责“这次延迟任务是否已经过期”
- `prefetched_next_danmaku_indices` 负责“这一目标 index 是否已经成功进入预下载流程”

## 数据流

### 开播后 10 秒路径

```text
当前集开始播放
  -> PlayerController.on_item_started(session, current_index)
  -> 生成新的 prefetch token
  -> 安排 10 秒后的延迟任务

10 秒后
  -> 检查 token 是否仍然有效
  -> 检查 next_index 是否有效且未预下载
  -> _schedule_next_episode_danmaku_prefetch(session, current_index)
  -> SpiderPluginController.prefetch_next_episode_danmaku(...)
```

### 接近片尾路径

```text
report_progress(...)
  -> 命中片尾阈值
  -> _schedule_next_episode_danmaku_prefetch(session, current_index)
  -> 若已预下载过则立即 return
  -> 若尚未预下载则立即执行
```

## 错误处理

- 如果延迟回调执行时 session 已经切到新状态，token 不匹配，直接 return。
- 如果目标 index 越界，直接 return。
- 如果 controller 不支持 `prefetch_next_episode_danmaku(...)`，直接 return。
- 如果真正执行预下载时抛异常，保持现有行为：
  - 记录日志
  - 从 `prefetched_next_danmaku_indices` 中回退该 index
  - 不影响当前播放

## 测试

### `tests/test_player_controller.py`

- `on_item_started(...)` 不再立即调用 prefetcher。
- `on_item_started(...)` 会登记一个 10 秒延迟任务。
- 延迟任务触发后才真正调用 prefetcher。
- 在延迟触发前再次 `on_item_started(...)`，旧任务必须失效，只允许最新任务生效。
- `stop_playback(...)` 或等效失效路径后，已登记的延迟任务触发时必须是 no-op。
- `report_progress(...)` 命中片尾阈值时仍然立即调用 prefetcher，不等待 10 秒。
- 如果片尾路径已经先成功预下载，之后延迟任务触发时不得重复调用。

### `tests/test_spider_plugin_controller.py`

- 现有 `prefetch_next_episode_danmaku(...)` 行为测试保持通过，不需要改变契约。

## 兼容性与范围控制

- 只影响下一集弹幕预下载时机。
- 不改变用户手动切换弹幕源的路径。
- 不改变当前集弹幕搜索/下载的触发时机。
- 不改变缓存 key、缓存内容和解析逻辑。

## 结果预期

- 开播后日志中不再立刻出现下一集的“弹幕预下载中”。
- 当前集播放约 10 秒后，才出现下一集预下载日志。
- 如果用户很快切到下一集，旧集安排的延迟任务不会污染新的播放状态。
- 接近片尾时仍能兜底预下载，避免因为延迟任务未执行而丢失下一集热缓存。
