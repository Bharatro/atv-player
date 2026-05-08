# Player Detail Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified player-detail action system that renders source-provided action buttons in the player sidebar and supports initial state plus refreshed state after execution for Python spider plugins and the built-in Bilibili controller.

**Architecture:** Introduce a shared `PlaybackDetailAction` model that lives on `PlayItem` and flows through `OpenPlayerRequest` and `PlayerSession`. Python spider plugins and the Bilibili controller each adapt their own playback-detail payloads into this model and expose a shared `detail_action_runner`, while `PlayerWindow` renders and executes actions through a single sidebar action area backed by the existing controller task queue.

**Tech Stack:** Python 3, PySide6, pytest, existing controller/session/request models, existing player sidebar UI

---

## File Map

- `src/atv_player/models.py`
  Responsibility: shared playback-detail action dataclass plus `PlayItem` and `OpenPlayerRequest` fields.
- `src/atv_player/controllers/player_controller.py`
  Responsibility: carry `detail_action_runner` from `OpenPlayerRequest` into `PlayerSession`.
- `src/atv_player/plugins/controller.py`
  Responsibility: normalize spider `playerContent().actions`, expose a spider action runner, and clear stale action state during playback resolution.
- `src/atv_player/controllers/bilibili_controller.py`
  Responsibility: normalize Bilibili playback actions and expose a Bilibili action runner through `build_request()`.
- `src/atv_player/api.py`
  Responsibility: declare one narrow Bilibili detail-action request method used by the controller adapter.
- `src/atv_player/ui/player_window.py`
  Responsibility: render the shared action area, execute actions in the background queue, refresh current-item action state, and discard stale action completions.
- `tests/test_player_controller.py`
  Responsibility: verify the new session callback wiring.
- `tests/test_spider_plugin_controller.py`
  Responsibility: verify spider action normalization and action execution refresh behavior.
- `tests/test_bilibili_controller.py`
  Responsibility: verify Bilibili action normalization, request wiring, and runner behavior.
- `tests/test_player_window_ui.py`
  Responsibility: verify sidebar action rendering, execution, refresh, and failure handling.

### Task 1: Shared Playback Detail Action Model

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: Write the failing model/session wiring tests**

Add these tests near the existing `create_session()` coverage in `tests/test_player_controller.py`:

```python
from atv_player.models import PlaybackDetailAction


def test_player_controller_create_session_defaults_detail_action_runner_to_none() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=0)

    assert session.detail_action_runner is None


def test_player_controller_create_session_preserves_detail_action_runner() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    def detail_action_runner(item: PlayItem, action_id: str) -> list[PlaybackDetailAction]:
        return [PlaybackDetailAction(id=action_id, label="已执行")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        detail_action_runner=detail_action_runner,
    )

    assert session.detail_action_runner is detail_action_runner
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_create_session_defaults_detail_action_runner_to_none tests/test_player_controller.py::test_player_controller_create_session_preserves_detail_action_runner -v`

Expected: FAIL with errors that `PlaybackDetailAction` or `detail_action_runner` is missing.

- [ ] **Step 3: Write the minimal shared model and session plumbing**

Update `src/atv_player/models.py` to add the shared action model and fields:

```python
@dataclass(slots=True)
class PlaybackDetailAction:
    id: str
    label: str
    active: bool = False
    enabled: bool = True
    visible: bool = True
    tooltip: str = ""


@dataclass(slots=True)
class PlayItem:
    title: str
    url: str
    original_url: str = ""
    video_cover_override: str = ""
    path: str = ""
    index: int = 0
    size: int = 0
    duration_seconds: int = 0
    vod_id: str = ""
    detail_actions: list["PlaybackDetailAction"] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    external_subtitles: list[ExternalSubtitleOption] = field(default_factory=list)
    playback_qualities: list["VideoQualityOption"] = field(default_factory=list)


@dataclass(slots=True)
class OpenPlayerRequest:
    vod: VodItem
    playlist: list[PlayItem]
    clicked_index: int
    playlists: list[list[PlayItem]] = field(default_factory=list)
    playlist_index: int = 0
    source_kind: str = "browse"
    source_key: str = ""
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None
```

Update `src/atv_player/controllers/player_controller.py` to carry the callback:

```python
@dataclass(slots=True)
class PlayerSession:
    vod: VodItem
    playlist: list[PlayItem]
    start_index: int
    start_position_seconds: int
    speed: float
    playlists: list[list[PlayItem]] = field(default_factory=list)
    playlist_index: int = 0
    opening_seconds: int = 0
    ending_seconds: int = 0
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None
    video_cover_override: str = ""
```

And extend `create_session()`:

```python
def create_session(
    self,
    vod: VodItem,
    playlist: list[PlayItem],
    clicked_index: int,
    playlists: list[list[PlayItem]] | None = None,
    playlist_index: int = 0,
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None,
    initial_log_message: str = "",
    is_placeholder: bool = False,
) -> PlayerSession:
    session = PlayerSession(
        vod=vod,
        playlist=active_playlist,
        start_index=start_index,
        start_position_seconds=position_seconds,
        speed=speed,
        playlists=normalized_playlists,
        playlist_index=playlist_index,
        opening_seconds=int((history.opening if history else 0) / 1000),
        ending_seconds=int((history.ending if history else 0) / 1000),
        detail_action_runner=detail_action_runner,
        initial_log_message=initial_log_message,
        is_placeholder=is_placeholder,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_create_session_defaults_detail_action_runner_to_none tests/test_player_controller.py::test_player_controller_create_session_preserves_detail_action_runner -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/controllers/player_controller.py tests/test_player_controller.py
git commit -m "feat: add playback detail action session model"
```

### Task 2: Python Spider Plugin Action Normalization And Runner

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `src/atv_player/models.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing spider action tests**

Add these helpers and tests to `tests/test_spider_plugin_controller.py`:

```python
from atv_player.models import PlaybackDetailAction


class ActionPayloadSpider(FakeSpider):
    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": f"https://stream.example{id}.m3u8",
            "actions": [
                {"id": "favorite_album", "label": "收藏专辑", "active": True, "tooltip": "已收藏"},
                {"id": "favorite_track", "label": "收藏歌曲", "enabled": False},
                {"id": "hidden", "label": "隐藏", "visible": False},
                {"id": "", "label": "bad"},
            ],
        }

    def runPlayerAction(self, action_id, context):
        assert context["action_id"] == action_id
        assert context["vod"].vod_name == "红果短剧"
        assert context["play_item"].title == "第1集"
        return {
            "actions": [
                {"id": "favorite_album", "label": "已收藏专辑", "active": True},
                {"id": "favorite_track", "label": "已收藏歌曲", "active": True},
            ]
        }


def test_spider_controller_maps_playercontent_actions_to_play_item() -> None:
    controller = SpiderPluginController(ActionPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")
    session = PlayerController(type("Api", (), {"get_history": lambda self, _key: None})()).create_session(
        request.vod,
        request.playlist,
        request.clicked_index,
        playlists=request.playlists,
        playlist_index=request.playlist_index,
        playback_loader=request.playback_loader,
        async_playback_loader=request.async_playback_loader,
        detail_action_runner=request.detail_action_runner,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])

    assert session.playlist[0].detail_actions == [
        PlaybackDetailAction(id="favorite_album", label="收藏专辑", active=True, tooltip="已收藏"),
        PlaybackDetailAction(id="favorite_track", label="收藏歌曲", enabled=False),
    ]


