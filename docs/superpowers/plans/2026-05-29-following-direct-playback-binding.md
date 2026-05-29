# Following Direct Playback Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let following detail entries open the last valid playback source directly, while playback history continues to restore episode, line, and position.

**Architecture:** Store only the last valid `source_kind` / `source_key` / `vod_id` in existing following source bindings. Let `FollowingController` own the progress guard: a switched source cannot replace the binding until its current episode reaches the existing following progress. `MainWindow` routes direct playback requests through existing source controllers so current playback history hooks keep working.

**Tech Stack:** Python, PySide6, pytest, existing `FollowingController`, `FollowingRepository`, `FollowingDetailPage`, `MainWindow`, `OpenPlayerRequest`.

---

## File Structure

- Modify `src/atv_player/following_repository.py`
  - Add a focused method that updates `source_bindings_json` and advances `latest_episode` without changing playback-position fields.
- Modify `src/atv_player/controllers/following_controller.py`
  - Add `record_playback_source(...)` for guarded binding updates and playback-source latest episode advancement.
- Modify `src/atv_player/ui/main_window.py`
  - Call `record_playback_source(...)` from the existing player following progress reporter.
  - Add `open_following_bound_source(...)` to route a following record's first binding to existing source controllers.
  - Connect a new following-detail signal.
- Modify `src/atv_player/ui/following_detail_page.py`
  - Add a `continue_play_requested` signal and “继续播放” button.
  - Enable it only when the current record has a usable source binding.
- Modify tests:
  - `tests/test_following_controller.py`
  - `tests/test_main_window_ui.py`
  - `tests/test_following_detail_page_ui.py`

---

### Task 1: Controller And Repository Binding State

**Files:**
- Modify: `src/atv_player/following_repository.py`
- Modify: `src/atv_player/controllers/following_controller.py`
- Test: `tests/test_following_controller.py`

- [ ] **Step 1: Write failing controller tests**

Append these tests to `tests/test_following_controller.py` and add `FollowingSourceBinding` to the existing `from atv_player.following_models import (...)` import.

```python
def test_following_controller_updates_recent_playback_binding_when_progress_reaches_current(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), now=lambda: 500)
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="player",
            provider_id="browse::vod-1",
            source_bindings=[
                FollowingSourceBinding(source_kind="browse", source_key="", vod_id="vod-1")
            ],
            current_season_number=1,
            current_episode=20,
            latest_episode=20,
        )
    )

    controller.record_playback_source(
        record_id,
        source_kind="telegram",
        source_key="",
        vod_id="tg-vod-1",
        current_season_number=1,
        current_episode=20,
        playlist_latest_episode=24,
    )

    loaded = repo.get(record_id)
    assert loaded is not None
    assert [(b.source_kind, b.source_key, b.vod_id) for b in loaded.source_bindings[:2]] == [
        ("telegram", "", "tg-vod-1"),
        ("browse", "", "vod-1"),
    ]
    assert loaded.latest_episode == 24
    assert loaded.has_update is True
    assert loaded.new_episode_count == 4


def test_following_controller_keeps_binding_when_switched_source_is_behind_current_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), now=lambda: 500)
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="player",
            provider_id="browse::vod-1",
            source_bindings=[
                FollowingSourceBinding(source_kind="browse", source_key="", vod_id="vod-1")
            ],
            current_season_number=1,
            current_episode=20,
            latest_episode=20,
        )
    )

    controller.record_playback_source(
        record_id,
        source_kind="telegram",
        source_key="",
        vod_id="tg-vod-1",
        current_season_number=1,
        current_episode=1,
        playlist_latest_episode=24,
    )

    loaded = repo.get(record_id)
    assert loaded is not None
    assert [(b.source_kind, b.source_key, b.vod_id) for b in loaded.source_bindings] == [
        ("browse", "", "vod-1")
    ]
    assert loaded.latest_episode == 24
    assert loaded.has_update is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_following_controller.py -k "playback_binding or switched_source" -v`

Expected: FAIL with `AttributeError: 'FollowingController' object has no attribute 'record_playback_source'`.

- [ ] **Step 3: Add repository update method**

In `src/atv_player/following_repository.py`, add this method near `update_progress(...)`:

