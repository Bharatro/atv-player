# My Following Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full local `我的追更` feature: add from player or metadata search, persist progress and metadata IDs, check external metadata updates, show following-page reminders, show homepage prompts for users caught up to the previous latest episode, and provide a rich detail page.

**Architecture:** Add an independent following domain with focused dataclasses, SQLite repository, metadata adapter, controller, update service, list page, detail page, and search dialog. Reuse existing metadata providers/search, poster loading, player progress reporting, and `MainWindow` playback/search routing while keeping following persistence and reminder state separate from favorites.

**Tech Stack:** Python, PySide6, SQLite, existing metadata provider layer, existing poster/Qt theme utilities, pytest

---

## File Structure

- Create: `src/atv_player/following_models.py`
  Responsibility: following-only dataclasses and provider-priority helpers.
- Create: `src/atv_player/following_repository.py`
  Responsibility: SQLite tables, JSON serialization, CRUD, progress updates, check-state updates, prompt state.
- Create: `src/atv_player/following_metadata.py`
  Responsibility: convert metadata search/detail/provider raw payloads into `FollowingRecord` and `FollowingDetailSnapshot` shapes, compute episode totals/latest episode, and expose provider-priority selection.
- Create: `src/atv_player/following_update_service.py`
  Responsibility: due-record selection, scheduled checks, provider fallback, update-state transitions, Qt timer scheduling.
- Create: `src/atv_player/controllers/following_controller.py`
  Responsibility: search-add flow orchestration, page/detail view models, manual checks, progress updates, prompt operations.
- Create: `src/atv_player/ui/following_page.py`
  Responsibility: list page, search/filter controls, update markers, card activation, add/check/delete actions.
- Create: `src/atv_player/ui/following_detail_page.py`
  Responsibility: rich detail layout with backdrop/poster fallback, action row, episode rail, cast/crew rail, episode preview.
- Create: `src/atv_player/ui/following_search_dialog.py`
  Responsibility: metadata search dialog for adding following entries from external catalogs.
- Modify: `src/atv_player/ui/player_window.py`
  Responsibility: add a follow toggle alongside existing favorite metadata action and report following progress.
- Modify: `src/atv_player/ui/main_window.py`
  Responsibility: add following tab/header button, homepage prompt, following callbacks, search-play routing.
- Modify: `src/atv_player/app.py`
  Responsibility: construct and inject repository/controller/update service and metadata dependencies.
- Modify: `src/atv_player/icons/`
  Responsibility: add a following icon only if an existing icon is insufficient.
- Create: `tests/test_following_repository.py`
- Create: `tests/test_following_metadata.py`
- Create: `tests/test_following_update_service.py`
- Create: `tests/test_following_controller.py`
- Create: `tests/test_following_page_ui.py`
- Create: `tests/test_following_detail_page_ui.py`
- Modify: `tests/test_player_window_ui.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_app.py`

## Task 1: Following Models And Repository

**Files:**
- Create: `src/atv_player/following_models.py`
- Create: `src/atv_player/following_repository.py`
- Test: `tests/test_following_repository.py`

- [ ] **Step 1: Write failing repository tests**

```python
from pathlib import Path

from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.following_repository import FollowingRepository


def _record(**overrides):
    values = dict(
        id=0,
        title="凡人修仙传",
        original_title="",
        media_kind="anime",
        season_number=1,
        poster="poster",
        backdrop="backdrop",
        rating="8.2",
        provider="bangumi",
        provider_id="subject:123",
        provider_priority=["bangumi", "tmdb", "douban"],
        external_ids={"bangumi": "123", "tmdb": "456"},
        source_bindings=[],
        current_episode=127,
        position_seconds=300,
        watched_latest_episode=True,
        latest_episode=127,
        previous_latest_episode=127,
        total_episodes=156,
        has_update=False,
        new_episode_count=0,
        homepage_prompt_pending=False,
        prompt_snoozed_until=0,
        created_at=100,
        updated_at=100,
        last_played_at=90,
        last_checked_at=80,
        next_check_after=0,
        last_error="",
    )
    values.update(overrides)
    return FollowingRecord(**values)


def test_following_repository_upserts_by_provider_identity(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    first_id = repo.upsert(_record(title="旧标题"))
    second_id = repo.upsert(_record(title="新标题", poster="poster-b", updated_at=200))

    records, total = repo.load_page(page=1, size=20, keyword="", only_updates=False)

    assert first_id == second_id
    assert total == 1
    assert records[0].title == "新标题"
    assert records[0].poster == "poster-b"
    assert records[0].external_ids == {"bangumi": "123", "tmdb": "456"}


def test_following_repository_saves_snapshot_progress_and_prompt_state(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(_record())
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            overview="动画简介",
            cast=[{"name": "韩立", "role": "角色"}],
            crew=[{"name": "导演", "job": "Director"}],
            episodes=[FollowingEpisode(episode_number=128, title="新章", overview="剧情", still="still")],
            posters=["poster"],
            backdrops=["backdrop"],
            refreshed_at=110,
        ),
    )
    repo.update_progress(following_id, current_episode=128, position_seconds=42, last_played_at=120)
    repo.update_check_state(
        following_id,
        latest_episode=128,
        total_episodes=156,
        checked_at=130,
        next_check_after=140,
        has_update=True,
        new_episode_count=1,
        homepage_prompt_pending=True,
        last_error="",
    )

    record = repo.get(following_id)
    snapshot = repo.get_detail_snapshot(following_id)
    prompts = repo.load_homepage_prompt_records(now=131)

    assert record is not None
    assert record.current_episode == 128
    assert record.latest_episode == 128
    assert record.has_update is True
    assert record.homepage_prompt_pending is True
    assert snapshot is not None
    assert snapshot.episodes[0].title == "新章"
    assert [item.id for item in prompts] == [following_id]


def test_following_repository_filters_updates_and_snoozes_prompt(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    updated_id = repo.upsert(_record(title="有更新", provider_id="subject:1", has_update=True, homepage_prompt_pending=True))
    repo.upsert(_record(title="无更新", provider_id="subject:2", has_update=False))

    updated, total = repo.load_page(page=1, size=20, keyword="", only_updates=True)
    repo.snooze_prompt(updated_id, until=999)

    assert total == 1
    assert updated[0].title == "有更新"
    assert repo.load_homepage_prompt_records(now=998) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_following_repository.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.following_models'`.

- [ ] **Step 3: Add following dataclasses**

