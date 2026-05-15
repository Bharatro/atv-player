# 延迟下一集弹幕预下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“开播即预下载下一集弹幕”改为“开播 30 秒后预下载”，同时保留片尾阈值触发作为兜底。

**Architecture:** 延迟调度继续放在 `PlayerController`，不把等待逻辑塞进 `SpiderPluginController`。`PlayerSession` 记录一个预下载 token，用于让旧的延迟任务在切集或停止后自动失效；真正执行预下载仍然复用现有 `_schedule_next_episode_danmaku_prefetch(...)` 和 `prefetched_next_danmaku_indices` 去重。

**Tech Stack:** Python 3.14, PySide6, pytest, 现有 `PlayerController` / `SpiderPluginController` / `player_window` 集成

---

## File Structure

- Modify: `src/atv_player/controllers/player_controller.py`
  Responsibility: 管理 30 秒延迟调度、片尾立即触发、过期任务失效、去重复用。
- Modify: `tests/test_player_controller.py`
  Responsibility: 锁定延迟调度、token 失效、片尾兜底和去重行为。
- No code changes expected: `src/atv_player/plugins/controller.py`
  Responsibility remains unchanged: 真正执行预下载。
- No code changes expected: `src/atv_player/ui/player_window.py`
  Reason: 现有 `on_item_started(...)` 和 `report_progress(...)` 调用点已经就位，不需要额外接线。

## Task 1: Add Session Token And Delay Infrastructure

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py`
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: Write the failing tests for session token and delayed scheduling**

Add these test helpers and tests to `tests/test_player_controller.py` near the existing prefetch tests:

```python
class FakeTimer:
    def __init__(self, delay_seconds: float, callback) -> None:
        self.delay_seconds = delay_seconds
        self.callback = callback
        self.started = False

    def start(self) -> None:
        self.started = True


class FakeTimerFactory:
    def __init__(self) -> None:
        self.timers: list[FakeTimer] = []

    def __call__(self, delay_seconds: float, callback):
        timer = FakeTimer(delay_seconds, callback)
        self.timers.append(timer)
        return timer


def test_on_item_started_schedules_delayed_prefetch_instead_of_running_immediately() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)

    assert danmaku_controller.calls == []
    assert len(timer_factory.timers) == 1
    assert timer_factory.timers[0].delay_seconds == 30.0
    assert timer_factory.timers[0].started is True


def test_delayed_prefetch_callback_runs_prefetch_after_timer_fires() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    timer_factory.timers[0].callback()

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[1]
    assert 1 in session.prefetched_next_danmaku_indices


def test_latest_on_item_started_invalidates_older_delayed_prefetch_callback() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    first_callback = timer_factory.timers[0].callback
    controller.on_item_started(session, current_index=1)
    second_callback = timer_factory.timers[1].callback

    first_callback()
    second_callback()

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[2]
    assert 1 not in session.prefetched_next_danmaku_indices
    assert 2 in session.prefetched_next_danmaku_indices
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "delayed_prefetch or invalidates_older" -v
```

Expected:
- FAIL because `PlayerController` has no `_prefetch_timer_factory`
- FAIL because `on_item_started(...)` still triggers prefetch immediately

- [ ] **Step 3: Implement the delay configuration in `PlayerController`**

Update `src/atv_player/controllers/player_controller.py` imports and `PlayerSession` / `PlayerController.__init__`:

```python
import threading
```

```python
@dataclass(slots=True)
class PlayerSession:
    ...
    prefetched_next_danmaku_indices: set[int] = field(default_factory=set)
    pending_next_danmaku_prefetch_token: int = 0
```

```python
class PlayerController:
    _NEXT_EPISODE_DANMAKU_PREFETCH_DELAY_SECONDS = 30.0

    def __init__(self, api_client) -> None:
        self._api_client = api_client
        self._prefetch_timer_factory = lambda delay_seconds, callback: threading.Timer(delay_seconds, callback)