```python
    def update_playback_source_state(
        self,
        following_id: int,
        *,
        source_bindings: list[FollowingSourceBinding],
        latest_episode: int,
        updated_at: int,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT latest_episode, current_episode FROM following WHERE id = ?",
                (following_id,),
            ).fetchone()
            if row is None:
                return
            previous_latest = int(row[0] or 0)
            current_episode = int(row[1] or 0)
            normalized_latest = max(previous_latest, int(latest_episode or 0))
            latest_advanced = normalized_latest > previous_latest
            has_update = normalized_latest > current_episode
            new_episode_count = max(0, normalized_latest - current_episode)
            conn.execute(
                """
                UPDATE following
                SET source_bindings_json = ?, latest_episode = ?,
                    has_update = CASE WHEN ? THEN 1 ELSE has_update END,
                    new_episode_count = CASE WHEN ? THEN ? ELSE new_episode_count END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    _json_dumps([_binding_to_dict(binding) for binding in source_bindings]),
                    normalized_latest,
                    1 if has_update else 0,
                    1 if latest_advanced else 0,
                    new_episode_count,
                    updated_at,
                    following_id,
                ),
            )
```

- [ ] **Step 4: Add controller method**

In `src/atv_player/controllers/following_controller.py`, add this public method near `record_playback_progress(...)`:

```python
    def record_playback_source(
        self,
        following_id: int,
        *,
        source_kind: str,
        source_key: str = "",
        vod_id: str,
        current_season_number: int,
        current_episode: int,
        playlist_latest_episode: int = 0,
    ) -> None:
        record = self._repository.get(following_id)
        if record is None:
            return
        normalized_kind = str(source_kind or "").strip()
        normalized_key = str(source_key or "").strip()
        normalized_vod_id = str(vod_id or "").strip()
        if not normalized_kind or not normalized_vod_id:
            return
        can_update_binding = compare_progress(
            current_season_number,
            current_episode,
            record.current_season_number,
            record.current_episode,
            current_fallback_season=record.season_number,
            target_fallback_season=record.season_number,
        ) >= 0
        bindings = list(record.source_bindings or [])
        if can_update_binding:
            new_binding = FollowingSourceBinding(
                source_kind=normalized_kind,
                source_key=normalized_key,
                vod_id=normalized_vod_id,
            )
            bindings = [
                binding
                for binding in bindings
                if not (
                    binding.source_kind == new_binding.source_kind
                    and binding.source_key == new_binding.source_key
                    and binding.vod_id == new_binding.vod_id
                )
            ]
            bindings.insert(0, new_binding)
        self._repository.update_playback_source_state(
            following_id,
            source_bindings=bindings,
            latest_episode=max(record.latest_episode, int(playlist_latest_episode or 0)),
            updated_at=self._now(),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_following_controller.py -k "playback_binding or switched_source" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/following_repository.py src/atv_player/controllers/following_controller.py tests/test_following_controller.py
git commit -m "feat: track following playback source binding"
```

---

### Task 2: Main Window Progress Reporter Sync

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing main-window progress test**

Append this test near `test_main_window_reports_following_progress_only_after_threshold` in `tests/test_main_window_ui.py`:

```python
def test_main_window_reports_following_playback_source_after_threshold(qtbot) -> None:
    class SourceTrackingFollowingController(FakeFollowingController):
        def __init__(self) -> None:
            super().__init__()
            self.source_calls: list[dict[str, object]] = []

        def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
            return [
                SimpleNamespace(
                    record=FollowingRecord(
                        id=7,
                        title="凡人修仙传",
                        provider="player",
                        provider_id="telegram::tg-vod-1",
                        current_season_number=1,
                        current_episode=20,
                        season_number=1,
                    )
                )
            ], 1

        def record_playback_progress(self, following_id: int, **kwargs) -> None:
            del following_id, kwargs

        def record_playback_source(self, following_id: int, **kwargs) -> None:
            self.source_calls.append({"following_id": following_id, **kwargs})

    following = SourceTrackingFollowingController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        following_controller=following,
    )
    qtbot.addWidget(window)

    playlist = [PlayItem(title=f"第{i}集", url=f"https://media.example/{i}.m3u8", vod_id="tg-vod-1") for i in range(1, 25)]
    item = playlist[19]
    window.player_window = SimpleNamespace(
        session=PlayerSession(
            vod=VodItem(vod_id="tg-vod-1", vod_name="凡人修仙传"),
            playlist=playlist,
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
            source_kind="telegram",
            source_key="",
        ),
        current_index=19,
    )

    window._report_player_item_following_progress(item, position_seconds=20, duration_seconds=100)

    assert following.source_calls == [
        {
            "following_id": 7,
            "source_kind": "telegram",
            "source_key": "",
            "vod_id": "tg-vod-1",
            "current_season_number": 1,
            "current_episode": 20,
            "playlist_latest_episode": 24,
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main_window_ui.py -k "following_playback_source_after_threshold" -v`

Expected: FAIL because `record_playback_source` is not called.