```python
# src/atv_player/following_models.py
from __future__ import annotations

from dataclasses import dataclass, field


ANIME_PROVIDER_PRIORITY = ["bangumi", "tmdb", "douban"]
LIVE_ACTION_PROVIDER_PRIORITY = ["tmdb", "douban", "bangumi"]


@dataclass(slots=True)
class FollowingSourceBinding:
    source_kind: str
    source_key: str = ""
    source_name: str = ""
    vod_id: str = ""
    provider: str = ""
    provider_id: str = ""


@dataclass(slots=True)
class FollowingEpisode:
    episode_number: int
    season_number: int = 0
    title: str = ""
    overview: str = ""
    air_date: str = ""
    still: str = ""
    runtime: int = 0
    is_special: bool = False


@dataclass(slots=True)
class FollowingDetailSnapshot:
    following_id: int = 0
    overview: str = ""
    cast: list[dict[str, object]] = field(default_factory=list)
    crew: list[dict[str, object]] = field(default_factory=list)
    episodes: list[FollowingEpisode] = field(default_factory=list)
    posters: list[str] = field(default_factory=list)
    backdrops: list[str] = field(default_factory=list)
    refreshed_at: int = 0


@dataclass(slots=True)
class FollowingRecord:
    id: int
    title: str
    original_title: str = ""
    media_kind: str = ""
    season_number: int = 0
    poster: str = ""
    backdrop: str = ""
    rating: str = ""
    provider: str = ""
    provider_id: str = ""
    provider_priority: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    source_bindings: list[FollowingSourceBinding] = field(default_factory=list)
    current_episode: int = 0
    position_seconds: int = 0
    watched_latest_episode: bool = False
    latest_episode: int = 0
    previous_latest_episode: int = 0
    total_episodes: int = 0
    has_update: bool = False
    new_episode_count: int = 0
    homepage_prompt_pending: bool = False
    prompt_snoozed_until: int = 0
    created_at: int = 0
    updated_at: int = 0
    last_played_at: int = 0
    last_checked_at: int = 0
    next_check_after: int = 0
    last_error: str = ""


@dataclass(slots=True)
class FollowingCardItem:
    record: FollowingRecord
    display_title: str
    subtitle: str
    progress_text: str
    update_text: str
    updated_hint: bool
    error_text: str = ""


@dataclass(slots=True)
class FollowingUpdateResult:
    record_id: int
    checked: bool
    latest_episode: int = 0
    total_episodes: int = 0
    has_update: bool = False
    homepage_prompt_pending: bool = False
    error: str = ""


def provider_priority_for_media_kind(media_kind: str) -> list[str]:
    return list(ANIME_PROVIDER_PRIORITY if media_kind == "anime" else LIVE_ACTION_PROVIDER_PRIORITY)
```

- [ ] **Step 4: Implement repository JSON helpers and schema**

```python
# src/atv_player/following_repository.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord, FollowingSourceBinding
from atv_player.sqlite_utils import managed_connection


def _json_loads(value: object, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _binding_to_dict(binding: FollowingSourceBinding) -> dict[str, str]:
    return {
        "source_kind": binding.source_kind,
        "source_key": binding.source_key,
        "source_name": binding.source_name,
        "vod_id": binding.vod_id,
        "provider": binding.provider,
        "provider_id": binding.provider_id,
    }


def _binding_from_dict(value: object) -> FollowingSourceBinding:
    data = value if isinstance(value, dict) else {}
    return FollowingSourceBinding(
        source_kind=str(data.get("source_kind") or ""),
        source_key=str(data.get("source_key") or ""),
        source_name=str(data.get("source_name") or ""),
        vod_id=str(data.get("vod_id") or ""),
        provider=str(data.get("provider") or ""),
        provider_id=str(data.get("provider_id") or ""),
    )
```

Add `_init_db()` with exact columns from the spec and a unique index:

```python
conn.execute("""
CREATE TABLE IF NOT EXISTS following (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    original_title TEXT NOT NULL DEFAULT '',
    media_kind TEXT NOT NULL DEFAULT '',
    season_number INTEGER NOT NULL DEFAULT 0,
    poster TEXT NOT NULL DEFAULT '',
    backdrop TEXT NOT NULL DEFAULT '',
    rating TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    provider_priority_json TEXT NOT NULL DEFAULT '[]',
    external_ids_json TEXT NOT NULL DEFAULT '{}',
    source_bindings_json TEXT NOT NULL DEFAULT '[]',
    current_episode INTEGER NOT NULL DEFAULT 0,
    position_seconds INTEGER NOT NULL DEFAULT 0,
    watched_latest_episode INTEGER NOT NULL DEFAULT 0,
    latest_episode INTEGER NOT NULL DEFAULT 0,
    previous_latest_episode INTEGER NOT NULL DEFAULT 0,
    total_episodes INTEGER NOT NULL DEFAULT 0,
    has_update INTEGER NOT NULL DEFAULT 0,
    new_episode_count INTEGER NOT NULL DEFAULT 0,
    homepage_prompt_pending INTEGER NOT NULL DEFAULT 0,
    prompt_snoozed_until INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0,
    last_played_at INTEGER NOT NULL DEFAULT 0,
    last_checked_at INTEGER NOT NULL DEFAULT 0,
    next_check_after INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    UNIQUE(provider, provider_id)
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS following_detail_snapshots (
    following_id INTEGER PRIMARY KEY,
    overview TEXT NOT NULL DEFAULT '',
    cast_json TEXT NOT NULL DEFAULT '[]',
    crew_json TEXT NOT NULL DEFAULT '[]',
    episodes_json TEXT NOT NULL DEFAULT '[]',
    posters_json TEXT NOT NULL DEFAULT '[]',
    backdrops_json TEXT NOT NULL DEFAULT '[]',
    refreshed_at INTEGER NOT NULL DEFAULT 0
)
""")
```

- [ ] **Step 5: Implement repository methods**

Implement these public methods on `FollowingRepository` with the schema above:

```python
def __init__(self, db_path: Path) -> None
def upsert(self, record: FollowingRecord) -> int
def get(self, record_id: int) -> FollowingRecord | None
def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool) -> tuple[list[FollowingRecord], int]
def delete(self, record_id: int) -> None
def save_detail_snapshot(self, following_id: int, snapshot: FollowingDetailSnapshot) -> None
def get_detail_snapshot(self, following_id: int) -> FollowingDetailSnapshot | None
def update_progress(self, following_id: int, *, current_episode: int, position_seconds: int, last_played_at: int) -> None
def update_check_state(self, following_id: int, *, latest_episode: int, total_episodes: int, checked_at: int, next_check_after: int, has_update: bool, new_episode_count: int, homepage_prompt_pending: bool, last_error: str) -> None
def load_due_records(self, *, now: int, limit: int) -> list[FollowingRecord]
def load_homepage_prompt_records(self, *, now: int) -> list[FollowingRecord]
def clear_homepage_prompt(self, following_id: int) -> None
def snooze_prompt(self, following_id: int, *, until: int) -> None
```

Critical behavior:

```python
# update_check_state should preserve the old latest as previous_latest_episode before writing the new latest.
previous = int(row["latest_episode"] or 0)
conn.execute(
    """
    UPDATE following
    SET previous_latest_episode = ?,
        latest_episode = ?,
        total_episodes = ?,
        last_checked_at = ?,
        next_check_after = ?,
        has_update = ?,
        new_episode_count = ?,
        homepage_prompt_pending = ?,
        last_error = ?
    WHERE id = ?
    """,
    (previous, latest_episode, total_episodes, checked_at, next_check_after, int(has_update), new_episode_count, int(homepage_prompt_pending), last_error, following_id),
)
```

- [ ] **Step 6: Run repository tests**

Run: `uv run pytest tests/test_following_repository.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/following_models.py src/atv_player/following_repository.py tests/test_following_repository.py
git commit -m "feat: add following repository"
```

## Task 2: Metadata Adapter For Following

**Files:**
- Create: `src/atv_player/following_metadata.py`
- Modify: `src/atv_player/metadata/providers/tmdb_client.py`
- Modify: `src/atv_player/metadata/providers/tmdb.py`
- Test: `tests/test_following_metadata.py`

- [ ] **Step 1: Write failing metadata adapter tests**