```

- [ ] **Step 4: Add the delayed-scheduling helper methods**

Add these methods to `PlayerController`, immediately above `on_item_started(...)`:

```python
    def _invalidate_pending_next_episode_danmaku_prefetch(self, session: PlayerSession) -> None:
        session.pending_next_danmaku_prefetch_token += 1

    def _schedule_delayed_next_episode_danmaku_prefetch(
        self,
        session: PlayerSession,
        current_index: int,
    ) -> None:
        next_index = current_index + 1
        if not (0 <= next_index < len(session.playlist)):
            return
        if next_index in session.prefetched_next_danmaku_indices:
            return
        controller = session.danmaku_controller
        if controller is None:
            return
        prefetcher = getattr(controller, "prefetch_next_episode_danmaku", None)
        if not callable(prefetcher):
            return
        self._invalidate_pending_next_episode_danmaku_prefetch(session)
        token = session.pending_next_danmaku_prefetch_token

        def run_if_still_current() -> None:
            if token != session.pending_next_danmaku_prefetch_token:
                return
            self._schedule_next_episode_danmaku_prefetch(session, current_index)

        timer = self._prefetch_timer_factory(
            self._NEXT_EPISODE_DANMAKU_PREFETCH_DELAY_SECONDS,
            run_if_still_current,
        )
        timer.start()
```

- [ ] **Step 5: Change `on_item_started(...)` to use the delayed helper**

Replace:

```python
    def on_item_started(self, session: PlayerSession, current_index: int) -> None:
        self._schedule_next_episode_danmaku_prefetch(session, current_index)
```

With:

```python
    def on_item_started(self, session: PlayerSession, current_index: int) -> None:
        self._schedule_delayed_next_episode_danmaku_prefetch(session, current_index)
```

- [ ] **Step 6: Run the focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "delayed_prefetch or invalidates_older" -v
```

Expected:
- PASS for all three new tests

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat(player): delay next danmaku prefetch by 30 seconds"
```

## Task 2: Preserve Existing Edge-Case Guards Under Delayed Scheduling

**Files:**
- Modify: `tests/test_player_controller.py`
- Modify: `src/atv_player/controllers/player_controller.py`

- [ ] **Step 1: Replace the immediate-prefetch tests with delay-aware versions**

Update the existing tests in `tests/test_player_controller.py` so they assert delayed scheduling rather than immediate invocation:

```python
def test_on_item_started_noop_when_next_index_out_of_range() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=len(session.playlist) - 1)

    assert timer_factory.timers == []
    assert danmaku_controller.calls == []
    assert session.prefetched_next_danmaku_indices == set()


def test_on_item_started_skips_when_controller_lacks_prefetch() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory

    class NoPrefetchController:
        pass

    session, _ = _make_session_for_prefetch(controller, NoPrefetchController())

    controller.on_item_started(session, current_index=0)

    assert timer_factory.timers == []
    assert session.prefetched_next_danmaku_prefetch_token == 0
```

And add this new test:

```python
def test_delayed_prefetch_discards_index_when_prefetcher_raises() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    danmaku_controller.raise_on_call = RuntimeError("boom")
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    timer_factory.timers[0].callback()

    assert session.prefetched_next_danmaku_indices == set()
    assert len(danmaku_controller.calls) == 1
```

- [ ] **Step 2: Run the focused guard tests and verify failures**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "next_index_out_of_range or lacks_prefetch or raise" -v
```

Expected:
- some tests FAIL because assertions still assume immediate calls or token field names are missing

- [ ] **Step 3: Ensure `stop_playback(...)` invalidates old delayed callbacks**

Update `stop_playback(...)` in `src/atv_player/controllers/player_controller.py` to invalidate the token before returning or invoking the stopper:

```python
    def stop_playback(self, session: PlayerSession, current_index: int) -> None:
        self._invalidate_pending_next_episode_danmaku_prefetch(session)
        if session.playback_stopper is None:
            return
        if not (0 <= current_index < len(session.playlist)):
            return
        logger.info("Stop playback vod_id=%s index=%s", session.vod.vod_id, current_index)
        session.playback_stopper(session.playlist[current_index])
```