def test_spider_controller_detail_action_runner_returns_refreshed_actions() -> None:
    controller = SpiderPluginController(ActionPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.detail_action_runner is not None
    refreshed = request.detail_action_runner(request.playlist[0], "favorite_track")

    assert refreshed == [
        PlaybackDetailAction(id="favorite_album", label="已收藏专辑", active=True),
        PlaybackDetailAction(id="favorite_track", label="已收藏歌曲", active=True),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_actions_to_play_item tests/test_spider_plugin_controller.py::test_spider_controller_detail_action_runner_returns_refreshed_actions -v`

Expected: FAIL because spider actions are not normalized and `detail_action_runner` is missing.

- [ ] **Step 3: Write the minimal spider action normalization and runner**

In `src/atv_player/plugins/controller.py`, add normalization helpers near the existing subtitle and quality mappers:

```python
def _map_playback_detail_actions(payload: object) -> list[PlaybackDetailAction]:
    if not isinstance(payload, list):
        return []
    actions: list[PlaybackDetailAction] = []
    for raw_action in payload:
        if not isinstance(raw_action, Mapping):
            continue
        action_id = str(raw_action.get("id") or "").strip()
        label = str(raw_action.get("label") or "").strip()
        if not action_id or not label:
            continue
        action = PlaybackDetailAction(
            id=action_id,
            label=label,
            active=bool(raw_action.get("active")),
            enabled=bool(raw_action.get("enabled", True)),
            visible=bool(raw_action.get("visible", True)),
            tooltip=str(raw_action.get("tooltip") or "").strip(),
        )
        if action.visible:
            actions.append(action)
    return actions
```

Reset stale action state at the top of `_resolve_play_item()`:

```python
item.detail_actions = []
```

Populate it after `playerContent()` succeeds:

```python
item.detail_actions = _map_playback_detail_actions(payload.get("actions"))
```

Add a runner helper on `SpiderPluginController`:

```python
def _run_detail_action(
    self,
    vod: VodItem,
    playlists: list[list[PlayItem]],
    playlist_index: int,
    item: PlayItem,
    action_id: str,
) -> list[PlaybackDetailAction]:
    runner = getattr(self._spider, "runPlayerAction", None)
    if not callable(runner):
        raise ValueError(f"详情动作未注册[{action_id}]")
    context = {
        "action_id": action_id,
        "vod": vod,
        "play_item": item,
        "playlist": playlists[playlist_index] if 0 <= playlist_index < len(playlists) else [],
        "playlist_index": playlist_index,
        "play_index": item.index,
        "log": lambda message: logger.info("Spider detail action plugin=%s action=%s %s", self._plugin_name, action_id, message),
    }
    payload = runner(action_id, context)
    if isinstance(payload, Mapping):
        return _map_playback_detail_actions(payload.get("actions"))
    return _map_playback_detail_actions(payload)
```

Wire it in `build_request()`:

```python
detail_action_runner = lambda item, action_id, detail=detail, playlists=playlists: self._run_detail_action(
    detail,
    playlists,
    0,
    item,
    action_id,
)

return OpenPlayerRequest(
    vod=detail,
    playlist=playlist,
    playlists=playlists,
    playlist_index=0,
    clicked_index=0,
    source_kind="plugin",
    source_mode="detail",
    source_vod_id=source_vod_id,
    detail_action_runner=detail_action_runner,
)
```

When wiring the runner, capture the current session playlist index instead of hard-coding `0`:

```python
def playback_loader(
    session_or_item: PlayerSession | PlayItem,
    item: PlayItem | None = None,
) -> PlaybackLoadResult | None:
    if item is None:
        session = PlayerSession(
            vod=detail,
            playlist=playlist,
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
            playlists=playlists,
            playlist_index=0,
        )
        current_item = session_or_item
    else:
        session = session_or_item
        current_item = item
    return self._resolve_play_item(session, current_item)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_maps_playercontent_actions_to_play_item tests/test_spider_plugin_controller.py::test_spider_controller_detail_action_runner_returns_refreshed_actions -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: add spider playback detail actions"
```

### Task 3: Bilibili Detail Action Adapter

**Files:**
- Modify: `src/atv_player/api.py`
- Modify: `src/atv_player/controllers/bilibili_controller.py`
- Test: `tests/test_bilibili_controller.py`

- [ ] **Step 1: Write the failing Bilibili action tests**

Extend `FakeApiClient` in `tests/test_bilibili_controller.py` by appending these lines to the existing `__init__()` body and adding one new method:

```python
class FakeApiClient:
    def __init__(self) -> None:
        self.playback_payload = {
            "url": ["Episode 1", "http://b/1.mp4"],
            "header": {"Referer": "https://www.bilibili.com/"},
        }
        self.detail_action_payload = {"actions": []}
        self.detail_action_calls: list[tuple[str, str]] = []

    def run_bilibili_detail_action(self, vod_id: str, action_id: str) -> dict:
        self.detail_action_calls.append((vod_id, action_id))
        return self.detail_action_payload
```

Add these tests:

```python
from atv_player.models import PlaybackDetailAction


def test_load_playback_item_maps_bilibili_detail_actions() -> None:
    api = FakeApiClient()
    api.playback_payload = {
        "url": ["Episode 1", "http://b/1.mp4"],
        "header": {"Referer": "https://www.bilibili.com/"},
        "actions": [
            {"id": "favorite_collection", "label": "收藏歌单", "active": True},
            {"id": "like_track", "label": "点赞", "enabled": False},
            {"id": "", "label": "bad"},
        ],
    }
    controller = BilibiliController(api)
    item = PlayItem(title="视频", url="", vod_id="BV1xx411c7mD")

    controller.load_playback_item(item)

    assert item.detail_actions == [
        PlaybackDetailAction(id="favorite_collection", label="收藏歌单", active=True),
        PlaybackDetailAction(id="like_track", label="点赞", enabled=False),
    ]


def test_build_request_exposes_bilibili_detail_action_runner() -> None:
    api = FakeApiClient()
    api.detail_payload = {
        "list": [
            {
                "vod_id": "BV1xx411c7mD",
                "vod_name": "孤独摇滚",
                "vod_play_url": "第1话$BV1xx411c7mD",
            }
        ]
    }
    api.detail_action_payload = {
        "actions": [
            {"id": "favorite_collection", "label": "已收藏歌单", "active": True},
            {"id": "favorite_track", "label": "已收藏歌曲", "active": True},
        ]
    }
    controller = BilibiliController(api)

    request = controller.build_request("BV1xx411c7mD")

    assert request.detail_action_runner is not None
    refreshed = request.detail_action_runner(request.playlist[0], "favorite_track")

    assert api.detail_action_calls == [("BV1xx411c7mD", "favorite_track")]
    assert refreshed == [
        PlaybackDetailAction(id="favorite_collection", label="已收藏歌单", active=True),
        PlaybackDetailAction(id="favorite_track", label="已收藏歌曲", active=True),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bilibili_controller.py::test_load_playback_item_maps_bilibili_detail_actions tests/test_bilibili_controller.py::test_build_request_exposes_bilibili_detail_action_runner -v`

Expected: FAIL because Bilibili action mapping and runner support do not exist.

- [ ] **Step 3: Write the minimal Bilibili action adapter**

Add the narrow API client method in `src/atv_player/api.py`:

```python
def run_bilibili_detail_action(self, vod_id: str, action_id: str) -> dict[str, Any]:
    return self._request(
        "POST",
        f"/bilibili/{self._vod_token}/action",
        json={"id": vod_id, "action": action_id},
        headers={"X-CLIENT": "gui"},
    )
```

In `src/atv_player/controllers/bilibili_controller.py`, add a shared mapper:

```python
from atv_player.models import (
    DoubanCategory,
    ExternalSubtitleOption,
    HistoryRecord,
    OpenPlayerRequest,
    PlayItem,
    PlaybackDetailAction,
    VodItem,
)


def _map_detail_actions(payload: object) -> list[PlaybackDetailAction]:
    if not isinstance(payload, list):
        return []
    actions: list[PlaybackDetailAction] = []
    for raw_action in payload:
        if not isinstance(raw_action, dict):
            continue
        action_id = str(raw_action.get("id") or "").strip()
        label = str(raw_action.get("label") or "").strip()
        if not action_id or not label:
            continue
        visible = bool(raw_action.get("visible", True))
        if not visible:
            continue
        actions.append(
            PlaybackDetailAction(
                id=action_id,
                label=label,
                active=bool(raw_action.get("active")),
                enabled=bool(raw_action.get("enabled", True)),
                tooltip=str(raw_action.get("tooltip") or "").strip(),
            )
        )
    return actions
```

Populate actions during playback load:

```python
item.detail_actions = _map_detail_actions(payload.get("actions"))
```

Add an execution helper:

```python
def _run_detail_action(self, vod_id: str, action_id: str) -> list[PlaybackDetailAction]:
    payload = self._api_client.run_bilibili_detail_action(vod_id, action_id) or {}
    if isinstance(payload, dict):
        return _map_detail_actions(payload.get("actions"))
    return _map_detail_actions(payload)
```

Wire it in `build_request()`:

```python
return OpenPlayerRequest(
    vod=detail,
    playlist=playlist,
    clicked_index=0,
    playlists=playlists,
    playlist_index=playlist_index,
    source_kind="bilibili",
    source_mode="detail",
    source_vod_id=detail.vod_id,
    use_local_history=False,
    detail_action_runner=lambda _item, action_id, source_vod_id=detail.vod_id: self._run_detail_action(
        source_vod_id,
        action_id,
    ),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bilibili_controller.py::test_load_playback_item_maps_bilibili_detail_actions tests/test_bilibili_controller.py::test_build_request_exposes_bilibili_detail_action_runner -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/api.py src/atv_player/controllers/bilibili_controller.py tests/test_bilibili_controller.py
git commit -m "feat: add bilibili playback detail actions"
```

### Task 4: Player Sidebar Action Area And Execution Flow

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player window tests**

Add `PlaybackDetailAction` to the test imports in `tests/test_player_window_ui.py`, then add these tests near other sidebar-detail coverage:

```python
from atv_player.models import (
    AppConfig,
    ExternalSubtitleOption,
    ExternalSubtitleSelection,
    PlayItem,
    PlaybackDetailAction,
    PlaybackLoadResult,
    VideoQualityOption,
    VodItem,
)


def test_player_window_hides_detail_actions_when_current_item_has_none(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(make_player_session(start_index=0))

    assert window.detail_actions_widget.isHidden() is True
    assert window.detail_actions_layout.count() == 0


def test_player_window_renders_current_item_detail_actions_in_order(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    session = PlayerSession(
        vod=VodItem(vod_id="song-1", vod_name="Song"),
        playlist=[
            PlayItem(
                title="Track 1",
                url="http://m/1.m3u8",
                detail_actions=[
                    PlaybackDetailAction(id="favorite_collection", label="收藏歌单", active=True, tooltip="已收藏"),
                    PlaybackDetailAction(id="favorite_track", label="收藏歌曲", enabled=False),
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    window.open_session(session)

    assert window.detail_actions_widget.isHidden() is False
    assert [window.detail_actions_layout.itemAt(i).widget().text() for i in range(window.detail_actions_layout.count())] == [
        "收藏歌单",
        "收藏歌曲",
    ]
    assert window.detail_actions_layout.itemAt(0).widget().toolTip() == "已收藏"
    assert window.detail_actions_layout.itemAt(1).widget().isEnabled() is False


def test_player_window_executes_detail_action_and_refreshes_current_item(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    calls: list[tuple[str, str]] = []
    item = PlayItem(
        title="Track 1",
        url="http://m/1.m3u8",
        detail_actions=[PlaybackDetailAction(id="favorite_track", label="收藏歌曲")],
    )
    session = PlayerSession(
        vod=VodItem(vod_id="song-1", vod_name="Song"),
        playlist=[item],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        detail_action_runner=lambda current_item, action_id: calls.append((current_item.title, action_id)) or [
            PlaybackDetailAction(id="favorite_track", label="已收藏歌曲", active=True)
        ],
    )

    window.open_session(session)
    button = window.detail_actions_layout.itemAt(0).widget()
    button.click()
    qtbot.waitUntil(lambda: item.detail_actions[0].label == "已收藏歌曲")

    assert calls == [("Track 1", "favorite_track")]
    assert window.detail_actions_layout.itemAt(0).widget().text() == "已收藏歌曲"


def test_player_window_detail_action_failure_logs_error_without_stopping_playback(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    session = PlayerSession(
        vod=VodItem(vod_id="song-1", vod_name="Song"),
        playlist=[
            PlayItem(
                title="Track 1",
                url="http://m/1.m3u8",
                detail_actions=[PlaybackDetailAction(id="favorite_track", label="收藏歌曲")],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        detail_action_runner=lambda _item, _action_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    window.open_session(session)
    window.detail_actions_layout.itemAt(0).widget().click()
    qtbot.waitUntil(lambda: "详情动作执行失败[favorite_track]: boom" in window.log_view.toPlainText())

    assert window.video.load_calls == [("http://m/1.m3u8", 0)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_detail_actions_when_current_item_has_none tests/test_player_window_ui.py::test_player_window_renders_current_item_detail_actions_in_order tests/test_player_window_ui.py::test_player_window_executes_detail_action_and_refreshes_current_item tests/test_player_window_ui.py::test_player_window_detail_action_failure_logs_error_without_stopping_playback -v`

Expected: FAIL because the player sidebar has no detail-action UI or execution flow.

- [ ] **Step 3: Write the minimal player sidebar action UI and runner flow**

In `src/atv_player/ui/player_window.py`, add the action-area widgets in `__init__()` before `影片详情`:

```python
self.detail_actions_widget = QWidget()
self.detail_actions_layout = QHBoxLayout(self.detail_actions_widget)
self.detail_actions_layout.setContentsMargins(0, 0, 0, 0)
self.detail_actions_layout.setSpacing(6)
details_layout.addWidget(self.detail_actions_widget)
details_layout.addWidget(QLabel("影片详情"))
```

Add per-window action request state and signals near the other async signal classes:

```python
class _DetailActionSignals(QObject):
    succeeded = Signal(int, object, object)
    failed = Signal(int, str)
```

Initialize them:

```python
self._detail_action_request_id = 0
self._detail_action_signals = _DetailActionSignals()
self._connect_async_signal(self._detail_action_signals.succeeded, self._handle_detail_action_succeeded)
self._connect_async_signal(self._detail_action_signals.failed, self._handle_detail_action_failed)
```

Add helpers:

```python
def _current_detail_actions(self) -> list[PlaybackDetailAction]:
    if self.session is None or not (0 <= self.current_index < len(self.session.playlist)):
        return []
    return [action for action in self.session.playlist[self.current_index].detail_actions if action.visible]


def _clear_detail_action_buttons(self) -> None:
    while self.detail_actions_layout.count():
        item = self.detail_actions_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _render_detail_actions(self) -> None:
    self._clear_detail_action_buttons()
    actions = self._current_detail_actions()
    self.detail_actions_widget.setHidden(not actions)
    for action in actions:
        button = QPushButton(action.label)
        button.setToolTip(action.tooltip)
        button.setEnabled(action.enabled)
        button.setCheckable(True)
        button.setChecked(action.active)
        button.clicked.connect(lambda _checked=False, action_id=action.id: self._run_detail_action(action_id))
        self.detail_actions_layout.addWidget(button)
```

Refresh on lifecycle transitions:

```python
def open_session(self, session, start_paused: bool = False) -> None:
    self._invalidate_play_item_resolution()
    if not session.playlists:
        session.playlists = [session.playlist]
        session.playlist_index = 0
    self.session = session
    self._render_poster()
    self._render_metadata()
    self._reset_log()
    self.current_index = session.start_index
    self._render_detail_actions()
    self._render_playlist_group_combo()
    self._render_playlist_items()

def _apply_playback_loader_result(self, load_result: PlaybackLoadResult | None) -> None:
    if self.session is None:
        return
    if not isinstance(load_result, PlaybackLoadResult) or not load_result.replacement_playlist:
        self._render_detail_actions()
        return
    self._render_detail_actions()

def _play_item_at_index(
    self,
    index: int,
    start_position_seconds: int = 0,
    pause: bool = False,
    *,
    preserve_primary_external_subtitle_selection: bool = False,
) -> None:
    self._refresh_danmaku_source_entry_points()
    self._render_detail_actions()
    self._load_current_item(
        start_position_seconds=start_position_seconds,
        pause=pause,
        previous_index=self.current_index,
        preserve_primary_external_subtitle_selection=preserve_primary_external_subtitle_selection,
    )
```

Use the existing background task pattern for execution:

```python
def _set_detail_actions_enabled(self, enabled: bool) -> None:
    for index in range(self.detail_actions_layout.count()):
        widget = self.detail_actions_layout.itemAt(index).widget()
        if isinstance(widget, QPushButton):
            widget.setEnabled(enabled and widget.isEnabled())


def _run_detail_action(self, action_id: str) -> None:
    if self.session is None or self.session.detail_action_runner is None:
        self._append_log(f"详情动作未注册[{action_id}]")
        return
    if not (0 <= self.current_index < len(self.session.playlist)):
        return
    current_item = self.session.playlist[self.current_index]
    expected_index = self.current_index
    self._detail_action_request_id += 1
    request_id = self._detail_action_request_id
    self._set_detail_actions_enabled(False)

    def run() -> None:
        try:
            actions = self.session.detail_action_runner(current_item, action_id)
        except Exception as exc:
            if self._is_window_alive():
                self._detail_action_signals.failed.emit(request_id, f"详情动作执行失败[{action_id}]: {exc}")
            return
        if self._is_window_alive():
            self._detail_action_signals.succeeded.emit(request_id, current_item, (expected_index, actions))

    threading.Thread(target=run, daemon=True).start()


def _handle_detail_action_succeeded(self, request_id: int, item: PlayItem, payload: object) -> None:
    if request_id != self._detail_action_request_id or self.session is None:
        return
    expected_index, actions = payload
    if expected_index != self.current_index:
        self._render_detail_actions()
        return
    if self.session.playlist[self.current_index] is not item:
        self._render_detail_actions()
        return
    item.detail_actions = list(actions) if isinstance(actions, list) else []
    self._render_detail_actions()


def _handle_detail_action_failed(self, request_id: int, message: str) -> None:
    if request_id != self._detail_action_request_id:
        return
    self._append_log(message)
    self._render_detail_actions()
```

Keep the implementation minimal:

- no custom styling beyond `setCheckable()` and `setChecked()`
- no new persistence layer
- no new context menu entries

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_hides_detail_actions_when_current_item_has_none tests/test_player_window_ui.py::test_player_window_renders_current_item_detail_actions_in_order tests/test_player_window_ui.py::test_player_window_executes_detail_action_and_refreshes_current_item tests/test_player_window_ui.py::test_player_window_detail_action_failure_logs_error_without_stopping_playback -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player sidebar detail actions"
```

### Task 5: Focused Regression Verification

**Files:**
- Modify: none
- Test: `tests/test_player_controller.py`
- Test: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_bilibili_controller.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Run the focused controller and player tests**

Run:

```bash
uv run pytest \
  tests/test_player_controller.py \
  tests/test_spider_plugin_controller.py \
  tests/test_bilibili_controller.py \
  tests/test_player_window_ui.py -q
```

Expected: PASS

- [ ] **Step 2: If a failure appears in unrelated existing behavior, fix the smallest regression**

Keep fixes scoped to the changed detail-action plumbing. Typical acceptable fixes:

```python
# Example: preserve current button enabled state while temporarily disabling all buttons
button.setProperty("detail_action_base_enabled", action.enabled)
button.setEnabled(action.enabled)
for index in range(self.detail_actions_layout.count()):
    widget = self.detail_actions_layout.itemAt(index).widget()
    if isinstance(widget, QPushButton):
        base_enabled = bool(widget.property("detail_action_base_enabled"))
        widget.setEnabled(enabled and base_enabled)
```

Do not refactor unrelated sidebar, subtitle, or playback logic.

- [ ] **Step 3: Re-run the focused suite**

Run:

```bash
uv run pytest \
  tests/test_player_controller.py \
  tests/test_spider_plugin_controller.py \
  tests/test_bilibili_controller.py \
  tests/test_player_window_ui.py -q
```

Expected: PASS

- [ ] **Step 4: Commit the final integration state**

```bash
git add src/atv_player/models.py src/atv_player/controllers/player_controller.py src/atv_player/plugins/controller.py src/atv_player/controllers/bilibili_controller.py src/atv_player/api.py src/atv_player/ui/player_window.py tests/test_player_controller.py tests/test_spider_plugin_controller.py tests/test_bilibili_controller.py tests/test_player_window_ui.py
git commit -m "feat: add player detail actions"
```

## Self-Review

- Spec coverage check:
  - shared action model: Task 1
  - spider adapter + execution: Task 2
  - Bilibili adapter + execution: Task 3
  - player sidebar rendering + refresh + failure handling: Task 4
  - focused regression verification: Task 5
- Placeholder scan:
  - no `TODO`, `TBD`, or “handle appropriately” placeholders remain
  - every task has concrete files, code snippets, and exact commands
- Type consistency:
  - shared type name is `PlaybackDetailAction`
  - request/session callback name is `detail_action_runner`
  - per-item field name is `detail_actions`