```python
from atv_player.following_metadata import (
    build_following_from_candidate,
    build_snapshot_from_record,
    compute_episode_counts,
    following_provider_priority,
)
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate


def test_following_provider_priority_prefers_bangumi_for_anime() -> None:
    assert following_provider_priority("anime") == ["bangumi", "tmdb", "douban"]
    assert following_provider_priority("live_action") == ["tmdb", "douban", "bangumi"]


def test_build_following_from_bangumi_candidate_preserves_ids_and_counts() -> None:
    candidate = MetadataScrapeCandidate(
        provider="bangumi",
        provider_label="Bangumi",
        provider_id="subject:123",
        title="凡人修仙传",
        year="2026",
        subtitle="动漫",
        raw={"episodes": [{"sort": 1, "name_cn": "第一话", "desc": "剧情"}, {"sort": 2, "name": "Episode 2"}]},
    )

    record, snapshot = build_following_from_candidate(candidate, now=100)

    assert record.provider == "bangumi"
    assert record.provider_id == "subject:123"
    assert record.external_ids["bangumi"] == "123"
    assert record.latest_episode == 2
    assert record.total_episodes == 2
    assert snapshot.episodes[0].title == "第一话"


def test_build_snapshot_from_tmdb_record_includes_backdrops_cast_and_episode_stills() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:456:season:1",
        title="庆余年",
        poster="poster",
        backdrop="backdrop",
        rating="8.0",
        tmdb_id="456",
        douban_id=129,
        actors=["张若昀"],
        directors=["孙皓"],
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 1, "name": "第一集", "overview": "剧情", "still_url": "still"}
                ],
            }
        ],
    )

    following, snapshot = build_snapshot_from_record(record, now=200, media_kind="live_action")

    assert following.external_ids == {"tmdb": "456", "douban": "129"}
    assert following.backdrop == "backdrop"
    assert snapshot.cast[0]["name"] == "张若昀"
    assert snapshot.crew[0]["name"] == "孙皓"
    assert snapshot.episodes[0].still == "still"


def test_compute_episode_counts_ignores_specials_and_zero_episode_numbers() -> None:
    latest, total = compute_episode_counts(
        [
            {"episode_number": 0, "name": "SP"},
            {"episode_number": 1, "name": "第一集"},
            {"sort": 3, "type": 1, "name": "特别篇"},
            {"sort": 2, "type": 0, "name": "第二集"},
        ]
    )

    assert latest == 2
    assert total == 2
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_following_metadata.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.following_metadata'`.

- [ ] **Step 3: Implement adapter functions**

```python
# src/atv_player/following_metadata.py
from __future__ import annotations

import re

from atv_player.following_models import (
    FollowingDetailSnapshot,
    FollowingEpisode,
    FollowingRecord,
    provider_priority_for_media_kind,
)


def following_provider_priority(media_kind: str) -> list[str]:
    return provider_priority_for_media_kind(media_kind)


def _provider_external_id(provider: str, provider_id: str) -> tuple[str, str]:
    if provider == "bangumi" and provider_id.startswith("subject:"):
        return "bangumi", provider_id.split(":", 1)[1]
    if provider == "tmdb":
        match = re.match(r"^(?:tv|movie):([^:]+)", provider_id)
        return ("tmdb", match.group(1)) if match else ("tmdb", provider_id)
    return provider, provider_id


def _episode_from_raw(raw: dict[str, object]) -> FollowingEpisode:
    number = int(raw.get("episode_number") or raw.get("sort") or raw.get("ep") or 0)
    title = str(raw.get("name_cn") or raw.get("name") or raw.get("title") or "").strip()
    return FollowingEpisode(
        episode_number=number,
        season_number=int(raw.get("season_number") or 0),
        title=title,
        overview=str(raw.get("overview") or raw.get("desc") or raw.get("summary") or "").strip(),
        air_date=str(raw.get("air_date") or raw.get("date") or "").strip(),
        still=str(raw.get("still_url") or raw.get("still") or raw.get("image") or "").strip(),
        runtime=int(raw.get("runtime") or raw.get("duration") or 0),
        is_special=number <= 0 or int(raw.get("type") or 0) != 0,
    )


def compute_episode_counts(raw_episodes: list[dict[str, object]]) -> tuple[int, int]:
    episodes = [_episode_from_raw(item) for item in raw_episodes if isinstance(item, dict)]
    normal_numbers = [episode.episode_number for episode in episodes if episode.episode_number > 0 and not episode.is_special]
    return (max(normal_numbers) if normal_numbers else 0, len(set(normal_numbers)))
```

Add:

```python
def build_following_from_candidate(candidate, *, now: int) -> tuple[FollowingRecord, FollowingDetailSnapshot]:
    raw = dict(getattr(candidate, "raw", {}) or {})
    provider = str(getattr(candidate, "provider", "") or "").strip()
    provider_id = str(getattr(candidate, "provider_id", "") or "").strip()
    external_key, external_value = _provider_external_id(provider, provider_id)
    raw_episodes = [item for item in raw.get("episodes") or [] if isinstance(item, dict)]
    latest, total = compute_episode_counts(raw_episodes)
    media_kind = "anime" if provider == "bangumi" or "动漫" in str(getattr(candidate, "subtitle", "")) else "live_action"
    record = FollowingRecord(
        id=0,
        title=str(getattr(candidate, "title", "") or "").strip(),
        media_kind=media_kind,
        provider=provider,
        provider_id=provider_id,
        provider_priority=following_provider_priority(media_kind),
        external_ids={external_key: str(external_value)} if external_value else {},
        latest_episode=latest,
        previous_latest_episode=latest,
        total_episodes=total,
        created_at=now,
        updated_at=now,
        next_check_after=now,
    )
    snapshot = FollowingDetailSnapshot(
        episodes=[_episode_from_raw(item) for item in raw_episodes],
        refreshed_at=now,
    )
    return record, snapshot
```

- [ ] **Step 4: Extend TMDB detail data for following**

Modify `TMDBClient.get_tv_season_detail()` to call `_request()` and then add `still_url` for each episode when `still_path` exists:

```python
def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, Any]:
    payload = self._request(f"/tv/{tmdb_id}/season/{season_number}")
    still_base = self._image_base("backdrop")
    episodes = []
    for episode in payload.get("episodes") or []:
        row = dict(episode)
        still_path = str(row.get("still_path") or "").strip()
        row["still_url"] = f"{still_base}{still_path}" if still_path else ""
        row["season_number"] = season_number
        episodes.append(row)
    payload["episodes"] = episodes
    return payload
```

Modify `TMDBProvider.get_detail()` so season episodes can be recovered by the following adapter through a detail field:

```python
detail_fields = []
if media_type == "tv" and season_number is not None:
    detail_fields.append({"label": "episodes", "value": list(season_payload.get("episodes") or [])})
```

Pass `detail_fields=detail_fields` into the `MetadataRecord` constructor.

- [ ] **Step 5: Run metadata tests**

Run: `uv run pytest tests/test_following_metadata.py tests/test_metadata_tmdb_client.py tests/test_metadata_tmdb_provider.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/following_metadata.py src/atv_player/metadata/providers/tmdb_client.py src/atv_player/metadata/providers/tmdb.py tests/test_following_metadata.py tests/test_metadata_tmdb_client.py tests/test_metadata_tmdb_provider.py
git commit -m "feat: add following metadata adapter"
```

