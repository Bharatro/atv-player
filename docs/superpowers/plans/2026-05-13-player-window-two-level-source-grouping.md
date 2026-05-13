# Player Window Two-Level Source Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-level playback source grouping to the player window so users pick a source group and a child source separately while keeping single-level routes, playback replacement, and history restore compatible.

**Architecture:** Keep `session.playlist` as the active leaf-source playlist, and add an explicit two-level source model around it. Normalize legacy flat `playlists` into grouped sources in `PlayerController`, persist the selected group/source alongside the old flat `playlistIndex`, and let `PlayerWindow` drive two linked combo boxes from the new grouped structure.

**Tech Stack:** Python 3.12, PySide6, sqlite3, pytest

---

## File Structure

- `src/atv_player/models.py`
  Responsibility: shared data models for `OpenPlayerRequest`, `PlayerSession` inputs, and playback history records.
- `src/atv_player/controllers/player_controller.py`
  Responsibility: normalize flat playlists into grouped sources, restore the active leaf source, and emit history payloads.
- `src/atv_player/ui/main_window.py`
  Responsibility: forward grouped-source request fields into `PlayerController.create_session()`.
- `src/atv_player/ui/player_window.py`
  Responsibility: render the group/source combo boxes, switch active sources, and keep replacement playlists scoped to the selected leaf source.
- `src/atv_player/local_playback_history.py`
  Responsibility: persist grouped-source selection for local non-server playback history.
- `src/atv_player/plugins/repository.py`
  Responsibility: persist grouped-source selection for spider-plugin playback history.
- `src/atv_player/api.py`
  Responsibility: parse optional `sourceGroupIndex` / `sourceIndex` fields from server history responses.
- `src/atv_player/plugins/controller.py`
  Responsibility: build grouped sources for spider playback routes while preserving the legacy flat playlist compatibility layer.
- `tests/test_player_controller.py`
  Responsibility: lock normalization, history restore, and reporting behavior.
- `tests/test_player_window_ui.py`
  Responsibility: lock the two-combo UI behavior and replacement-playlist scoping.
- `tests/test_storage.py`
  Responsibility: lock sqlite migration and grouped-source history persistence.
- `tests/test_api_client.py`
  Responsibility: lock API history parsing for optional grouped-source fields.
- `tests/test_spider_plugin_controller.py`
  Responsibility: lock spider route grouping and grouped request output.

### Task 1: Add Grouped Source Models And Session Normalization

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_player_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_controller_normalizes_legacy_playlists_into_grouped_sources() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    first_group = [PlayItem(title="第1集", url="http://a/1.m3u8", play_source="备用线")]
    second_group = [PlayItem(title="第1集", url="http://b/1.m3u8", play_source="极速线")]

    session = controller.create_session(
        vod,
        playlist=second_group,
        clicked_index=0,
        playlists=[first_group, second_group],
        playlist_index=1,
    )

    assert [group.label for group in session.source_groups] == ["备用线", "极速线"]
    assert [source.label for source in session.source_groups[0].sources] == ["备用线"]
    assert [source.label for source in session.source_groups[1].sources] == ["极速线"]
    assert session.source_group_index == 1
    assert session.source_index == 0
    assert session.playlist is second_group


