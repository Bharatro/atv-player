# 预下载下一集弹幕 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 切换到第 N 集后,在后台静默拉取第 N+1 集的弹幕 XML,使用户切到下一集时不再等待网络。

**Architecture:** 在 `SpiderPluginController` 暴露 `prefetch_next_episode_danmaku`,由 `PlayerController` 集中调度。两个调度点:`_play_item_at_index` 后立即调度一次;`report_progress` 在视频时长 > 15min 且剩余 < 150s 时调度一次。session 上的去重集合避免重复入队,实际下载复用 `_maybe_resolve_danmaku` 的后台线程与三重短路。

**Tech Stack:** Python 3.12, PySide6, pytest, `uv`-managed deps. 测试通过 `pytest-qt` headless,见 `tests/conftest.py`。

设计文档: `docs/superpowers/specs/2026-05-14-prefetch-next-episode-danmaku-design.md`

---

## 文件清单

- 修改 `src/atv_player/controllers/player_controller.py`:
  - `PlayerSession` 增加 `prefetched_next_danmaku_indices: set[int]` 字段。
  - `PlayerController.report_progress` 增加 `duration_seconds: int = 0` 参数,内部按阈值调度尾部预取。
  - 新增 `PlayerController.on_item_started(session, current_index)`。
  - 新增内部 `_schedule_next_episode_danmaku_prefetch(session, current_index)`。
- 修改 `src/atv_player/plugins/controller.py`:
  - `SpiderPluginController` 新增公共方法 `prefetch_next_episode_danmaku(item, playlist)`。
- 修改 `src/atv_player/ui/player_window.py`:
  - `_play_item_at_index`: 加载成功后调用 `self.controller.on_item_started(self.session, self.current_index)`。
  - `report_progress`: 调用 controller 时附带 `duration_seconds=self._current_media_duration_seconds()`。
- 测试 `tests/test_player_controller.py`: 追加 `on_item_started` / `report_progress` 预取调度行为单元测试。
- 测试 `tests/test_spider_plugin_controller.py`: 追加 `prefetch_next_episode_danmaku` 单元测试。

---

## Task 1: PlayerSession 新增 `prefetched_next_danmaku_indices` 字段

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py` (`PlayerSession` 数据类,行 24-51 附近)

- [ ] **Step 1: 给 `PlayerSession` 加字段**

在 `src/atv_player/controllers/player_controller.py` 的 `PlayerSession` 数据类中,在最后一个字段 `video_cover_override: str = ""` 之后追加:

```python
    prefetched_next_danmaku_indices: set[int] = field(default_factory=set)
```

- [ ] **Step 2: 跑现有测试确认未破坏**

```bash
uv run pytest tests/test_player_controller.py -v
```

预期: 全部通过 (新字段有默认值,不影响现有用例)。

- [ ] **Step 3: 提交**

```bash
git add src/atv_player/controllers/player_controller.py
git commit -m "feat(player): add prefetched_next_danmaku_indices to PlayerSession"
```

---

## Task 2: SpiderPluginController 暴露 `prefetch_next_episode_danmaku`

**Files:**
- Modify: `src/atv_player/plugins/controller.py` (在 `_maybe_resolve_danmaku` 附近)
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: 在测试文件末尾追加失败测试**

打开 `tests/test_spider_plugin_controller.py`,在文件末尾追加以下三个测试。注意 `SpiderPluginController` 构造参数较多,使用最小化的 stub spider 实例。先看文件已有的 fixture 模式(`FakeSpider`),复用同款 stub。

```python
def test_prefetch_next_episode_danmaku_skips_when_should_not_prefetch(tmp_path) -> None:
    spider = FakeSpider()
    controller = SpiderPluginController(
        plugin_name="test",
        plugin_key="test",
        spider=spider,
        plugin_config={},
    )
    item = PlayItem(title="电影", url="https://example.com/movie.mp4")
    # _should_prefetch_danmaku 要求能解析出 episode label;单片应当跳过
    called: list[tuple] = []
    controller._maybe_resolve_danmaku = lambda *args, **kwargs: called.append((args, kwargs))  # type: ignore[assignment]

    controller.prefetch_next_episode_danmaku(item, [item])

    assert called == []