## Task 3: Following Update Service

**Files:**
- Create: `src/atv_player/following_update_service.py`
- Test: `tests/test_following_update_service.py`

- [ ] **Step 1: Write failing update service tests**

```python
from pathlib import Path

from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.following_repository import FollowingRepository
from atv_player.following_update_service import FollowingUpdateService


class FakeMetadataGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failures: set[str] = set()

    def refresh(self, record: FollowingRecord, provider: str):
        self.calls.append((record.title, provider))
        if provider in self.failures:
            raise RuntimeError(f"{provider} failed")
        return (
            record,
            FollowingDetailSnapshot(
                following_id=record.id,
                episodes=[
                    FollowingEpisode(episode_number=1, title="第一集"),
                    FollowingEpisode(episode_number=2, title="第二集"),
                ],
                refreshed_at=200,
            ),
        )


def _record(**overrides):
    values = dict(
        id=0,
        title="凡人修仙传",
        media_kind="anime",
        provider="bangumi",
        provider_id="subject:1",
        provider_priority=["bangumi", "tmdb", "douban"],
        external_ids={"bangumi": "1"},
        latest_episode=1,
        previous_latest_episode=1,
        total_episodes=1,
        current_episode=1,
        watched_latest_episode=True,
        next_check_after=0,
        created_at=1,
        updated_at=1,
    )
    values.update(overrides)
    return FollowingRecord(**values)


def test_update_service_sets_homepage_prompt_when_caught_up(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record())
    gateway = FakeMetadataGateway()
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 200)

    results = service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert results[0].has_update is True
    assert record is not None
    assert record.latest_episode == 2
    assert record.has_update is True
    assert record.homepage_prompt_pending is True


def test_update_service_does_not_prompt_when_user_is_behind(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record(current_episode=0, watched_latest_episode=False))
    service = FollowingUpdateService(repo, metadata_gateway=FakeMetadataGateway(), now=lambda: 200)

    service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert record is not None
    assert record.has_update is True
    assert record.homepage_prompt_pending is False


def test_update_service_falls_back_to_next_provider_and_keeps_errors(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    record_id = repo.upsert(_record())
    gateway = FakeMetadataGateway()
    gateway.failures.add("bangumi")
    service = FollowingUpdateService(repo, metadata_gateway=gateway, now=lambda: 200)

    service.check_due_records(limit=10)

    record = repo.get(record_id)
    assert gateway.calls[:2] == [("凡人修仙传", "bangumi"), ("凡人修仙传", "tmdb")]
    assert record is not None
    assert record.last_error == ""
    assert record.latest_episode == 2
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_following_update_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'atv_player.following_update_service'`.

- [ ] **Step 3: Implement update service core**

```python
# src/atv_player/following_update_service.py
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QObject, QTimer, Signal

from atv_player.following_metadata import compute_episode_counts
from atv_player.following_models import FollowingRecord, FollowingUpdateResult


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
NORMAL_INTERVAL_SECONDS = 6 * 3600
WINDOW_INTERVAL_SECONDS = 5 * 60


def is_common_update_window(timestamp: int) -> bool:
    now = datetime.fromtimestamp(timestamp, BEIJING_TZ)
    minutes = now.hour * 60 + now.minute
    return (0 <= minutes < 120) or (600 <= minutes < 780) or (1080 <= minutes < 1410)
```

```python
class FollowingUpdateService(QObject):
    update_finished = Signal(object)

    def __init__(self, repository, *, metadata_gateway, now: Callable[[], int] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._metadata_gateway = metadata_gateway
        self._now = now or (lambda: int(time.time()))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_due_records)

    def next_interval_seconds(self) -> int:
        return WINDOW_INTERVAL_SECONDS if is_common_update_window(self._now()) else NORMAL_INTERVAL_SECONDS

    def start(self) -> None:
        QTimer.singleShot(60_000, self.check_due_records)
        self._timer.start(self.next_interval_seconds() * 1000)

    def check_due_records(self, limit: int = 3) -> list[FollowingUpdateResult]:
        now = self._now()
        results = [self._check_one(record, now=now) for record in self._repository.load_due_records(now=now, limit=limit)]
        if results:
            self.update_finished.emit(results)
        if self._timer.isActive():
            self._timer.start(self.next_interval_seconds() * 1000)
        return results
```

Implement `_check_one()`:

```python
def _check_one(self, record: FollowingRecord, *, now: int) -> FollowingUpdateResult:
    last_error = ""
    for provider in record.provider_priority or [record.provider]:
        try:
            refreshed_record, snapshot = self._metadata_gateway.refresh(record, provider)
        except Exception as exc:
            last_error = str(exc)
            continue
        raw_episodes = [
            {
                "episode_number": episode.episode_number,
                "type": 1 if episode.is_special else 0,
            }
            for episode in snapshot.episodes
        ]
        latest, total = compute_episode_counts(raw_episodes)
        latest = latest or refreshed_record.latest_episode or record.latest_episode
        total = total or refreshed_record.total_episodes or record.total_episodes
        has_update = latest > record.latest_episode or record.has_update
        new_count = max(latest - record.latest_episode, record.new_episode_count if record.has_update else 0)
        caught_up = record.watched_latest_episode or (record.latest_episode > 0 and record.current_episode >= record.latest_episode)
        snoozed = record.prompt_snoozed_until > now
        homepage_prompt = bool(has_update and caught_up and not snoozed)
        self._repository.update_check_state(
            record.id,
            latest_episode=latest,
            total_episodes=total,
            checked_at=now,
            next_check_after=now + self.next_interval_seconds(),
            has_update=has_update,
            new_episode_count=new_count,
            homepage_prompt_pending=homepage_prompt,
            last_error="",
        )
        if snapshot.episodes or snapshot.overview:
            self._repository.save_detail_snapshot(record.id, snapshot)
        return FollowingUpdateResult(record_id=record.id, checked=True, latest_episode=latest, total_episodes=total, has_update=has_update, homepage_prompt_pending=homepage_prompt)
    self._repository.update_check_state(
        record.id,
        latest_episode=record.latest_episode,
        total_episodes=record.total_episodes,
        checked_at=now,
        next_check_after=now + self.next_interval_seconds(),
        has_update=record.has_update,
        new_episode_count=record.new_episode_count,
        homepage_prompt_pending=record.homepage_prompt_pending,
        last_error=last_error,
    )
    return FollowingUpdateResult(record_id=record.id, checked=False, error=last_error)
```

- [ ] **Step 4: Run update service tests**

Run: `uv run pytest tests/test_following_update_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/following_update_service.py tests/test_following_update_service.py
git commit -m "feat: add following update service"
```

## Task 4: Following Controller

**Files:**
- Create: `src/atv_player/controllers/following_controller.py`
- Test: `tests/test_following_controller.py`

- [ ] **Step 1: Write failing controller tests**