def test_player_controller_restores_selected_grouped_source_from_history_loader() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie")
    baidu1 = [PlayItem(title="第1集", url="https://b1/1.m3u8", play_source="百度1")]
    baidu2 = [
        PlayItem(title="第1集", url="https://b2/1.m3u8", play_source="百度2"),
        PlayItem(title="第2集", url="https://b2/2.m3u8", play_source="百度2"),
    ]

    session = controller.create_session(
        vod,
        playlist=baidu1,
        clicked_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="百度",
                sources=[
                    PlaybackSource(label="百度1", playlist=baidu1),
                    PlaybackSource(label="百度2", playlist=baidu2),
                ],
            )
        ],
        source_group_index=0,
        source_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="plugin:plugin-vod-1",
            vod_name="Plugin Movie",
            vod_pic="",
            vod_remarks="第2集",
            episode=1,
            episode_url="https://b2/2.m3u8",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
            playlist_index=1,
            source_group_index=0,
            source_index=1,
        ),
    )

    assert session.source_group_index == 0
    assert session.source_index == 1
    assert session.playlist is baidu2
    assert session.playlist_index == 1
    assert session.start_index == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_normalizes_legacy_playlists_into_grouped_sources tests/test_player_controller.py::test_player_controller_restores_selected_grouped_source_from_history_loader -v`

Expected: FAIL with `AttributeError` or `TypeError` because `PlayerSession`, `OpenPlayerRequest`, and `HistoryRecord` do not yet expose grouped-source fields.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class PlaybackSource:
    label: str
    playlist: list[PlayItem] = field(default_factory=list)


@dataclass(slots=True)
class PlaybackSourceGroup:
    label: str
    sources: list[PlaybackSource] = field(default_factory=list)


@dataclass(slots=True)
class HistoryRecord:
    ...
    playlist_index: int = 0
    source_group_index: int = 0
    source_index: int = 0
    source_kind: str = "remote"
```

```python
@dataclass(slots=True)
class OpenPlayerRequest:
    vod: VodItem
    playlist: list[PlayItem]
    clicked_index: int
    playlists: list[list[PlayItem]] = field(default_factory=list)
    playlist_index: int = 0
    source_groups: list[PlaybackSourceGroup] = field(default_factory=list)
    source_group_index: int = 0
    source_index: int = 0
    ...
```

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
    source_groups: list[PlaybackSourceGroup] = field(default_factory=list)
    source_group_index: int = 0
    source_index: int = 0
    ...
```

```python
def _build_legacy_source_groups(self, playlist: list[PlayItem], playlists: list[list[PlayItem]] | None) -> list[PlaybackSourceGroup]:
    normalized = [group for group in (playlists or []) if group]
    if not normalized:
        normalized = [playlist]
    source_groups: list[PlaybackSourceGroup] = []
    for group_index, current_playlist in enumerate(normalized):
        label = current_playlist[0].play_source if current_playlist and current_playlist[0].play_source else f"线路 {group_index + 1}"
        source_groups.append(
            PlaybackSourceGroup(
                label=label,
                sources=[PlaybackSource(label=label, playlist=current_playlist)],
            )
        )
    return source_groups


def _flatten_source_groups(
    self,
    source_groups: list[PlaybackSourceGroup],
) -> tuple[list[list[PlayItem]], dict[tuple[int, int], int]]:
    playlists: list[list[PlayItem]] = []
    mapping: dict[tuple[int, int], int] = {}
    for group_index, group in enumerate(source_groups):
        for source_index, source in enumerate(group.sources):
            mapping[(group_index, source_index)] = len(playlists)
            playlists.append(source.playlist)
    return playlists, mapping


def _normalize_source_groups(
    self,
    playlist: list[PlayItem],
    playlists: list[list[PlayItem]] | None,
    playlist_index: int,
    source_groups: list[PlaybackSourceGroup] | None,
    source_group_index: int,
    source_index: int,
) -> tuple[list[PlaybackSourceGroup], int, int, list[list[PlayItem]], int, list[PlayItem]]:
    normalized_groups = [group for group in (source_groups or []) if group.sources]
    if not normalized_groups:
        normalized_groups = self._build_legacy_source_groups(playlist, playlists)
    source_group_index = max(0, min(source_group_index, len(normalized_groups) - 1))
    active_group = normalized_groups[source_group_index]
    source_index = max(0, min(source_index, len(active_group.sources) - 1))
    flat_playlists, flat_mapping = self._flatten_source_groups(normalized_groups)
    flat_index = flat_mapping[(source_group_index, source_index)]
    return (
        normalized_groups,
        source_group_index,
        source_index,
        flat_playlists,
        flat_index,
        active_group.sources[source_index].playlist,
    )