- [ ] **Step 3: Update reporter implementation**

In `src/atv_player/ui/main_window.py`, inside `_report_player_item_following_progress(...)`, after `record_playback_progress(...)`, add:

```python
        if hasattr(self._following_controller, "record_playback_source"):
            playlist = list(getattr(self.player_window.session, "playlist", []) or [])
            playlist_latest_episode = len(playlist) if len(playlist) > 1 else decision.episode_number
            self._following_controller.record_playback_source(
                record.id,
                source_kind=str(getattr(self.player_window.session, "source_kind", "") or "browse"),
                source_key=str(getattr(self.player_window.session, "source_key", "") or ""),
                vod_id=str(getattr(self.player_window.session.vod, "vod_id", "") or getattr(item, "vod_id", "") or ""),
                current_season_number=decision.season_number,
                current_episode=decision.episode_number,
                playlist_latest_episode=playlist_latest_episode,
            )
```

Keep this call behind the same `threshold_reached` guard as progress updates.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "following_progress_only_after_threshold or following_playback_source_after_threshold" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: sync following binding from player progress"
```

---

### Task 3: Following Detail Continue Button

**Files:**
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write failing detail-page UI test**

Add `FollowingSourceBinding` to the test import from `atv_player.following_models`, then append:

```python
def test_following_detail_page_emits_continue_play_and_keeps_search_play(qtbot) -> None:
    class BoundSourceController(FakeController):
        def load_detail(self, following_id: int, *, refresh_if_empty: bool = True, include_ai_summary: bool = True):
            view = super().load_detail(following_id, refresh_if_empty=refresh_if_empty)
            view.record.source_bindings = [
                FollowingSourceBinding(source_kind="telegram", source_key="", vod_id="tg-vod-1")
            ]
            return view

    controller = BoundSourceController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    continued: list[int] = []
    searched: list[int] = []
    page.continue_play_requested.connect(continued.append)
    page.search_play_requested.connect(searched.append)

    page.load_record(1)
    page.continue_play_button.click()
    page.search_play_button.click()

    assert page.continue_play_button.isEnabled() is True
    assert continued == [1]
    assert searched == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "continue_play_and_keeps_search_play" -v`

Expected: FAIL because `FollowingDetailPage` has no `continue_play_requested` signal or `continue_play_button`.

- [ ] **Step 3: Add signal, button, and state**

In `src/atv_player/ui/following_detail_page.py`:

```python
    continue_play_requested = Signal(int)
```

Create the button near `search_play_button`:

```python
        self.continue_play_button = QPushButton("继续播放")
```

Add it to the action row before `search_play_button`:

```python
        action_row.addWidget(self.continue_play_button)
        action_row.addWidget(self.search_play_button)
```

Connect it:

```python
        self.continue_play_button.clicked.connect(self._emit_continue_play)
```

Add helper:

```python
    def _emit_continue_play(self) -> None:
        self.continue_play_requested.emit(self.current_following_id)
```

In `_render(...)`, set the state:

```python
        has_binding = any(
            str(getattr(binding, "source_kind", "") or "").strip()
            and str(getattr(binding, "vod_id", "") or "").strip()
            for binding in list(record.source_bindings or [])
        )
        self.continue_play_button.setEnabled(has_binding)
        self.continue_play_button.setToolTip("从上次播放源继续" if has_binding else "暂无已绑定播放源，请先搜索播放")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_following_detail_page_ui.py -k "continue_play_and_keeps_search_play or reference_layout" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/following_detail_page.py tests/test_following_detail_page_ui.py
git commit -m "feat: add following continue playback action"
```

---

### Task 4: Main Window Direct Playback Routing

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing routing tests**

Add `FollowingSourceBinding` to the existing import from `atv_player.following_models`, then append:

```python
def test_main_window_routes_following_bound_telegram_source(qtbot, monkeypatch) -> None:
    class BoundFollowingController(FakeFollowingController):
        def load_detail(self, following_id: int):
            return FollowingDetailView(
                record=FollowingRecord(
                    id=following_id,
                    title="凡人修仙传",
                    source_bindings=[FollowingSourceBinding(source_kind="telegram", source_key="", vod_id="tg-vod-1")],
                ),
                snapshot=FollowingDetailSnapshot(following_id=following_id),
            )

    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        following_controller=BoundFollowingController(),
    )
    qtbot.addWidget(window)
    opened: list[OpenPlayerRequest] = []
    window.telegram_controller = SimpleNamespace(
        build_request=lambda vod_id: OpenPlayerRequest(
            vod=VodItem(vod_id=vod_id, vod_name="凡人修仙传"),
            playlist=[PlayItem(title="第20集", url="https://media.example/20.m3u8")],
            clicked_index=0,
            source_kind="telegram",
            source_key="",
            playback_history_loader=lambda: HistoryRecord(
                id=0,
                key=vod_id,
                vod_name="凡人修仙传",
                vod_pic="",
                vod_remarks="第20集",
                episode=19,
                episode_url="https://media.example/20.m3u8",
                position=120000,
                opening=0,
                ending=0,
                speed=1.0,
                create_time=1,
                source_kind="telegram",
            ),
        )
    )
    monkeypatch.setattr(window, "_start_open_request", lambda builder: opened.append(builder()))

    window.open_following_bound_source(1)

    assert opened
    assert opened[0].vod.vod_id == "tg-vod-1"
    assert opened[0].playback_history_loader is not None