```python
from pathlib import Path

from atv_player.controllers.following_controller import FollowingController
from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.following_repository import FollowingRepository
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup
from atv_player.models import PlayItem, VodItem


class FakeSearchService:
    def search(self, query, provider_filter=""):
        return [
            MetadataScrapeGroup(
                provider="bangumi",
                provider_label="Bangumi",
                items=[
                    MetadataScrapeCandidate(
                        provider="bangumi",
                        provider_label="Bangumi",
                        provider_id="subject:1",
                        title=query.title,
                        subtitle="动漫",
                        raw={"episodes": [{"sort": 1, "type": 0, "name": "第一话"}]},
                    )
                ],
            )
        ]


class FakeUpdateService:
    def __init__(self) -> None:
        self.manual_checks: list[int] = []

    def check_record(self, record_id: int):
        self.manual_checks.append(record_id)
        return None


def test_following_controller_searches_and_adds_candidate(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    groups = controller.search_media("凡人修仙传")
    record = controller.add_candidate(groups[0].items[0])

    assert groups[0].provider == "bangumi"
    assert record.title == "凡人修仙传"
    assert repo.get(record.id) is not None
    assert repo.get_detail_snapshot(record.id).episodes[0].title == "第一话"


def test_following_controller_builds_card_and_detail_models(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    following_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="凡人修仙传",
            provider="bangumi",
            provider_id="subject:1",
            provider_priority=["bangumi"],
            current_episode=127,
            latest_episode=128,
            total_episodes=156,
            has_update=True,
            new_episode_count=1,
        )
    )
    repo.save_detail_snapshot(
        following_id,
        FollowingDetailSnapshot(
            following_id=following_id,
            overview="简介",
            episodes=[FollowingEpisode(episode_number=128, title="新章")],
        ),
    )
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)

    cards, total = controller.load_page(page=1, size=20, keyword="", only_updates=True)
    detail = controller.load_detail(following_id)

    assert total == 1
    assert cards[0].progress_text == "看到 127 · 最新 128 / 总 156"
    assert cards[0].updated_hint is True
    assert detail.snapshot.overview == "简介"


def test_following_controller_adds_from_player_and_updates_progress(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "app.db")
    controller = FollowingController(repo, metadata_search_service=FakeSearchService(), update_service=FakeUpdateService(), now=lambda: 100)
    vod = VodItem(vod_id="vod-1", vod_name="凡人修仙传", vod_pic="poster", dbid=123)
    item = PlayItem(title="第127集", url="u", media_title="凡人修仙传", vod_id="vod-1")

    record = controller.add_from_player(vod=vod, item=item, source_kind="browse", source_key="", position_seconds=321)
    controller.record_playback_progress(record.id, current_episode=128, position_seconds=15)

    loaded = repo.get(record.id)
    assert loaded.current_episode == 128
    assert loaded.position_seconds == 15
    assert loaded.source_bindings[0].vod_id == "vod-1"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_following_controller.py -v`

Expected: FAIL because `atv_player.controllers.following_controller` does not exist.

- [ ] **Step 3: Implement controller models and methods**

Create `FollowingDetailView` inside `following_controller.py`:

```python
from dataclasses import dataclass

@dataclass(slots=True)
class FollowingDetailView:
    record: FollowingRecord
    snapshot: FollowingDetailSnapshot
```

Implement controller:

```python
class FollowingController:
    def __init__(self, repository, *, metadata_search_service, update_service=None, now=None) -> None:
        self._repository = repository
        self._metadata_search_service = metadata_search_service
        self._update_service = update_service
        self._now = now or (lambda: int(time.time()))

    def search_media(self, keyword: str):
        query = MetadataQuery(title=keyword.strip())
        return self._metadata_search_service.search(query)

    def add_candidate(self, candidate) -> FollowingRecord:
        record, snapshot = build_following_from_candidate(candidate, now=self._now())
        record_id = self._repository.upsert(record)
        saved = self._repository.get(record_id)
        snapshot.following_id = record_id
        self._repository.save_detail_snapshot(record_id, snapshot)
        return saved
```

Add these methods:

```python
def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
    records, total = self._repository.load_page(page=page, size=size, keyword=keyword, only_updates=only_updates)
    cards = [
        FollowingCardItem(
            record=record,
            display_title=record.title,
            subtitle=record.provider or record.media_kind,
            progress_text=f"看到 {record.current_episode} · 最新 {record.latest_episode} / 总 {record.total_episodes}",
            update_text=f"有 {record.new_episode_count} 集更新" if record.has_update else "暂无更新",
            updated_hint=record.has_update,
            error_text=record.last_error,
        )
        for record in records
    ]
    return cards, total

def load_detail(self, following_id: int) -> FollowingDetailView:
    record = self._repository.get(following_id)
    if record is None:
        raise KeyError(f"following not found: {following_id}")
    snapshot = self._repository.get_detail_snapshot(following_id) or FollowingDetailSnapshot(following_id=following_id)
    return FollowingDetailView(record=record, snapshot=snapshot)

def mark_watched_latest(self, following_id: int) -> None:
    record = self._repository.get(following_id)
    if record is None:
        return
    self._repository.update_progress(
        following_id,
        current_episode=record.latest_episode,
        position_seconds=0,
        last_played_at=self._now(),
    )
    self._repository.clear_homepage_prompt(following_id)

def record_playback_progress(self, following_id: int, *, current_episode: int, position_seconds: int) -> None:
    self._repository.update_progress(
        following_id,
        current_episode=current_episode,
        position_seconds=position_seconds,
        last_played_at=self._now(),
    )

def clear_homepage_prompt(self, following_id: int) -> None:
    self._repository.clear_homepage_prompt(following_id)

def snooze_prompt(self, following_id: int) -> None:
    self._repository.snooze_prompt(following_id, until=self._now() + 24 * 3600)
```

Use the existing episode inference helper in `add_from_player()`:

```python
episode_number = infer_playlist_episode_number(item, [item]) or 0
```

`add_from_player()` must create a `FollowingRecord` from `vod`, set a `FollowingSourceBinding`, save `position_seconds`, and use `vod.dbid` as a Douban external ID when present.

- [ ] **Step 4: Run controller tests**

Run: `uv run pytest tests/test_following_controller.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/controllers/following_controller.py tests/test_following_controller.py
git commit -m "feat: add following controller"
```

## Task 5: Following List Page And Search Dialog

**Files:**
- Create: `src/atv_player/ui/following_page.py`
- Create: `src/atv_player/ui/following_search_dialog.py`
- Test: `tests/test_following_page_ui.py`

- [ ] **Step 1: Write failing UI tests**

```python
from atv_player.following_models import FollowingCardItem, FollowingRecord
from atv_player.ui.following_page import FollowingPage


class FakeFollowingController:
    def __init__(self) -> None:
        self.check_all_calls = 0
        self.search_dialog_opened = 0
        self.only_updates_seen: list[bool] = []

    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        self.only_updates_seen.append(only_updates)
        record = FollowingRecord(
            id=1,
            title="凡人修仙传",
            provider="bangumi",
            provider_id="subject:1",
            current_episode=127,
            latest_episode=128,
            total_episodes=156,
            has_update=True,
        )
        return [
            FollowingCardItem(
                record=record,
                display_title=record.title,
                subtitle="Bangumi",
                progress_text="看到 127 · 最新 128 / 总 156",
                update_text="有 1 集更新",
                updated_hint=True,
            )
        ], 1

    def check_all_due(self) -> None:
        self.check_all_calls += 1


def test_following_page_renders_update_card_and_emits_detail(qtbot) -> None:
    controller = FakeFollowingController()
    page = FollowingPage(controller)
    opened: list[int] = []
    page.open_detail_requested.connect(opened.append)

    page.ensure_loaded()
    page.card_widgets[0].double_clicked.emit(page.records[0].record.id)

    assert page.records[0].display_title == "凡人修仙传"
    assert page.records[0].updated_hint is True
    assert opened == [1]


def test_following_page_filters_updates_and_runs_manual_check(qtbot) -> None:
    controller = FakeFollowingController()
    page = FollowingPage(controller)

    page.only_updates_checkbox.setChecked(True)
    page.load_page()
    page.check_updates_button.click()

    assert controller.only_updates_seen[-1] is True
    assert controller.check_all_calls == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_page_ui.py -v`

