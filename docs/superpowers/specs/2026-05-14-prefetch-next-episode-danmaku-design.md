# 预下载下一集弹幕

## 目标

切换到剧集 N 后,后台静默预取 N+1 的弹幕 XML,使用户切到下一集时无需等待网络往返,`_configure_danmaku_for_current_item` 直接命中已写好的 `PlayItem.danmaku_xml`。

## 范围

- 仅 `SpiderPluginController` (剧集/动漫主战场)。
- B 站 (随 `playerContent` 一次返回所有 episode 的 danmaku) 和 direct_parse (单源即时拉取) 不在范围内。
- 默认开启,无设置项。

## 触发条件 (两点合并,任一命中)

1. **切集时**: `_play_item_at_index` 成功后立即调度一次。
2. **接近片尾时**: `report_progress` 中,满足 `duration_seconds > 15*60` 且 `duration_seconds - position_seconds < 150`。

两点均经同一调度入口,通过 session 上的去重集合避免重复入队;实际下载由 `SpiderPluginController._maybe_resolve_danmaku` 已有的 `_pending_danmaku_item_ids` / `danmaku_pending` 双重短路保证幂等。

## 接口

### `SpiderPluginController.prefetch_next_episode_danmaku`

```python
def prefetch_next_episode_danmaku(
    self, item: PlayItem, playlist: list[PlayItem]
) -> None:
    if not _should_prefetch_danmaku(item, playlist):
        return
    url = item.url or item.vod_id
    if not url:
        return
    self._maybe_resolve_danmaku(item, url, playlist)
```

- 公开方法。守门复用现有 `_should_prefetch_danmaku` (要求 item 能解析到 episode label,过滤单片)。
- 下载逻辑完全复用 `_maybe_resolve_danmaku` (`danmaku_xml` 已存在 / `danmaku_pending` / `_pending_danmaku_item_ids` 三重短路)。
- 其它 controller 不实现此方法,调用方做能力探测。

### `PlayerController.on_item_started`

```python
def on_item_started(self, session: PlayerSession, current_index: int) -> None:
    self._schedule_next_episode_danmaku_prefetch(session, current_index)
```

由 `player_window._play_item_at_index` 在成功加载后调用一次。

### `PlayerController.report_progress` 新增参数

```python
def report_progress(
    self,
    session,
    current_index,
    position_seconds,
    speed,
    opening_seconds,
    ending_seconds,
    paused,
    force_remote_report=False,
    duration_seconds: int = 0,  # 新增,默认 0 关闭尾部预取
) -> None:
    ...
    if (
        not paused
        and duration_seconds > 15 * 60
        and duration_seconds - position_seconds < 150
    ):
        self._schedule_next_episode_danmaku_prefetch(session, current_index)
```

### 内部 `_schedule_next_episode_danmaku_prefetch`

```python
def _schedule_next_episode_danmaku_prefetch(
    self, session: PlayerSession, current_index: int
) -> None:
    next_index = current_index + 1
    if not (0 <= next_index < len(session.playlist)):
        return
    if next_index in session.prefetched_next_danmaku_indices:
        return
    controller = session.danmaku_controller
    prefetcher = getattr(controller, "prefetch_next_episode_danmaku", None)
    if not callable(prefetcher):
        return
    session.prefetched_next_danmaku_indices.add(next_index)
    try:
        prefetcher(session.playlist[next_index], session.playlist)
    except Exception:
        logger.exception(
            "Prefetch next episode danmaku failed vod_id=%s next_index=%s",
            session.vod.vod_id,
            next_index,
        )
        session.prefetched_next_danmaku_indices.discard(next_index)
```

### `PlayerSession` 新增字段

```python
prefetched_next_danmaku_indices: set[int] = field(default_factory=set)
```

仅在调度成功后写入。失败时回退,允许下次重试。

## player_window 集成

- `_play_item_at_index` 末尾,`_load_current_item` 成功后追加一行:
  ```python
  if self.controller is not None and self.session is not None:
      self.controller.on_item_started(self.session, self.current_index)
  ```
- `report_progress` 调用点 (`self.controller.report_progress(...)`,见 `player_window.py:2370`) 加传 `duration_seconds=self._current_media_duration_seconds()`。
- player_window 已持有 `self.controller`,无新增依赖注入。

## 数据流

```
切到第 N 集
   │
   ├─► player_window._play_item_at_index(N) 成功
   │       │
   │       └─► PlayerController.on_item_started
   │              │
   │              └─► _schedule_next_episode_danmaku_prefetch(session, N)
   │                     │
   │                     └─► SpiderPluginController.prefetch_next_episode_danmaku(playlist[N+1])
   │                            │
   │                            └─► _maybe_resolve_danmaku → 后台线程
   │                                   │
   │                                   └─► playlist[N+1].danmaku_xml ← XML 写回
   │
   └─► 播放进行
           │
           └─► report_progress (每个周期)
                  │
                  └─► 剩余 < 150s 且时长 > 900s
                         │
                         └─► _schedule_next_episode_danmaku_prefetch(session, N)
                                │ (N+1 已在 set 里 → 立即 return,无重复)
                                └─► 若首次失败已 discard → 重试一次

切到 N+1
   │
   └─► _configure_danmaku_for_current_item → playlist[N+1].danmaku_xml 已就绪
```

## 错误处理

- 预取下载失败: `_maybe_resolve_danmaku` 内部 `finally` 复位 `danmaku_pending=False`,日志已存在,不抛出。
- 调度环节 (调用 prefetcher 前后) 抛出: catch 并 `discard(next_index)`,允许后续 `report_progress` 周期重试。不影响当前播放。
- 没有 plugin controller (例如 direct_parse / bilibili 播放) → 能力探测 `getattr` 返回 None,静默跳过。

## 测试

### `tests/test_player_controller.py` (新建或追加)

- `on_item_started` 越界 (`current_index == len(playlist) - 1`) 时不调用 prefetcher。
- 同一 `next_index` 仅调度一次 (第二次 on_item_started / report_progress 不再调用 prefetcher)。
- prefetcher 抛异常时 `prefetched_next_danmaku_indices` 不保留该 index。
- `report_progress` 在 `duration_seconds <= 900` 时不调度。
- `report_progress` 在 `duration_seconds - position_seconds >= 150` 时不调度。
- `report_progress` 在 `paused=True` 时不调度尾部预取。
- 切到 N+1 后,`on_item_started` 调度 N+2 (`prefetched_next_danmaku_indices` 中只剩 N+1 之后写入的索引;N+2 是首次)。
- `session.danmaku_controller` 缺少 `prefetch_next_episode_danmaku` 方法时不抛错。

### `tests/test_spider_plugin_controller.py` (追加)

- `prefetch_next_episode_danmaku`: `_should_prefetch_danmaku` 返回 False 时不调用 `_maybe_resolve_danmaku`。
- 目标 item 没有 url 与 vod_id 时不调用。
- 满足条件时调用 `_maybe_resolve_danmaku(item, url, playlist)`。

## 不变更

- 弹幕 XML / ASS 缓存机制 (`danmaku/cache.py`)。
- ASS 渲染 (`danmaku/subtitle.py`)。
- B 站 / direct_parse 流程。
- `PlayItem.danmaku_xml / danmaku_pending` 语义。
- 设置/数据库结构。