def test_main_window_shows_error_when_following_has_no_bound_source(qtbot, monkeypatch) -> None:
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        following_controller=FakeFollowingController(),
    )
    qtbot.addWidget(window)
    errors: list[str] = []
    monkeypatch.setattr(window, "show_error", errors.append)

    window.open_following_bound_source(1)

    assert errors == ["暂无已绑定播放源，请先搜索播放"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window_ui.py -k "following_bound_telegram_source or following_has_no_bound_source" -v`

Expected: FAIL because `MainWindow` has no `open_following_bound_source`.

- [ ] **Step 3: Connect detail signal**

In `src/atv_player/ui/main_window.py`, next to the existing following detail connections:

```python
        self.following_detail_page.continue_play_requested.connect(self.open_following_bound_source)
```

- [ ] **Step 4: Add routing helpers**

Add these methods near `search_play_for_following(...)`:

```python
    def open_following_bound_source(self, following_id: int) -> None:
        view = self._following_controller.load_detail(int(following_id))
        binding = self._first_playable_following_binding(view.record)
        if binding is None:
            self.show_error("暂无已绑定播放源，请先搜索播放")
            return
        self._following_controller.clear_homepage_prompt(int(following_id))
        self._close_following_prompt_dialog(already_handled=True)
        self._start_open_request(lambda: self._build_following_bound_source_request(binding))

    def _first_playable_following_binding(self, record):
        for binding in list(getattr(record, "source_bindings", []) or []):
            source_kind = str(getattr(binding, "source_kind", "") or "").strip()
            vod_id = str(getattr(binding, "vod_id", "") or "").strip()
            if source_kind and vod_id:
                return binding
        return None

    def _build_following_bound_source_request(self, binding):
        source_kind = str(getattr(binding, "source_kind", "") or "").strip()
        source_key = str(getattr(binding, "source_key", "") or "").strip()
        vod_id = str(getattr(binding, "vod_id", "") or "").strip()
        if source_kind == "browse":
            return self.browse_controller.build_request_from_detail(vod_id)
        if source_kind in {"plugin", "spider_plugin"}:
            controller = self._plugin_controller_by_id(source_key)
            if controller is None:
                raise RuntimeError("已绑定插件不可用")
            request = controller.build_request(vod_id)
            request.source_kind = "plugin"
            request.source_key = source_key
            return request
        controller_map = {
            "telegram": self.telegram_controller,
            "bilibili": self.bilibili_controller,
            "youtube": self.youtube_controller,
            "emby": self.emby_controller,
            "jellyfin": self.jellyfin_controller,
            "feiniu": self.feiniu_controller,
        }
        controller = controller_map.get(source_kind)
        if controller is None:
            raise RuntimeError("已绑定播放源不可用")
        return self._apply_request_playback_history_title(controller.build_request(vod_id))
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_main_window_ui.py -k "following_bound_telegram_source or following_has_no_bound_source" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: route following continue playback"
```

---

### Task 5: Focused Regression Run

**Files:**
- No planned code changes.

- [ ] **Step 1: Run focused suite**

Run:

```bash
uv run pytest tests/test_following_controller.py tests/test_following_detail_page_ui.py tests/test_main_window_ui.py -k "following or playback_source or continue_play or bound_source" -v
```

Expected: PASS.

- [ ] **Step 2: Run repository/model regressions**

Run:

```bash
uv run pytest tests/test_following_repository.py tests/test_following_models.py tests/test_following_progress.py -v
```

Expected: PASS.

- [ ] **Step 3: Review diff**

Run: `git diff --stat HEAD~4..HEAD`

Expected: only the planned following/controller/UI/test files plus plan/spec docs.

- [ ] **Step 4: Confirm no uncommitted verification fixes remain**

Run: `git status --short`

Expected: no modified source or test files.