Expected: FAIL because `atv_player.ui.following_page` does not exist.

- [ ] **Step 3: Implement page structure**

Use `FavoritesPage` and `poster_grid_page._FlowLayout` patterns. Required widgets:

```python
class FollowingPage(QWidget, AsyncGuardMixin):
    open_detail_requested = Signal(int)

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self.current_page = 1
        self.page_size = 20
        self.records = []
        self.card_widgets = []
        self.search_edit = QLineEdit()
        self.add_button = QPushButton("添加追更")
        self.check_updates_button = QPushButton("检查更新")
        self.only_updates_checkbox = QCheckBox("只看有更新")
        self.page_size_combo = FlatComboBox()
```

Implement `FollowingCardButton` with:

- poster label
- title label
- progress label
- update label
- error label
- double-click signal carrying `record.id`

- [ ] **Step 4: Implement search dialog**

Create `FollowingSearchDialog`:

```python
class FollowingSearchDialog(QDialog):
    candidate_selected = Signal(object)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.search_edit = QLineEdit()
        self.search_button = QPushButton("搜索")
        self.provider_tabs = QTabWidget()
        self.status_label = QLabel("")
```

Search behavior:

```python
def run_search(self) -> None:
    keyword = self.search_edit.text().strip()
    if not keyword:
        self.status_label.setText("请输入标题")
        return
    groups = self.controller.search_media(keyword)
    self._render_groups(groups)
```

Each candidate row should show title, year, provider label, subtitle, and an `加入追更` button that calls `controller.add_candidate(candidate)` and emits `candidate_selected`.

- [ ] **Step 5: Run UI tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_page_ui.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/following_page.py src/atv_player/ui/following_search_dialog.py tests/test_following_page_ui.py
git commit -m "feat: add following page"
```

## Task 6: Following Detail Page

**Files:**
- Create: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write failing detail page tests**

```python
from atv_player.controllers.following_controller import FollowingDetailView
from atv_player.following_models import FollowingDetailSnapshot, FollowingEpisode, FollowingRecord
from atv_player.ui.following_detail_page import FollowingDetailPage


class FakeController:
    def __init__(self) -> None:
        self.manual_checks: list[int] = []
        self.mark_latest: list[int] = []
        self.deleted: list[int] = []

    def load_detail(self, following_id: int):
        return FollowingDetailView(
            record=FollowingRecord(
                id=following_id,
                title="凡人修仙传",
                poster="poster",
                backdrop="backdrop",
                rating="8.2",
                provider="bangumi",
                provider_id="subject:1",
                current_episode=127,
                latest_episode=128,
                total_episodes=156,
                has_update=True,
            ),
            snapshot=FollowingDetailSnapshot(
                following_id=following_id,
                overview="长篇简介",
                cast=[{"name": "韩立", "role": "主角", "avatar": ""}],
                crew=[{"name": "导演", "job": "Director"}],
                episodes=[FollowingEpisode(episode_number=128, title="新章", overview="完整剧情", still="still")],
                backdrops=["backdrop"],
            ),
        )

    def check_one(self, following_id: int) -> None:
        self.manual_checks.append(following_id)

    def mark_watched_latest(self, following_id: int) -> None:
        self.mark_latest.append(following_id)