def test_prefetch_next_episode_danmaku_skips_when_url_and_vod_id_blank(tmp_path) -> None:
    spider = FakeSpider()
    controller = SpiderPluginController(
        plugin_name="test",
        plugin_key="test",
        spider=spider,
        plugin_config={},
    )
    episode_one = PlayItem(title="第 1 集", url="https://example.com/e1.mp4")
    episode_two = PlayItem(title="第 2 集", url="", vod_id="")
    called: list[tuple] = []
    controller._maybe_resolve_danmaku = lambda *args, **kwargs: called.append((args, kwargs))  # type: ignore[assignment]

    controller.prefetch_next_episode_danmaku(episode_two, [episode_one, episode_two])

    assert called == []


def test_prefetch_next_episode_danmaku_invokes_resolver_when_eligible(tmp_path) -> None:
    spider = FakeSpider()
    controller = SpiderPluginController(
        plugin_name="test",
        plugin_key="test",
        spider=spider,
        plugin_config={},
    )
    episode_one = PlayItem(title="第 1 集", url="https://example.com/e1.mp4")
    episode_two = PlayItem(title="第 2 集", url="https://example.com/e2.mp4")
    playlist = [episode_one, episode_two]
    captured: list[tuple] = []
    controller._maybe_resolve_danmaku = lambda item, url, playlist=None: captured.append((item, url, playlist))  # type: ignore[assignment]

    controller.prefetch_next_episode_danmaku(episode_two, playlist)

    assert captured == [(episode_two, "https://example.com/e2.mp4", playlist)]
```

- [ ] **Step 2: 跑测试,确认 3 个用例全失败**

```bash
uv run pytest tests/test_spider_plugin_controller.py -k prefetch_next_episode -v
```

预期: 3 个 FAIL,原因 `AttributeError: 'SpiderPluginController' object has no attribute 'prefetch_next_episode_danmaku'`。

- [ ] **Step 3: 在 `SpiderPluginController._maybe_resolve_danmaku` 紧邻处插入公共方法**

在 `src/atv_player/plugins/controller.py` 中找到 `def _maybe_resolve_danmaku(` (大约行 1203),紧邻其上方插入:

```python
    def prefetch_next_episode_danmaku(
        self,
        item: PlayItem,
        playlist: list[PlayItem],
    ) -> None:
        if not _should_prefetch_danmaku(item, playlist):
            return
        url = (item.url or item.vod_id or "").strip()
        if not url:
            return
        self._maybe_resolve_danmaku(item, url, playlist)
```

- [ ] **Step 4: 跑测试**

```bash
uv run pytest tests/test_spider_plugin_controller.py -k prefetch_next_episode -v
```

预期: 3 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat(plugin): expose prefetch_next_episode_danmaku on SpiderPluginController"
```

---

## Task 3: PlayerController 新增 `_schedule_next_episode_danmaku_prefetch` 与 `on_item_started`

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py`
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: 写失败测试**

打开 `tests/test_player_controller.py`,在文件末尾追加:

```python
class FakeDanmakuController:
    def __init__(self) -> None:
        self.calls: list[tuple[PlayItem, list[PlayItem]]] = []
        self.raise_on_call: Exception | None = None

    def prefetch_next_episode_danmaku(self, item: PlayItem, playlist: list[PlayItem]) -> None:
        self.calls.append((item, playlist))
        if self.raise_on_call is not None:
            raise self.raise_on_call


def _make_session_for_prefetch(
    controller: PlayerController,
    danmaku_controller: object | None,
) -> "tuple[object, list[PlayItem]]":
    vod = VodItem(vod_id="series-1", vod_name="Series", vod_pic="pic")
    playlist = [
        PlayItem(title="第 1 集", url="1.mp4"),
        PlayItem(title="第 2 集", url="2.mp4"),
        PlayItem(title="第 3 集", url="3.mp4"),
    ]
    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        danmaku_controller=danmaku_controller,
    )
    return session, playlist


def test_on_item_started_schedules_prefetch_for_next_index() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, playlist = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is playlist[1]
    assert danmaku_controller.calls[0][1] is session.playlist
    assert 1 in session.prefetched_next_danmaku_indices


def test_on_item_started_noop_when_next_index_out_of_range() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=len(session.playlist) - 1)

    assert danmaku_controller.calls == []
    assert session.prefetched_next_danmaku_indices == set()


def test_on_item_started_does_not_reschedule_same_next_index() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.on_item_started(session, current_index=0)

    assert len(danmaku_controller.calls) == 1


def test_on_item_started_discards_index_when_prefetcher_raises() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    danmaku_controller.raise_on_call = RuntimeError("boom")
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)

    assert session.prefetched_next_danmaku_indices == set()
    assert len(danmaku_controller.calls) == 1