```

```python
def _restore_selected_source(
    self,
    source_groups: list[PlaybackSourceGroup],
    playlists: list[list[PlayItem]],
    playlist_index: int,
    source_group_index: int,
    source_index: int,
    history: HistoryRecord | None,
) -> tuple[int, int, int, list[PlayItem]]:
    if history is not None:
        if 0 <= history.source_group_index < len(source_groups):
            source_group_index = history.source_group_index
            active_group = source_groups[source_group_index]
            if 0 <= history.source_index < len(active_group.sources):
                source_index = history.source_index
        elif 0 <= history.playlist_index < len(playlists):
            playlist_index = history.playlist_index
            source_group_index = playlist_index
            source_index = 0
    flat_playlists, flat_mapping = self._flatten_source_groups(source_groups)
    playlist_index = flat_mapping[(source_group_index, source_index)]
    return source_group_index, source_index, playlist_index, flat_playlists[playlist_index]
```

```python
return self.player_controller.create_session(
    request.vod,
    request.playlist,
    request.clicked_index,
    playlists=request.playlists,
    playlist_index=request.playlist_index,
    source_groups=request.source_groups,
    source_group_index=request.source_group_index,
    source_index=request.source_index,
    ...
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_controller.py::test_player_controller_normalizes_legacy_playlists_into_grouped_sources tests/test_player_controller.py::test_player_controller_restores_selected_grouped_source_from_history_loader -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/controllers/player_controller.py src/atv_player/ui/main_window.py tests/test_player_controller.py
git commit -m "feat: add grouped player source session model"
```

### Task 2: Persist Grouped Source Selection In History

**Files:**
- Modify: `src/atv_player/api.py`
- Modify: `src/atv_player/local_playback_history.py`
- Modify: `src/atv_player/plugins/repository.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_local_playback_history_round_trip_persists_grouped_source_indexes(tmp_path: Path) -> None:
    repo = LocalPlaybackHistoryRepository(tmp_path / "history.db")

    repo.save_history(
        "spider_plugin",
        "detail-1",
        {
            "vodName": "红果短剧",
            "vodPic": "",
            "vodRemarks": "第2集",
            "episode": 1,
            "episodeUrl": "https://b2/2.m3u8",
            "position": 90000,
            "opening": 5000,
            "ending": 10000,
            "speed": 1.25,
            "playlistIndex": 3,
            "sourceGroupIndex": 1,
            "sourceIndex": 1,
            "createTime": 42,
        },
        source_key="7",
        source_name="红果短剧",
    )

    history = repo.get_history("spider_plugin", "detail-1", source_key="7")

    assert history is not None
    assert history.playlist_index == 3
    assert history.source_group_index == 1
    assert history.source_index == 1


def test_spider_plugin_repository_migrates_missing_grouped_source_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "plugins.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugin_playback_history (
                plugin_id INTEGER NOT NULL,
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                playlist_index INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (plugin_id, vod_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugin_playback_history (
                plugin_id, vod_id, vod_name, vod_pic, vod_remarks,
                episode, episode_url, position, opening, ending,
                speed, playlist_index, updated_at
            )
            VALUES (7, 'detail-1', '红果短剧', '', '第1集', 0, 'https://a/1.m3u8', 0, 0, 0, 1.0, 0, 99)
            """
        )

    repo = SpiderPluginRepository(db_path)
    history = repo.get_playback_history(7, "detail-1")

    assert history is not None
    assert history.source_group_index == 0
    assert history.source_index == 0


def test_api_client_get_history_reads_grouped_source_indexes(httpx_mock) -> None:
    client = ApiClient("http://127.0.0.1:4567", token="", vod_token="vod-token")
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:4567/history/vod-token?key=movie-1",
        json={
            "id": 1,
            "key": "movie-1",
            "vodName": "Movie",
            "episode": 2,
            "episodeUrl": "https://b2/3.m3u8",
            "playlistIndex": 4,
            "sourceGroupIndex": 2,
            "sourceIndex": 1,
            "createTime": 123,
        },
    )

    history = client.get_history("movie-1")

    assert history is not None
    assert history.playlist_index == 4
    assert history.source_group_index == 2
    assert history.source_index == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py::test_local_playback_history_round_trip_persists_grouped_source_indexes tests/test_storage.py::test_spider_plugin_repository_migrates_missing_grouped_source_columns tests/test_api_client.py::test_api_client_get_history_reads_grouped_source_indexes -v`

Expected: FAIL because sqlite schemas and API parsing do not yet read or persist `sourceGroupIndex` / `sourceIndex`.

- [ ] **Step 3: Write minimal implementation**

```python
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS media_playback_history (
        source_kind TEXT NOT NULL,
        source_key TEXT NOT NULL DEFAULT '',
        source_name TEXT NOT NULL DEFAULT '',
        vod_id TEXT NOT NULL,
        vod_name TEXT NOT NULL DEFAULT '',
        vod_pic TEXT NOT NULL DEFAULT '',
        vod_remarks TEXT NOT NULL DEFAULT '',
        episode INTEGER NOT NULL DEFAULT 0,
        episode_url TEXT NOT NULL DEFAULT '',
        position INTEGER NOT NULL DEFAULT 0,
        opening INTEGER NOT NULL DEFAULT 0,
        ending INTEGER NOT NULL DEFAULT 0,
        speed REAL NOT NULL DEFAULT 1.0,
        playlist_index INTEGER NOT NULL DEFAULT 0,
        source_group_index INTEGER NOT NULL DEFAULT 0,
        source_index INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (source_kind, source_key, vod_id)
    )
    """
)
columns = {row[1] for row in conn.execute("PRAGMA table_info(media_playback_history)").fetchall()}
if "source_group_index" not in columns:
    conn.execute("ALTER TABLE media_playback_history ADD COLUMN source_group_index INTEGER NOT NULL DEFAULT 0")
if "source_index" not in columns:
    conn.execute("ALTER TABLE media_playback_history ADD COLUMN source_index INTEGER NOT NULL DEFAULT 0")
```

```python
SELECT source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
       episode, episode_url, position, opening, ending, speed, playlist_index,
       source_group_index, source_index, updated_at
FROM media_playback_history
WHERE source_kind = ? AND source_key = ? AND vod_id = ?
```

```python
HistoryRecord(
    ...,
    playlist_index=int(row[13]),
    source_group_index=int(row[14]),
    source_index=int(row[15]),
    create_time=int(row[16]),
)
```

```python
INSERT INTO media_playback_history (
    source_kind, source_key, source_name, vod_id, vod_name, vod_pic, vod_remarks,
    episode, episode_url, position, opening, ending, speed, playlist_index,
    source_group_index, source_index, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(source_kind, source_key, vod_id) DO UPDATE SET
    ...
    playlist_index = excluded.playlist_index,
    source_group_index = excluded.source_group_index,
    source_index = excluded.source_index,
    updated_at = excluded.updated_at
```

```python
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS spider_plugin_playback_history (
        plugin_id INTEGER NOT NULL,
        vod_id TEXT NOT NULL,
        vod_name TEXT NOT NULL DEFAULT '',
        vod_pic TEXT NOT NULL DEFAULT '',
        vod_remarks TEXT NOT NULL DEFAULT '',
        episode INTEGER NOT NULL DEFAULT 0,
        episode_url TEXT NOT NULL DEFAULT '',
        position INTEGER NOT NULL DEFAULT 0,
        opening INTEGER NOT NULL DEFAULT 0,
        ending INTEGER NOT NULL DEFAULT 0,
        speed REAL NOT NULL DEFAULT 1.0,
        playlist_index INTEGER NOT NULL DEFAULT 0,
        source_group_index INTEGER NOT NULL DEFAULT 0,
        source_index INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (plugin_id, vod_id)
    )
    """
)
if "source_group_index" not in columns:
    conn.execute(
        "ALTER TABLE spider_plugin_playback_history ADD COLUMN source_group_index INTEGER NOT NULL DEFAULT 0"
    )
if "source_index" not in columns:
    conn.execute(
        "ALTER TABLE spider_plugin_playback_history ADD COLUMN source_index INTEGER NOT NULL DEFAULT 0"
    )
```

```python
return HistoryRecord(
    ...,
    playlist_index=int(data.get("playlistIndex", 0)),
    source_group_index=int(data.get("sourceGroupIndex", 0)),
    source_index=int(data.get("sourceIndex", 0)),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_storage.py::test_local_playback_history_round_trip_persists_grouped_source_indexes tests/test_storage.py::test_spider_plugin_repository_migrates_missing_grouped_source_columns tests/test_api_client.py::test_api_client_get_history_reads_grouped_source_indexes -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/api.py src/atv_player/local_playback_history.py src/atv_player/plugins/repository.py tests/test_storage.py tests/test_api_client.py
git commit -m "feat: persist grouped playback source history"
```

### Task 3: Replace The Single Route Selector With Two Linked Combos

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_player_window_renders_two_level_source_selectors_and_switches_group(qtbot) -> None:
    parse1 = [PlayItem(title="第1集", url="http://parse/1.m3u8", play_source="解析1")]
    baidu1 = [
        PlayItem(title="第1集", url="http://baidu1/1.m3u8", play_source="百度1"),
        PlayItem(title="第2集", url="http://baidu1/2.m3u8", play_source="百度1"),
    ]
    baidu2 = [
        PlayItem(title="第1集", url="http://baidu2/1.m3u8", play_source="百度2"),
        PlayItem(title="第2集", url="http://baidu2/2.m3u8", play_source="百度2"),
    ]
    session = PlayerSession(
        vod=VodItem(vod_id="plugin-1", vod_name="红果短剧"),
        playlist=baidu2,
        playlists=[parse1, baidu1, baidu2],
        playlist_index=2,
        source_groups=[
            PlaybackSourceGroup(label="解析", sources=[PlaybackSource(label="解析1", playlist=parse1)]),
            PlaybackSourceGroup(
                label="百度",
                sources=[
                    PlaybackSource(label="百度1", playlist=baidu1),
                    PlaybackSource(label="百度2", playlist=baidu2),
                ],
            ),
        ],
        source_group_index=1,
        source_index=1,
        start_index=1,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)

    assert [window.playlist_group_combo.itemText(i) for i in range(window.playlist_group_combo.count())] == ["解析", "百度"]
    assert [window.playlist_source_combo.itemText(i) for i in range(window.playlist_source_combo.count())] == ["百度1", "百度2"]
    assert window.playlist.currentRow() == 1

    window.playlist_group_combo.setCurrentIndex(0)

    assert window.session is not None
    assert window.session.source_group_index == 0
    assert window.session.source_index == 0
    assert window.current_index == 0
    assert window.video.load_calls[-1][0] == "http://parse/1.m3u8"


def test_player_window_switches_leaf_source_and_keeps_episode_index_when_possible(qtbot) -> None:
    first = [
        PlayItem(title="第1集", url="http://q1/1.m3u8", play_source="夸克1"),
        PlayItem(title="第2集", url="http://q1/2.m3u8", play_source="夸克1"),
    ]
    second = [
        PlayItem(title="第1集", url="http://q2/1.m3u8", play_source="夸克2"),
        PlayItem(title="第2集", url="http://q2/2.m3u8", play_source="夸克2"),
    ]
    session = PlayerSession(
        vod=VodItem(vod_id="plugin-1", vod_name="网盘剧集"),
        playlist=first,
        playlists=[first, second],
        playlist_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="夸克",
                sources=[
                    PlaybackSource(label="夸克1", playlist=first),
                    PlaybackSource(label="夸克2", playlist=second),
                ],
            )
        ],
        source_group_index=0,
        source_index=0,
        start_index=1,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    window.playlist_source_combo.setCurrentIndex(1)

    assert window.session is not None
    assert window.session.source_index == 1
    assert window.current_index == 1
    assert window.video.load_calls[-1][0] == "http://q2/2.m3u8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_renders_two_level_source_selectors_and_switches_group tests/test_player_window_ui.py::test_player_window_switches_leaf_source_and_keeps_episode_index_when_possible -v`

Expected: FAIL because `PlayerWindow` only has one route combo and no `playlist_source_combo`.

- [ ] **Step 3: Write minimal implementation**

```python
self.playlist_group_combo = QComboBox()
self.playlist_group_combo.setHidden(True)
self.playlist_source_combo = QComboBox()
self.playlist_source_combo.setHidden(True)
...
sidebar_layout.addWidget(self.playlist_group_combo)
sidebar_layout.addWidget(self.playlist_source_combo)
...
self.playlist_group_combo.currentIndexChanged.connect(self._change_playlist_group)
self.playlist_source_combo.currentIndexChanged.connect(self._change_playlist_source)
```

```python
def _session_source_groups(self) -> list[PlaybackSourceGroup]:
    if self.session is None:
        return []
    return self.session.source_groups


def _render_playlist_source_combos(self) -> None:
    source_groups = self._session_source_groups()
    self.playlist_group_combo.blockSignals(True)
    self.playlist_source_combo.blockSignals(True)
    self.playlist_group_combo.clear()
    self.playlist_source_combo.clear()
    for group in source_groups:
        self.playlist_group_combo.addItem(group.label)
    show_group_combo = len(source_groups) > 1
    active_group = source_groups[self.session.source_group_index] if self.session is not None and source_groups else None
    if active_group is not None:
        for source in active_group.sources:
            self.playlist_source_combo.addItem(source.label)
    show_source_combo = active_group is not None and len(active_group.sources) > 1
    self.playlist_group_combo.setHidden(not show_group_combo)
    self.playlist_source_combo.setHidden(not show_source_combo)
    if self.session is not None and source_groups:
        self.playlist_group_combo.setCurrentIndex(self.session.source_group_index)
        self.playlist_source_combo.setCurrentIndex(self.session.source_index)
    self.playlist_group_combo.blockSignals(False)
    self.playlist_source_combo.blockSignals(False)
```

```python
def _target_index_for_playlist(self, playlist: list[PlayItem]) -> int:
    if not playlist:
        return 0
    return max(0, min(self.current_index, len(playlist) - 1))


def _switch_active_source(self, source_group_index: int, source_index: int) -> None:
    if self.session is None:
        return
    source_groups = self._session_source_groups()
    target_playlist = source_groups[source_group_index].sources[source_index].playlist
    if not target_playlist:
        self.session.source_group_index = source_group_index
        self.session.source_index = source_index
        self._render_playlist_source_combos()
        self._render_playlist_items()
        return
    target_index = self._target_index_for_playlist(target_playlist)
    self.report_progress(force_remote_report=True)
    self._stop_current_playback()
    self._invalidate_play_item_resolution()
    self.session.source_group_index = source_group_index
    self.session.source_index = source_index
    self.session.playlist_index = self._flat_playlist_index(source_group_index, source_index)
    self.session.playlist = target_playlist
    self.current_index = target_index
    self._render_playlist_source_combos()
    self._render_playlist_items()
    self._load_current_item(previous_index=self.current_index)
```

```python
def _change_playlist_group(self, group_index: int) -> None:
    if self.session is None or group_index == self.session.source_group_index:
        return
    self._switch_active_source(group_index, 0)


def _change_playlist_source(self, source_index: int) -> None:
    if self.session is None or source_index == self.session.source_index:
        return
    self._switch_active_source(self.session.source_group_index, source_index)
```

```python
def _apply_playback_loader_result(self, load_result: PlaybackLoadResult | None) -> None:
    if self.session is None:
        return
    if not isinstance(load_result, PlaybackLoadResult) or not load_result.replacement_playlist:
        self._render_detail_actions()
        return
    replacement = list(load_result.replacement_playlist)
    active_group = self.session.source_groups[self.session.source_group_index]
    active_source = active_group.sources[self.session.source_index]
    active_source.playlist = replacement
    self.session.playlists[self.session.playlist_index] = replacement
    self.session.playlist = replacement
    self.current_index = max(0, min(load_result.replacement_start_index, len(replacement) - 1))
    self._render_playlist_source_combos()
    self._render_playlist_items()
    self._render_detail_actions()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_player_window_ui.py::test_player_window_renders_two_level_source_selectors_and_switches_group tests/test_player_window_ui.py::test_player_window_switches_leaf_source_and_keeps_episode_index_when_possible -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add two-level player source selectors"
```

### Task 4: Group Spider Playback Routes Into Two-Level Sources

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_spider_controller_groups_numbered_routes_into_two_level_sources() -> None:
    class GroupedRouteSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "红果短剧",
                        "vod_play_from": "解析1$$$百度1$$$百度2$$$夸克1$$$夸克2$$$夸克3$$$磁力1",
                        "vod_play_url": (
                            "第1集$http://parse/1.m3u8"
                            "$$$第1集$http://baidu1/1.m3u8"
                            "$$$第1集$http://baidu2/1.m3u8"
                            "$$$第1集$http://quark1/1.m3u8"
                            "$$$第1集$http://quark2/1.m3u8"
                            "$$$第1集$http://quark3/1.m3u8"
                            "$$$磁力1$magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        ),
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(GroupedRouteSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert [group.label for group in request.source_groups] == ["解析", "百度", "夸克", "磁力"]
    assert [source.label for source in request.source_groups[1].sources] == ["百度1", "百度2"]
    assert [source.label for source in request.source_groups[2].sources] == ["夸克1", "夸克2", "夸克3"]
    assert request.source_group_index == 0
    assert request.source_index == 0
    assert len(request.playlists) == 7


def test_spider_controller_keeps_non_numbered_routes_as_single_source_groups() -> None:
    class LegacyRouteSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "电影",
                        "vod_play_from": "备用线$$$极速线",
                        "vod_play_url": "正片$http://a/1.m3u8$$$正片$http://b/1.m3u8",
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(LegacyRouteSpider(), plugin_name="电影", search_enabled=True)
    request = controller.build_request("detail-1")

    assert [group.label for group in request.source_groups] == ["备用线", "极速线"]
    assert [source.label for source in request.source_groups[0].sources] == ["备用线"]
    assert [source.label for source in request.source_groups[1].sources] == ["极速线"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_groups_numbered_routes_into_two_level_sources tests/test_spider_plugin_controller.py::test_spider_controller_keeps_non_numbered_routes_as_single_source_groups -v`

Expected: FAIL because `OpenPlayerRequest` currently carries only flat routes from `SpiderPluginController`.

- [ ] **Step 3: Write minimal implementation**

```python
_ROUTE_GROUP_SUFFIX_RE = re.compile(r"^(?P<group>.*?\D)(?P<number>\d+)$")


def _split_route_group_and_source(route_label: str) -> tuple[str, str]:
    normalized = route_label.strip()
    if not normalized:
        return "", ""
    match = _ROUTE_GROUP_SUFFIX_RE.match(normalized)
    if match is None:
        return normalized, normalized
    group_label = match.group("group").strip()
    if not group_label:
        return normalized, normalized
    return group_label, normalized


def _build_source_groups_from_playlists(self, playlists: list[list[PlayItem]]) -> list[PlaybackSourceGroup]:
    source_groups: list[PlaybackSourceGroup] = []
    index_by_label: dict[str, int] = {}
    for group_index, playlist in enumerate(playlists):
        route_label = self._route_name([playlist[0].play_source if playlist else ""], 0)
        group_label, source_label = _split_route_group_and_source(route_label)
        if group_label not in index_by_label:
            index_by_label[group_label] = len(source_groups)
            source_groups.append(PlaybackSourceGroup(label=group_label, sources=[]))
        source_groups[index_by_label[group_label]].sources.append(
            PlaybackSource(label=source_label, playlist=playlist)
        )
    return source_groups
```

```python
source_groups = self._build_source_groups_from_playlists(playlists)
playlist = playlists[0]
return OpenPlayerRequest(
    vod=detail,
    playlist=playlist,
    playlists=playlists,
    playlist_index=0,
    source_groups=source_groups,
    source_group_index=0,
    source_index=0,
    clicked_index=0,
    ...
)
```

```python
session = PlayerSession(
    vod=detail,
    playlist=playlist,
    start_index=0,
    start_position_seconds=0,
    speed=1.0,
    playlists=playlists,
    playlist_index=0,
    source_groups=source_groups,
    source_group_index=0,
    source_index=0,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_groups_numbered_routes_into_two_level_sources tests/test_spider_plugin_controller.py::test_spider_controller_keeps_non_numbered_routes_as_single_source_groups -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: group spider playback routes into source groups"
```

### Task 5: Verify Cross-Cut Behavior Before Completion

**Files:**
- Modify: `tests/test_player_controller.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Add the cross-cut regression tests**

```python
def test_player_controller_reports_grouped_source_indexes_to_history_saver() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie")
    first = [PlayItem(title="第1集", url="https://q1/1.m3u8", play_source="夸克1")]
    second = [PlayItem(title="第1集", url="https://q2/1.m3u8", play_source="夸克2")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist=second,
        clicked_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="夸克",
                sources=[
                    PlaybackSource(label="夸克1", playlist=first),
                    PlaybackSource(label="夸克2", playlist=second),
                ],
            )
        ],
        source_group_index=0,
        source_index=1,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=30,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    assert saved_payloads[0]["playlistIndex"] == 1
    assert saved_payloads[0]["sourceGroupIndex"] == 0
    assert saved_payloads[0]["sourceIndex"] == 1


def test_player_window_replacement_updates_only_active_leaf_source(qtbot) -> None:
    active = [PlayItem(title="查看", url="", vod_id="https://pan.quark.cn/s/demo", play_source="夸克2")]
    sibling = [PlayItem(title="第1集", url="http://q1/1.mp4", play_source="夸克1")]
    session = PlayerSession(
        vod=VodItem(vod_id="plugin-1", vod_name="网盘剧集"),
        playlist=active,
        playlists=[sibling, active],
        playlist_index=1,
        source_groups=[
            PlaybackSourceGroup(
                label="夸克",
                sources=[
                    PlaybackSource(label="夸克1", playlist=sibling),
                    PlaybackSource(label="夸克2", playlist=active),
                ],
            )
        ],
        source_group_index=0,
        source_index=1,
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        playback_loader=lambda item: PlaybackLoadResult(
            replacement_playlist=[PlayItem(title="S1 - 1", url="http://m/1.mp4", play_source="夸克2")],
            replacement_start_index=0,
        ),
    )
    window = PlayerWindow(FakePlayerController(), config=None, save_config=lambda: None)
    qtbot.addWidget(window)

    window.open_session(session)

    assert window.session is not None
    assert [item.title for item in window.session.source_groups[0].sources[0].playlist] == ["第1集"]
    assert [item.title for item in window.session.source_groups[0].sources[1].playlist] == ["S1 - 1"]
```

- [ ] **Step 2: Run the focused regression suite**

Run: `uv run pytest tests/test_player_controller.py tests/test_player_window_ui.py tests/test_storage.py tests/test_api_client.py tests/test_spider_plugin_controller.py -q`

Expected: PASS

- [ ] **Step 3: Run the broader UI/session smoke suite**

Run: `uv run pytest tests/test_app.py tests/test_main_window_ui.py -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_player_controller.py tests/test_player_window_ui.py tests/test_storage.py tests/test_api_client.py tests/test_spider_plugin_controller.py
git commit -m "test: cover grouped playback source behavior"
```

## Self-Review

- Spec coverage:
  - Two-level models and legacy compatibility are covered by Task 1.
  - History persistence and restore are covered by Tasks 1 and 2.
  - Dual-combo UI behavior and replacement scoping are covered by Tasks 3 and 5.
  - Spider grouped-source request output is covered by Task 4.
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to Task N” references remain.
  - Every code-changing step includes concrete code or SQL.
- Type consistency:
  - Shared grouped-source names are `PlaybackSource`, `PlaybackSourceGroup`, `source_groups`, `source_group_index`, and `source_index` throughout the plan.