def test_following_detail_page_renders_reference_layout_and_actions(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    search_play: list[int] = []
    page.search_play_requested.connect(search_play.append)

    page.load_record(1)
    page.search_play_button.click()
    page.manual_check_button.click()
    page.mark_latest_button.click()

    assert page.title_label.text() == "凡人修仙传"
    assert "最新 128 / 总 156" in page.meta_label.text()
    assert page.episode_widgets[0].title_label.text().startswith("128")
    assert page.cast_widgets[0].name_label.text() == "韩立"
    assert search_play == [1]
    assert controller.manual_checks == [1]
    assert controller.mark_latest == [1]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -v`

Expected: FAIL because `atv_player.ui.following_detail_page` does not exist.

- [ ] **Step 3: Implement detail page**

Create widgets:

```python
class FollowingDetailPage(QWidget, AsyncGuardMixin):
    back_requested = Signal()
    search_play_requested = Signal(int)
    unfollow_requested = Signal(int)

    def __init__(self, controller) -> None:
        super().__init__()
        self._init_async_guard()
        self.controller = controller
        self.current_following_id = 0
        self.back_button = QPushButton("返回")
        self.backdrop_label = QLabel()
        self.poster_label = QLabel()
        self.title_label = QLabel()
        self.meta_label = QLabel()
        self.overview_label = QLabel()
        self.search_play_button = QPushButton("搜索播放")
        self.manual_check_button = QPushButton("手动检查")
        self.mark_latest_button = QPushButton("标记追到最新")
        self.unfollow_button = QPushButton("取消追更")
        self.season_tabs = QTabBar()
        self.episode_widgets: list[FollowingEpisodeCard] = []
        self.cast_widgets: list[FollowingPersonCard] = []
```

Use horizontal `QScrollArea` sections for episode and cast rails. Render text immediately and load images through existing poster-loading utilities after widgets are created.

- [ ] **Step 4: Implement episode preview**

Create a small `QDialog` opened by clicking an episode card:

```python
class FollowingEpisodePreviewDialog(ThemedDialogBase):
    def __init__(self, episode: FollowingEpisode, parent=None) -> None:
        super().__init__(title=f"{episode.episode_number}. {episode.title}", resizable=True)
        self.episode = episode
        layout = QVBoxLayout(self.content_widget())
        self.still_label = QLabel()
        self.title_label = QLabel(f"{episode.episode_number}. {episode.title}")
        self.meta_label = QLabel(episode.air_date)
        self.overview_label = QLabel(episode.overview or "暂无剧情概要")
        self.overview_label.setWordWrap(True)
        layout.addWidget(self.still_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.overview_label)
```

The dialog shows still image or an empty still area, title, air date, and full overview.

- [ ] **Step 5: Run detail UI tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/following_detail_page.py tests/test_following_detail_page_ui.py
git commit -m "feat: add following detail page"
```

## Task 7: Player Following Integration

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing player UI tests**

Append tests near existing favorite button tests:

```python
def test_player_window_following_button_sits_next_to_favorite_and_toggles(qtbot):
    followed_ids: set[str] = {"vod-1"}
    toggled: list[str] = []

    def toggle(item):
        toggled.append(item.vod_id)
        if item.vod_id in followed_ids:
            followed_ids.remove(item.vod_id)
        else:
            followed_ids.add(item.vod_id)

    window = PlayerWindow(
        DummyPlayerController(),
        following_is_active=lambda item: item.vod_id in followed_ids,
        following_toggle=toggle,
    )
    window.session = SimpleNamespace(
        playlist=[PlayItem(title="第1集", url="u", vod_id="vod-1")],
        vod=VodItem(vod_id="vod-1", vod_name="凡人修仙传"),
        start_index=0,
    )
    window.current_index = 0

    window._refresh_following_button()

    assert window._metadata_heading_row.indexOf(window.following_button) == window._metadata_heading_row.indexOf(window.favorite_button) + 1
    assert window.following_button.property("following_active") is True
    assert window.following_button.toolTip() == "取消追更"

    window.following_button.click()

    assert toggled == ["vod-1"]
    assert window.following_button.property("following_active") is False
```

- [ ] **Step 2: Run targeted test to verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k following_button -v`

Expected: FAIL because `PlayerWindow.__init__()` does not accept `following_is_active`.

- [ ] **Step 3: Add player callbacks and button**

Modify `PlayerWindow.__init__` signature:

```python
following_is_active=None,
following_toggle=None,
following_progress_reporter=None,
```

Set:

```python
self._following_is_active = following_is_active or (lambda _item: False)
self._following_toggle = following_toggle or (lambda _item: None)
self._following_progress_reporter = following_progress_reporter or (lambda *_args, **_kwargs: None)
```

Add button after `favorite_button`:

```python
self.following_button = self._create_icon_button("refresh.svg", "加入追更")
self.following_button.clicked.connect(self._toggle_current_following)
self._metadata_heading_row.addWidget(self.favorite_button, 0, Qt.AlignmentFlag.AlignVCenter)
self._metadata_heading_row.addWidget(self.following_button, 0, Qt.AlignmentFlag.AlignVCenter)
```

Implement:

```python
def _refresh_following_button(self) -> None:
    item = self.current_item()
    active = item is not None and self._following_is_active(item)
    tooltip = "取消追更" if active else "加入追更"
    self.following_button.setHidden(item is None)
    self.following_button.setToolTip(tooltip)
    self.following_button.setAccessibleName(tooltip)
    self.following_button.setProperty("following_active", active)

def _toggle_current_following(self) -> None:
    item = self.current_item()
    if item is None:
        return
    self._following_toggle(item)
    self._refresh_following_button()
```

Call `_refresh_following_button()` wherever `_refresh_favorite_button()` is called.

- [ ] **Step 4: Report following progress**

In `report_progress()`, after existing controller progress reporting, call:

```python
item = self.current_item()
if item is not None:
    self._following_progress_reporter(
        item,
        position_seconds=int(self.video_widget.position() or 0),
        duration_seconds=int(self.video_widget.duration() or 0),
    )
```

Use the actual existing `MpvWidget` accessors in `report_progress()`; do not duplicate mpv state reads.

- [ ] **Step 5: Run player tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "following_button or favorite_button" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add player following action"
```

## Task 8: Main Window Integration And Homepage Prompt

**Files:**
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write failing main window tests**

```python
from atv_player.following_models import FollowingRecord


class FakeFollowingController:
    def __init__(self) -> None:
        self.cleared: list[int] = []
        self.snoozed: list[int] = []
        self.search_play: list[int] = []

    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        return [], 0

    def load_homepage_prompts(self):
        return [
            FollowingRecord(
                id=1,
                title="凡人修仙传",
                provider="bangumi",
                provider_id="subject:1",
                latest_episode=128,
                new_episode_count=1,
                homepage_prompt_pending=True,
            )
        ]

    def clear_homepage_prompt(self, following_id: int) -> None:
        self.cleared.append(following_id)

    def snooze_prompt(self, following_id: int) -> None:
        self.snoozed.append(following_id)


def test_main_window_registers_following_tab_and_header_button(qtbot):
    following_controller = FakeFollowingController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        following_controller=following_controller,
    )

    assert window.following_page is not None
    assert any(definition.key == "following" for definition in window._trailing_tab_definitions)
    assert window.following_button.toolTip() == "我的追更"


def test_main_window_homepage_prompt_actions(qtbot, monkeypatch):
    following_controller = FakeFollowingController()
    window = MainWindow(
        FakeStaticController(),
        DummyHistoryController(),
        FakePlayerController(),
        AppConfig(),
        following_controller=following_controller,
    )

    window.show_following_homepage_prompts()

    assert window._following_prompt_dialog is not None
    window._following_prompt_detail_button.click()
    assert following_controller.cleared == [1]
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k following -v`

Expected: FAIL because `following_controller` is not accepted and `following_page` is missing.

- [ ] **Step 3: Add empty controller and following page**

In `main_window.py`, add `_EmptyFollowingController` mirroring `_EmptyFavoritesController`:

```python
class _EmptyFollowingController:
    def load_page(self, *, page: int, size: int, keyword: str, only_updates: bool):
        return [], 0
    def load_homepage_prompts(self):
        return []
    def clear_homepage_prompt(self, following_id: int) -> None:
        del following_id
    def snooze_prompt(self, following_id: int) -> None:
        del following_id
```

Modify `MainWindow.__init__`:

```python
following_controller=None,
following_update_service=None,
```

Create:

```python
self._following_controller = following_controller or _EmptyFollowingController()
self._following_update_service = following_update_service
self.following_button = QPushButton("")
self.following_page = FollowingPage(self._following_controller)
self.following_detail_page = FollowingDetailPage(self._following_controller)
```

Add trailing tab:

```python
_TabDefinition("following", "我的追更", self.following_page),
```

Add header button near favorites:

```python
self._configure_header_icon_button(self.following_button, "我的追更")
self.following_button.clicked.connect(lambda: self.nav_tabs.setCurrentWidget(self.following_page))
```

- [ ] **Step 4: Wire detail navigation and search-play**

Connect:

```python
self.following_page.open_detail_requested.connect(self.open_following_detail)
self.following_detail_page.back_requested.connect(lambda: self.nav_tabs.setCurrentWidget(self.following_page))
self.following_detail_page.search_play_requested.connect(self.search_play_for_following)
```

Implement:

```python
def open_following_detail(self, following_id: int) -> None:
    self._following_controller.clear_homepage_prompt(following_id)
    self.following_detail_page.load_record(following_id)
    self.nav_tabs.setCurrentWidget(self.following_detail_page)

def search_play_for_following(self, following_id: int) -> None:
    view = self._following_controller.load_detail(following_id)
    self.global_search_edit.setText(view.record.title)
    self.nav_tabs.setCurrentWidget(self.douban_page)
    self._start_global_search()
```

- [ ] **Step 5: Implement homepage prompt**

Add a compact `QDialog` or `QMessageBox` wrapper. Store test-visible fields:

```python
self._following_prompt_dialog = None
self._following_prompt_detail_button = None
self._following_prompt_search_button = None
self._following_prompt_snooze_button = None
```

Implement:

```python
def show_following_homepage_prompts(self) -> None:
    records = list(self._following_controller.load_homepage_prompts())
    if not records:
        return
    record = records[0]
    dialog = ThemedDialogBase(title="追更更新", resizable=False)
    layout = QVBoxLayout(dialog.content_widget())
    title_label = QLabel(record.title)
    detail_label = QLabel(f"更新 {record.new_episode_count} 集，最新第 {record.latest_episode} 集")
    button_row = QHBoxLayout()
    self._following_prompt_detail_button = QPushButton("查看详情")
    self._following_prompt_search_button = QPushButton("搜索播放")
    self._following_prompt_snooze_button = QPushButton("稍后提醒")
    button_row.addWidget(self._following_prompt_detail_button)
    button_row.addWidget(self._following_prompt_search_button)
    button_row.addWidget(self._following_prompt_snooze_button)
    layout.addWidget(title_label)
    layout.addWidget(detail_label)
    layout.addLayout(button_row)
    self._following_prompt_detail_button.clicked.connect(lambda: self.open_following_detail(record.id))
    self._following_prompt_search_button.clicked.connect(lambda: self.search_play_for_following(record.id))
    self._following_prompt_snooze_button.clicked.connect(lambda: self._snooze_following_prompt(record.id))
    self._following_prompt_dialog = dialog
    dialog.show()
```

If `following_update_service` exists, connect its `update_finished` signal to `show_following_homepage_prompts`.

- [ ] **Step 6: Run main window tests**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -k following -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ui/main_window.py tests/test_main_window_ui.py
git commit -m "feat: integrate following in main window"
```

## Task 9: App Wiring

**Files:**
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing app wiring test**

Add a test near the favorites wiring test:

```python
def test_app_coordinator_show_main_wires_following_controller(monkeypatch) -> None:
    captured = {}

    class FakeMainWindow:
        def __init__(self, *args, **kwargs) -> None:
            captured["window_kwargs"] = kwargs

        def show(self) -> None:
            pass

    monkeypatch.setattr("atv_player.app.MainWindow", FakeMainWindow)
    coordinator = AppCoordinator(FakeApp(), SettingsRepository(":memory:"))
    coordinator._api_client = FakeApiClient()
    coordinator.repo.save_config(AppConfig(token="token"))

    coordinator._show_main()

    assert captured["window_kwargs"]["following_controller"] is not None
    assert captured["window_kwargs"]["following_update_service"] is not None
```

- [ ] **Step 2: Run targeted test to verify failure**

Run: `uv run pytest tests/test_app.py -k following_controller -v`

Expected: FAIL because `following_controller` is not wired.

- [ ] **Step 3: Construct following dependencies**

In `app.py`, import:

```python
from atv_player.controllers.following_controller import FollowingController
from atv_player.following_repository import FollowingRepository
from atv_player.following_update_service import FollowingUpdateService
```

Add repository initialization next to favorites repository:

```python
self._following_repository = FollowingRepository(repo.database_path)
```

Build a metadata search service factory for following using configured providers:

```python
def _build_following_metadata_search_service(self, api_client: ApiClient) -> MetadataScrapeService:
    config = self.repo.load_config()
    providers = self._build_metadata_providers(
        api_client=api_client,
        config=config,
        source_kind="browse",
        raw_detail=None,
    )
    return MetadataScrapeService(cache=MetadataCache(app_cache_dir() / "metadata"), providers=providers)
```

Build `metadata_gateway` used by `FollowingUpdateService`. Start with a small adapter object in `app.py` or `following_metadata.py`:

```python
class FollowingMetadataGateway:
    def __init__(self, metadata_search_service: MetadataScrapeService) -> None:
        self._metadata_search_service = metadata_search_service

    def refresh(self, record: FollowingRecord, provider: str):
        groups = self._metadata_search_service.search(MetadataQuery(title=record.title), provider_filter=provider)
        candidates = [item for group in groups for item in group.items]
        preferred = next((item for item in candidates if item.provider_id == record.provider_id), None)
        candidate = preferred or (candidates[0] if candidates else None)
        if candidate is None:
            raise RuntimeError(f"{provider} returned no following candidate")
        return build_following_from_candidate(candidate, now=int(time.time()))
```

Place `FollowingMetadataGateway` in `following_metadata.py` if importing `MetadataQuery` in `app.py` would create an import cycle during tests.

- [ ] **Step 4: Inject into main window**

In `_show_main()`:

```python
following_search_service = self._build_following_metadata_search_service(api_client)
following_update_service = FollowingUpdateService(
    self._following_repository,
    metadata_gateway=FollowingMetadataGateway(following_search_service),
)
following_controller = FollowingController(
    self._following_repository,
    metadata_search_service=following_search_service,
    update_service=following_update_service,
)
```

Pass:

```python
following_controller=following_controller,
following_update_service=following_update_service,
```

After `MainWindow` is created and shown, call:

```python
following_update_service.start()
```

- [ ] **Step 5: Run app test**

Run: `uv run pytest tests/test_app.py -k "following_controller or favorites_controller" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/app.py tests/test_app.py
git commit -m "feat: wire following app services"
```

## Task 10: End-To-End Verification And Polish

**Files:**
- Modify only files touched in Tasks 1-9 when verification exposes failures.

- [ ] **Step 1: Run focused following tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_following_repository.py \
  tests/test_following_metadata.py \
  tests/test_following_update_service.py \
  tests/test_following_controller.py \
  tests/test_following_page_ui.py \
  tests/test_following_detail_page_ui.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run integration-adjacent tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_player_window_ui.py -k "following or favorite" \
  tests/test_main_window_ui.py -k "following or favorites" \
  tests/test_app.py -k "following_controller or favorites_controller" \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run lint on touched files**

Run:

```bash
uv run ruff check \
  src/atv_player/following_models.py \
  src/atv_player/following_repository.py \
  src/atv_player/following_metadata.py \
  src/atv_player/following_update_service.py \
  src/atv_player/controllers/following_controller.py \
  src/atv_player/ui/following_page.py \
  src/atv_player/ui/following_detail_page.py \
  src/atv_player/ui/following_search_dialog.py \
  src/atv_player/ui/player_window.py \
  src/atv_player/ui/main_window.py \
  src/atv_player/app.py
```

Expected: PASS.

- [ ] **Step 4: Run compile check**

Run:

```bash
uv run python -m py_compile \
  src/atv_player/following_models.py \
  src/atv_player/following_repository.py \
  src/atv_player/following_metadata.py \
  src/atv_player/following_update_service.py \
  src/atv_player/controllers/following_controller.py \
  src/atv_player/ui/following_page.py \
  src/atv_player/ui/following_detail_page.py \
  src/atv_player/ui/following_search_dialog.py
```

Expected: PASS.

- [ ] **Step 5: Commit verification fixes if any**

If verification required fixes, stage the concrete touched files from Tasks 1-9:

```bash
git add src/atv_player/following_models.py src/atv_player/following_repository.py src/atv_player/following_metadata.py src/atv_player/following_update_service.py src/atv_player/controllers/following_controller.py src/atv_player/ui/following_page.py src/atv_player/ui/following_detail_page.py src/atv_player/ui/following_search_dialog.py src/atv_player/ui/player_window.py src/atv_player/ui/main_window.py src/atv_player/app.py tests/test_following_repository.py tests/test_following_metadata.py tests/test_following_update_service.py tests/test_following_controller.py tests/test_following_page_ui.py tests/test_following_detail_page_ui.py tests/test_player_window_ui.py tests/test_main_window_ui.py tests/test_app.py
git commit -m "fix: stabilize following integration"
```

If no fixes were needed, do not create an empty commit.

## Spec Coverage Self-Review

- Data model and persistence: Task 1.
- External metadata search and detail snapshots: Task 2 and Task 4.
- Update checks, provider fallback, update windows, prompt state: Task 3.
- Following page reminders and search-add flow: Task 5.
- Detail page using the referenced `nostr (5).html#detail` information hierarchy: Task 6.
- Player add/progress integration: Task 7.
- Homepage prompt and app wiring: Task 8 and Task 9.
- Verification: Task 10.

No implementation requirement from the spec is intentionally left out of this plan.