def test_on_item_started_skips_when_controller_lacks_prefetch() -> None:
    controller = PlayerController(FakeApiClient())

    class NoPrefetchController:
        pass

    session, _ = _make_session_for_prefetch(controller, NoPrefetchController())
    controller.on_item_started(session, current_index=0)
    # 没有 prefetch_next_episode_danmaku 属性,不应抛错
    assert session.prefetched_next_danmaku_indices == set()


def test_on_item_started_advances_set_when_switching_episodes() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.on_item_started(session, current_index=1)

    assert len(danmaku_controller.calls) == 2
    assert {1, 2}.issubset(session.prefetched_next_danmaku_indices)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_player_controller.py -k "on_item_started" -v
```

预期: FAIL,`PlayerController` 无 `on_item_started` 属性。

- [ ] **Step 3: 实现 `_schedule_next_episode_danmaku_prefetch` 与 `on_item_started`**

在 `src/atv_player/controllers/player_controller.py` 的 `PlayerController` 类末尾追加:

```python
    def on_item_started(self, session: PlayerSession, current_index: int) -> None:
        self._schedule_next_episode_danmaku_prefetch(session, current_index)

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

- [ ] **Step 4: 跑测试**

```bash
uv run pytest tests/test_player_controller.py -k "on_item_started" -v
```

预期: 6 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat(player): schedule next episode danmaku prefetch on item start"
```

---

## Task 4: `report_progress` 增加 `duration_seconds` 并触发尾部预取

**Files:**
- Modify: `src/atv_player/controllers/player_controller.py` (`report_progress` 方法)
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_player_controller.py` 末尾追加:

```python
def test_report_progress_tail_prefetch_triggers_when_remaining_under_150s() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,  # 18 min
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,  # 20 min, remaining = 120s
    )

    assert len(danmaku_controller.calls) == 1
    assert 1 in session.prefetched_next_danmaku_indices


def test_report_progress_tail_prefetch_skipped_when_duration_too_short() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 13,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 14,  # 14 min < 15 min
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_remaining_too_long() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 10,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,  # remaining = 600s
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_paused() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=True,
        duration_seconds=60 * 20,
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_duration_unknown() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        # duration_seconds defaults to 0
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_deduplicates_with_on_item_started() -> None:
    controller = PlayerController(FakeApiClient())
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
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
uv run pytest tests/test_player_controller.py -k "report_progress_tail_prefetch" -v
```

预期: 6 个 FAIL,`report_progress() got an unexpected keyword argument 'duration_seconds'`。

- [ ] **Step 3: 修改 `report_progress` 签名与实现**

在 `src/atv_player/controllers/player_controller.py` 中找到 `def report_progress(` (约行 296),在签名末尾的 `force_remote_report: bool = False,` 之后追加 `duration_seconds: int = 0,`。

完整新签名:

```python
    def report_progress(
        self,
        session: PlayerSession,
        current_index: int,
        position_seconds: int,
        speed: float,
        opening_seconds: int,
        ending_seconds: int,
        paused: bool,
        force_remote_report: bool = False,
        duration_seconds: int = 0,
    ) -> None:
```

然后在方法体最末尾(`self._api_client.save_history(payload)` 之后)追加:

```python
        if (
            not paused
            and duration_seconds > 15 * 60
            and (duration_seconds - position_seconds) < 150
        ):
            self._schedule_next_episode_danmaku_prefetch(session, current_index)
```

- [ ] **Step 4: 跑新测试**

```bash
uv run pytest tests/test_player_controller.py -k "report_progress_tail_prefetch" -v
```

预期: 6 个 PASS。

- [ ] **Step 5: 跑全部 player_controller 测试**

```bash
uv run pytest tests/test_player_controller.py -v
```

预期: 全部 PASS,无 regression。

- [ ] **Step 6: 提交**

```bash
git add src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat(player): trigger tail danmaku prefetch from report_progress"
```

---

## Task 5: player_window 集成调用点

**Files:**
- Modify: `src/atv_player/ui/player_window.py` (`_play_item_at_index` 与 `report_progress` 方法)

注意: 此任务无新增测试,因为 player_window 的相关分支已被 `tests/test_player_window_ui.py` (pytest-qt) 间接覆盖;我们只需保证现有 UI 测试不退化。

- [ ] **Step 1: 在 `_play_item_at_index` 末尾通知 controller**