Add the test:

```python
def test_stop_playback_invalidates_pending_delayed_prefetch() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.stop_playback(session, current_index=0)
    timer_factory.timers[0].callback()

    assert danmaku_controller.calls == []
    assert session.prefetched_next_danmaku_indices == set()
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "next_index_out_of_range or lacks_prefetch or raise or invalidates_pending" -v
```

Expected:
- PASS for all targeted tests

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "test: cover delayed danmaku prefetch guard cases"
```

## Task 3: Keep Tail Prefetch Immediate And Compatible With Delayed Startup Prefetch

**Files:**
- Modify: `tests/test_player_controller.py`
- Modify: `src/atv_player/controllers/player_controller.py` if needed

- [ ] **Step 1: Add failing tests for tail-trigger interaction**

Append these tests to `tests/test_player_controller.py`:

```python
def test_report_progress_tail_prefetch_triggers_immediately_even_with_startup_delay() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[1]
    assert 1 in session.prefetched_next_danmaku_indices


def test_delayed_prefetch_callback_noops_after_tail_prefetch_already_succeeded() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    delayed_callback = timer_factory.timers[0].callback
    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )
    delayed_callback()

    assert len(danmaku_controller.calls) == 1
```

- [ ] **Step 2: Run the targeted tests and verify they fail if delayed callback duplicates work**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "tail_prefetch_triggers_immediately or callback_noops_after_tail" -v
```

Expected:
- FAIL if delayed callback still duplicates prefetch after tail path ran first

- [ ] **Step 3: Invalidate the startup token when tail prefetch succeeds**

Update `_schedule_next_episode_danmaku_prefetch(...)` in `src/atv_player/controllers/player_controller.py` so a successful immediate prefetch also invalidates any older delayed callback for the same session:

```python
    def _schedule_next_episode_danmaku_prefetch(
        self,
        session: PlayerSession,
        current_index: int,
    ) -> None:
        next_index = current_index + 1
        if not (0 <= next_index < len(session.playlist)):
            return
        if next_index in session.prefetched_next_danmaku_indices:
            return
        controller = session.danmaku_controller
        if controller is None:
            return
        prefetcher = getattr(controller, "prefetch_next_episode_danmaku", None)
        if not callable(prefetcher):
            return
        self._invalidate_pending_next_episode_danmaku_prefetch(session)
        session.prefetched_next_danmaku_indices.add(next_index)
        try:
            prefetcher(session.playlist[next_index], session.playlist)
        except Exception:
            session.prefetched_next_danmaku_indices.discard(next_index)
            logger.exception(
                "Prefetch next episode danmaku failed vod_id=%s next_index=%s",
                session.vod.vod_id,
                next_index,
            )
```

- [ ] **Step 4: Run the tail-prefetch tests and verify they pass**

Run:

```bash
uv run pytest tests/test_player_controller.py -k "tail_prefetch" -v
```

Expected:
- PASS for the new delay-aware tail tests
- PASS for the pre-existing tail-threshold tests

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat(player): keep tail danmaku prefetch immediate"
```

## Task 4: Full Verification

**Files:**
- Verify only: `src/atv_player/controllers/player_controller.py`
- Verify only: `tests/test_player_controller.py`
- Verify only: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Run the full player-controller suite**

Run:

```bash
uv run pytest tests/test_player_controller.py -q
```

Expected:
- all tests PASS

- [ ] **Step 2: Run the prefetch-related spider-controller suite**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "prefetch_next_episode_danmaku" -q
```

Expected:
- all prefetch tests PASS

- [ ] **Step 3: Run the combined regression command**

Run:

```bash
uv run pytest tests/test_player_controller.py tests/test_spider_plugin_controller.py -q
```

Expected:
- PASS with 0 failures

- [ ] **Step 4: Commit the final verified state**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat: delay next episode danmaku prefetch by 30 seconds"
```