打开 `src/atv_player/ui/player_window.py`,定位 `_play_item_at_index` (约行 1635)。当前末尾 try 块结构如下:

```python
        try:
            self.playlist.setCurrentRow(self.current_index)
            self._refresh_danmaku_source_entry_points()
            self._render_metadata()
            self._render_detail_fields()
            self._render_detail_actions()
            self._load_current_item(
                start_position_seconds=start_position_seconds,
                pause=pause,
                previous_index=previous_index,
                preserve_primary_external_subtitle_selection=preserve_primary_external_subtitle_selection,
            )
            self._refresh_window_title()
        except Exception:
            self._restore_or_keep_current_index_after_failure(previous_index)
            raise
```

在 `self._refresh_window_title()` 之后、`except Exception:` 之前追加:

```python
            if self.session is not None:
                self.controller.on_item_started(self.session, self.current_index)
```

- [ ] **Step 2: 在 `report_progress` 调用 controller 时传递 duration**

定位 `report_progress` (约行 2351),其内部 `report()` 闭包调用 `self.controller.report_progress(...)` (约行 2370-2379)。给该调用追加 `duration_seconds` 关键字参数。

修改前:

```python
            def report() -> None:
                self.controller.report_progress(
                    session,
                    current_index=current_index,
                    position_seconds=position_seconds,
                    speed=speed,
                    opening_seconds=opening_seconds,
                    ending_seconds=ending_seconds,
                    paused=paused,
                    force_remote_report=force_remote_report,
                )
```

在闭包之上、`def report() -> None:` 之前 (与其它已捕获的局部变量同级) 新增:

```python
            duration_seconds = self._current_media_duration_seconds()
```

然后将 `force_remote_report=force_remote_report,` 行改为下面两行:

```python
                    force_remote_report=force_remote_report,
                    duration_seconds=duration_seconds,
```

最终该闭包应为:

```python
            duration_seconds = self._current_media_duration_seconds()

            def report() -> None:
                self.controller.report_progress(
                    session,
                    current_index=current_index,
                    position_seconds=position_seconds,
                    speed=speed,
                    opening_seconds=opening_seconds,
                    ending_seconds=ending_seconds,
                    paused=paused,
                    force_remote_report=force_remote_report,
                    duration_seconds=duration_seconds,
                )
```

- [ ] **Step 3: 跑 UI 测试**

```bash
uv run pytest tests/test_player_window_ui.py -v
```

预期: 全部通过。

- [ ] **Step 4: 跑全套测试**

```bash
uv run pytest
```

预期: 全部通过。

- [ ] **Step 5: lint**

```bash
uv run ruff check src/atv_player/controllers/player_controller.py src/atv_player/plugins/controller.py src/atv_player/ui/player_window.py tests/test_player_controller.py tests/test_spider_plugin_controller.py
```

预期: 无 error。

- [ ] **Step 6: 提交**

```bash
git add src/atv_player/ui/player_window.py
git commit -m "feat(player-window): wire next episode danmaku prefetch hooks"
```

---

## 验证清单 (人工)

- [ ] 启动 `./start.sh`,进入一个含弹幕的连续剧 (插件源)。
- [ ] 观看第 1 集,看 log 是否出现弹幕加载,然后切到第 2 集 — 应当瞬间出现弹幕,无 "弹幕加载中" 等待。
- [ ] 重新进入第 1 集,快进至接近片尾 (剩余 <150s),日志/缓存目录 `~/.cache/atv-player/danmaku/` 应有第 3 集的 xml 落盘。
- [ ] 切到剧场版/单片 (无 episode label) 时,确认不发起预取(可临时打开 logging.DEBUG 看)。
- [ ] B 站 / direct_parse 来源播放正常,无 AttributeError。

---

## 自检结果

- Spec 覆盖: §范围 → Task 2;§触发条件 → Task 3 + Task 4;§接口/PlayerSession → Task 1;§接口/on_item_started + _schedule → Task 3;§接口/report_progress 新增参数 → Task 4;§player_window 集成 → Task 5;§错误处理 → Task 3 测试 `discards_index_when_prefetcher_raises`、Task 3 测试 `skips_when_controller_lacks_prefetch`;§测试 → Task 2 / Task 3 / Task 4。
- 占位符扫描: 无。
- 类型一致性: `prefetched_next_danmaku_indices` / `on_item_started` / `_schedule_next_episode_danmaku_prefetch` / `prefetch_next_episode_danmaku` 全局一致。
