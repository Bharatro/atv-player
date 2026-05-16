# Bangumi Metadata Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an anime-only `BangumiMetadataProvider` with optional access-token support, wire it into automatic metadata hydration and manual scrape flows, and use Bangumi episode data for anime episode-title enhancement.

**Architecture:** Keep the existing provider-driven metadata pipeline and add Bangumi as one more explicit provider instead of folding it into a site provider. Make Bangumi always available at construction time, but gate participation by anime-category checks inside the provider, scrape option filtering, and episode-title candidate ordering.

**Tech Stack:** Python 3.14, dataclasses, `httpx`, PySide6, sqlite3, pytest

---

## File Map

**Create:**
- `src/atv_player/metadata/providers/bangumi_client.py`
- `src/atv_player/metadata/providers/bangumi.py`
- `tests/test_metadata_bangumi_client.py`
- `tests/test_metadata_bangumi_provider.py`

**Modify:**
- `src/atv_player/models.py`
- `src/atv_player/storage.py`
- `src/atv_player/ui/advanced_settings_dialog.py`
- `src/atv_player/metadata/providers/__init__.py`
- `src/atv_player/metadata/matching.py`
- `src/atv_player/metadata/merge.py`
- `src/atv_player/metadata/episode_title_resolver.py`
- `src/atv_player/metadata/scrape.py`
- `src/atv_player/app.py`
- `tests/test_storage.py`
- `tests/test_main_window_ui.py`
- `tests/test_metadata_merge.py`
- `tests/test_metadata_hydrator.py`
- `tests/test_metadata_scrape_service.py`
- `tests/test_metadata_episode_title_resolver.py`
- `tests/test_app.py`

**Existing references to inspect while implementing:**
- `src/atv_player/metadata/models.py`
- `src/atv_player/metadata/providers/tmdb.py`
- `src/atv_player/metadata/providers/bilibili.py`
- `docs/superpowers/specs/2026-05-16-bangumi-metadata-provider-design.md`

### Task 1: Add Bangumi token storage and advanced-settings UI

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing storage and dialog tests**

```python
def test_settings_repository_round_trip_persists_bangumi_token(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load()
    config.metadata_bangumi_access_token = "bgm-token"

    repo.save(config)

    saved = repo.load()
    assert saved.metadata_bangumi_access_token == "bgm-token"


def test_settings_repository_migrates_missing_bangumi_token_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO app_config (id, base_url, username, token, vod_token, last_path) VALUES (1, '', '', '', '', '/')"
        )
    repo = SettingsRepository(db_path)

    assert repo.load().metadata_bangumi_access_token == ""


def test_advanced_settings_dialog_loads_and_saves_bangumi_token(qtbot) -> None:
    saved: list[AppConfig] = []
    config = AppConfig(metadata_bangumi_access_token="bgm-demo-token")
    dialog = AdvancedSettingsDialog(config, save_config=lambda: saved.append(config))
    qtbot.addWidget(dialog)

    assert dialog.bangumi_access_token_edit.text() == "bgm-demo-token"
    dialog.bangumi_access_token_edit.setText("bgm-updated-token")
    dialog._save()

    assert saved[-1].metadata_bangumi_access_token == "bgm-updated-token"
```

- [ ] **Step 2: Run the focused settings tests and verify they fail**

Run: `uv run pytest tests/test_storage.py tests/test_main_window_ui.py -k "bangumi_token" -q`

Expected: FAIL because `metadata_bangumi_access_token` and `bangumi_access_token_edit` do not exist yet.

- [ ] **Step 3: Add the minimal config, storage, and dialog implementation**

```python
@dataclass(slots=True)
class AppConfig:
    metadata_tmdb_api_key: str = ""
    metadata_bangumi_access_token: str = ""
    episode_title_enhancement_enabled: bool = True
```

```python
if "metadata_bangumi_access_token" not in columns:
    conn.execute(
        "ALTER TABLE app_config ADD COLUMN metadata_bangumi_access_token TEXT NOT NULL DEFAULT ''"
    )
```

```python
self.bangumi_access_token_edit = QLineEdit()
self.bangumi_access_token_edit.setPlaceholderText("可选；留空时使用匿名访问")
self.bangumi_access_token_edit.setText(config.metadata_bangumi_access_token)
metadata_layout.addRow("Bangumi Access Token", self.bangumi_access_token_edit)
```

```python
self._config.metadata_bangumi_access_token = self.bangumi_access_token_edit.text().strip()
```

- [ ] **Step 4: Run the focused settings tests and verify they pass**

Run: `uv run pytest tests/test_storage.py tests/test_main_window_ui.py -k "bangumi_token" -q`

Expected: PASS with the new storage migration and dialog coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py src/atv_player/ui/advanced_settings_dialog.py tests/test_storage.py tests/test_main_window_ui.py
git commit -m "feat: add bangumi metadata token settings"
```

### Task 2: Add the Bangumi HTTP client with anonymous and bearer-token modes

**Files:**
- Create: `src/atv_player/metadata/providers/bangumi_client.py`
- Create: `tests/test_metadata_bangumi_client.py`

- [ ] **Step 1: Write the failing Bangumi client tests**

```python
import httpx

from atv_player.metadata.providers.bangumi_client import BangumiClient


def test_bangumi_client_search_subjects_sends_user_agent_without_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        assert request.url.path == "/v0/search/subjects"
        return httpx.Response(200, json={"data": [{"id": 1, "name": "葬送的芙莉莲"}]})

    client = BangumiClient(transport=httpx.MockTransport(handler))

    rows = client.search_subjects("葬送的芙莉莲")

    assert rows == [{"id": 1, "name": "葬送的芙莉莲"}]
    assert seen["path"] == "/v0/search/subjects"
    assert "authorization" not in {key.lower() for key in seen["headers"]}
    assert "User-Agent" in seen["headers"]


def test_bangumi_client_get_subject_uses_bearer_token_when_configured() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"id": 42, "name": "少女乐队的呐喊"})

    client = BangumiClient(access_token="bgm-token", transport=httpx.MockTransport(handler))

    subject = client.get_subject("42")

    assert subject["id"] == 42
    assert seen["path"] == "/v0/subjects/42"
    assert seen["authorization"] == "Bearer bgm-token"
```

- [ ] **Step 2: Run the focused Bangumi client tests and verify they fail**

Run: `uv run pytest tests/test_metadata_bangumi_client.py -q`

Expected: FAIL with `ModuleNotFoundError` because `bangumi_client.py` does not exist yet.

- [ ] **Step 3: Create the minimal Bangumi client implementation**

```python
from __future__ import annotations

from typing import Any

import httpx


class BangumiClient:
    _BASE_URL = "https://api.bgm.tv"
    _USER_AGENT = "ATVPlayer/1.0 (https://github.com/openai)"

    def __init__(self, access_token: str = "", transport: httpx.BaseTransport | None = None) -> None:
        self._access_token = str(access_token or "").strip()
        self._client = httpx.Client(base_url=self._BASE_URL, transport=transport, timeout=10.0)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self._USER_AGENT}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _get_json(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, Any] | list[Any]:
        response = self._client.get(path, params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def search_subjects(self, keyword: str) -> list[dict[str, object]]:
        payload = self._get_json("/v0/search/subjects", params={"keyword": keyword, "type": 2})
        return list((payload or {}).get("data") or [])

    def get_subject(self, subject_id: int | str) -> dict[str, object]:
        return dict(self._get_json(f"/v0/subjects/{subject_id}"))

    def get_subject_persons(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self._get_json(f"/v0/subjects/{subject_id}/persons"))

    def get_subject_characters(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self._get_json(f"/v0/subjects/{subject_id}/characters"))

    def get_episodes(self, subject_id: int | str) -> list[dict[str, object]]:
        payload = self._get_json("/v0/episodes", params={"subject_id": subject_id, "type": 0})
        return list((payload or {}).get("data") or [])
```

- [ ] **Step 4: Run the focused Bangumi client tests and verify they pass**

Run: `uv run pytest tests/test_metadata_bangumi_client.py -q`

Expected: PASS with the client auth-mode coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/bangumi_client.py tests/test_metadata_bangumi_client.py
git commit -m "feat: add bangumi metadata client"
```

### Task 3: Add `BangumiMetadataProvider` search, detail mapping, and merge priority rules

**Files:**
- Create: `src/atv_player/metadata/providers/bangumi.py`
- Create: `tests/test_metadata_bangumi_provider.py`
- Modify: `src/atv_player/metadata/providers/__init__.py`
- Modify: `src/atv_player/metadata/matching.py`
- Modify: `src/atv_player/metadata/merge.py`
- Modify: `tests/test_metadata_merge.py`

- [ ] **Step 1: Write the failing provider and merge tests**

```python
from atv_player.metadata.models import MetadataQuery, MetadataRecord
from atv_player.metadata.providers.bangumi import BangumiMetadataProvider, is_bangumi_anime_query
from atv_player.metadata.merge import merge_metadata_record
from atv_player.models import VodItem


class FakeBangumiClient:
    def __init__(self) -> None:
        self.search_rows: list[dict[str, object]] = []
        self.subject_detail: dict[str, object] = {}
        self.persons: list[dict[str, object]] = []
        self.characters: list[dict[str, object]] = []
        self.episodes: list[dict[str, object]] = []

    def search_subjects(self, keyword: str) -> list[dict[str, object]]:
        return list(self.search_rows)

    def get_subject(self, subject_id: int | str) -> dict[str, object]:
        return dict(self.subject_detail)

    def get_subject_persons(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.persons)

    def get_subject_characters(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.characters)

    def get_episodes(self, subject_id: int | str) -> list[dict[str, object]]:
        return list(self.episodes)


def test_is_bangumi_anime_query_uses_category_name_and_type_name() -> None:
    assert is_bangumi_anime_query(MetadataQuery(title="葬送的芙莉莲", category_name="动漫")) is True
    assert is_bangumi_anime_query(MetadataQuery(title="葬送的芙莉莲", type_name="番剧")) is True
    assert is_bangumi_anime_query(MetadataQuery(title="深空彼岸", category_name="电影")) is False


def test_bangumi_provider_search_matches_name_cn_and_aliases_for_anime() -> None:
    client = FakeBangumiClient()
    client.search_rows = [
        {
            "id": 1,
            "type": 2,
            "name": "Sousou no Frieren",
            "name_cn": "葬送的芙莉莲",
            "date": "2023-09-29",
            "infobox": [{"key": "别名", "value": "Frieren"}],
        }
    ]
    provider = BangumiMetadataProvider(client)

    matches = provider.search(MetadataQuery(title="葬送的芙莉莲", year="2023", category_name="动漫"))

    assert len(matches) == 1
    assert matches[0].provider == "bangumi"
    assert matches[0].provider_id == "subject:1"
    assert matches[0].title == "葬送的芙莉莲"


def test_merge_metadata_prefers_bangumi_text_fields_but_keeps_tmdb_poster() -> None:
    vod = VodItem(vod_id="v1", vod_name="旧标题", vod_pic="https://img.tmdb/poster.jpg")
    vod.metadata_field_sources["poster"] = "tmdb"
    bangumi = MetadataRecord(
        provider="bangumi",
        provider_id="subject:1",
        overview="Bangumi简介",
        actors=["种崎敦美"],
        genres=["动画", "奇幻"],
        poster="https://img.bgm/poster.jpg",
    )

    merge_metadata_record(vod, bangumi, provider_priority=["bangumi", "tmdb"])

    assert vod.vod_content == "Bangumi简介"
    assert vod.vod_actor == "种崎敦美"
    assert vod.type_name == "动画 / 奇幻"
    assert vod.vod_pic == "https://img.tmdb/poster.jpg"
```

- [ ] **Step 2: Run the focused provider and merge tests and verify they fail**

Run: `uv run pytest tests/test_metadata_bangumi_provider.py tests/test_metadata_merge.py -k "bangumi" -q`

Expected: FAIL because the provider, anime helper, and Bangumi merge priorities do not exist yet.

- [ ] **Step 3: Implement the minimal Bangumi provider and merge priority changes**

```python
def is_bangumi_anime_query(query: MetadataQuery) -> bool:
    values = f"{query.category_name} {query.type_name}".lower()
    return any(token in values for token in ("动漫", "动画", "番剧", "acg", "anime"))


class BangumiMetadataProvider:
    name = "bangumi"

    def __init__(self, client) -> None:
        self._client = client

    def can_enrich(self, context: MetadataContext) -> bool:
        return is_bangumi_anime_query(context.to_query())

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title or not is_bangumi_anime_query(candidate):
            return []
        rows = self._client.search_subjects(candidate.title)
        matches: list[MetadataMatch] = []
        for row in rows:
            if int(row.get("type") or 0) != 2:
                continue
            match = MetadataMatch(
                provider=self.name,
                provider_id=f"subject:{row['id']}",
                title=str(row.get("name_cn") or row.get("name") or "").strip(),
                year=str(row.get("date") or "")[:4],
                raw={"aliases": _subject_aliases(row), **dict(row)},
            )
            match.score = score_match(candidate, match)
            matches.append(match)
        return [item for item in sorted(matches, key=lambda item: item.score, reverse=True) if is_confident_match(item.score)]
```

```python
_FIELD_PROVIDER_PRIORITY["actors"] = ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"]
_FIELD_PROVIDER_PRIORITY["genres"] = ["bangumi", "iqiyi", "tmdb", "official_douban", "local_douban", "douban", "plugin"]
_OVERVIEW_PROVIDER_PRIORITY["bangumi"] = 2
```

- [ ] **Step 4: Run the focused provider and merge tests and verify they pass**

Run: `uv run pytest tests/test_metadata_bangumi_provider.py tests/test_metadata_merge.py -k "bangumi" -q`

Expected: PASS with Bangumi provider and merge-priority coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/bangumi.py src/atv_player/metadata/providers/__init__.py src/atv_player/metadata/matching.py src/atv_player/metadata/merge.py tests/test_metadata_bangumi_provider.py tests/test_metadata_merge.py
git commit -m "feat: add bangumi metadata provider"
```

### Task 4: Wire Bangumi into the app coordinator, hydrator, and scrape provider filtering

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Modify: `tests/test_metadata_hydrator.py`
- Modify: `tests/test_metadata_scrape_service.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing integration tests for provider wiring and scrape visibility**

```python
def test_app_coordinator_builds_bangumi_provider_without_token(monkeypatch, tmp_path) -> None:
    created: list[str] = []

    class FakeRepo:
        def __init__(self) -> None:
            self.config = AppConfig(
                metadata_enhancement_enabled=True,
                metadata_douban_cookie="",
                metadata_tmdb_api_key="",
                metadata_bangumi_access_token="",
            )

        def load_config(self) -> AppConfig:
            return self.config

    class RecordingBangumiClient:
        def __init__(self, access_token: str = "") -> None:
            created.append(access_token)

    class RecordingBangumiProvider:
        name = "bangumi"

        def __init__(self, client) -> None:
            self.client = client

    monkeypatch.setattr(app_module, "BangumiClient", RecordingBangumiClient, raising=False)
    monkeypatch.setattr(app_module, "BangumiMetadataProvider", RecordingBangumiProvider, raising=False)
    monkeypatch.setattr(app_module, "app_cache_dir", lambda: tmp_path / "app-cache")

    coordinator = AppCoordinator(FakeRepo())
    providers = coordinator._build_metadata_providers(
        api_client=object(),
        config=coordinator.repo.load_config(),
        source_kind="browse",
        raw_detail=None,
    )

    assert any(getattr(provider, "name", "") == "bangumi" for provider in providers)
    assert created == [""]


def test_metadata_scrape_service_hides_bangumi_for_non_anime_query(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(cache=cache, providers=[FakeProvider("bangumi"), FakeProvider("tmdb")])

    options = service.provider_options(MetadataQuery(title="深空彼岸", category_name="电影"))

    assert ("bangumi", "Bangumi") not in options
    assert ("tmdb", "TMDB") in options
```

- [ ] **Step 2: Run the focused coordinator and scrape tests and verify they fail**

Run: `uv run pytest tests/test_app.py tests/test_metadata_scrape_service.py tests/test_metadata_hydrator.py -k "bangumi" -q`

Expected: FAIL because Bangumi is not wired into the provider list and scrape options do not accept query-aware filtering.

- [ ] **Step 3: Implement the minimal app and scrape wiring**

```python
providers.append(BangumiMetadataProvider(BangumiClient(access_token=config.metadata_bangumi_access_token)))
providers.append(BilibiliMetadataProvider())
providers.append(IqiyiMetadataProvider())
providers.append(TencentMetadataProvider())
```

```python
def provider_options(self, query: MetadataQuery | None = None) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    for provider in self._providers:
        if provider.name == "bangumi" and query is not None and not is_bangumi_anime_query(query):
            continue
        options.append((provider.name, self._provider_label(provider.name)))
    return options
```

```python
provider_options = service.provider_options(
    MetadataQuery(
        title=self._metadata_scrape_default_title,
        year=self._metadata_scrape_default_year,
        category_name=str(self.session.vod.category_name or "").strip(),
        type_name=str(self.session.vod.type_name or "").strip(),
    )
)
```

- [ ] **Step 4: Run the focused coordinator and scrape tests and verify they pass**

Run: `uv run pytest tests/test_app.py tests/test_metadata_scrape_service.py tests/test_metadata_hydrator.py -k "bangumi" -q`

Expected: PASS with Bangumi provider construction and scrape filtering coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/app.py src/atv_player/metadata/scrape.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py tests/test_app.py
git commit -m "feat: wire bangumi into metadata flows"
```

### Task 5: Add Bangumi episode-title mapping and candidate priority

**Files:**
- Modify: `src/atv_player/metadata/episode_title_resolver.py`
- Modify: `src/atv_player/metadata/scrape.py`
- Modify: `tests/test_metadata_episode_title_resolver.py`
- Modify: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write the failing episode-title tests**

```python
def test_build_provider_episode_playlist_maps_bangumi_episode_names() -> None:
    vod = VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="bangumi",
        provider_id="subject:1",
        title="牧神记",
        year="2024",
        raw={
            "episodes": [
                {"sort": 1, "type": 0, "name_cn": "天黑别出门", "name": "Episode 1"},
                {"sort": 2, "type": 0, "name_cn": "我是霸体", "name": "Episode 2"},
            ]
        },
    )

    updated = build_provider_episode_playlist(
        vod,
        playlist,
        match,
        source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    )

    assert updated is not None
    assert [item.episode_display_title for item in updated] == ["第1集 天黑别出门", "第2集 我是霸体"]


def test_metadata_scrape_service_auto_search_prefers_bangumi_over_bilibili_tmdb_tencent_and_iqiyi(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bangumi = FakeProvider(
        "bangumi",
        matches=[
            MetadataMatch(
                provider="bangumi",
                provider_id="subject:1",
                title="牧神记",
                year="2024",
                raw={"episodes": [{"sort": 1, "type": 0, "name_cn": "天黑别出门"}]},
            )
        ],
    )
    service = MetadataScrapeService(cache=cache, providers=[bangumi, FakeProvider("bilibili"), FakeProvider("tmdb")])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
    )

    assert updated is not None
    assert updated[0].episode_title_source == "bangumi"
```

- [ ] **Step 2: Run the focused episode-title tests and verify they fail**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_scrape_service.py -k "bangumi" -q`

Expected: FAIL because `episode_title_resolver` has no Bangumi branch and the scrape service does not prefer Bangumi yet.

- [ ] **Step 3: Implement the minimal Bangumi episode-title support**

```python
METADATA_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "bangumi", "bilibili", "tmdb", "tencent", "iqiyi"]
```

```python
def _titles_by_index_for_provider(vod: VodItem, playlist: list[PlayItem], provider: str, raw: dict[str, object]) -> dict[int, str]:
    if provider == "bangumi":
        return _titles_by_index_for_bangumi(vod, playlist, raw)
    if provider == "tencent":
        return _titles_by_index_for_tencent(vod, playlist, raw)
```

```python
def _titles_by_index_for_bangumi(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for episode in raw.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        if int(episode.get("type") or 0) != 0:
            continue
        episode_number = int(episode.get("sort") or 0)
        episode_title = str(episode.get("name_cn") or episode.get("name") or "").strip()
        if episode_number > 0 and episode_title:
            titles_by_episode[episode_number] = episode_title
    return _map_episode_numbers_to_indices(vod, playlist, titles_by_episode)
```

```python
for provider_name in ("bangumi", "bilibili", "tmdb", "tencent", "iqiyi"):
    ...
```

- [ ] **Step 4: Run the focused episode-title tests and verify they pass**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_scrape_service.py -k "bangumi" -q`

Expected: PASS with Bangumi episode-title mapping and priority coverage green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/episode_title_resolver.py src/atv_player/metadata/scrape.py tests/test_metadata_episode_title_resolver.py tests/test_metadata_scrape_service.py
git commit -m "feat: prefer bangumi episode titles for anime"
```

### Task 6: Run the focused end-to-end Bangumi metadata suite and clean up regressions

**Files:**
- Modify: `tests/test_app.py`
- Modify: `tests/test_metadata_hydrator.py`
- Modify: `tests/test_metadata_scrape_service.py`
- Modify: `tests/test_main_window_ui.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Add the final focused integration assertions**

```python
def test_metadata_hydrator_uses_bound_bangumi_record_for_anime(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    bindings = MetadataBindingRepository(tmp_path / "bindings.db")
    bindings.save("牧神记", "2024", provider="bangumi", provider_id="subject:1", matched_title="牧神记", matched_year="2024")

    class RecordingBangumiProvider:
        name = "bangumi"

        def can_enrich(self, _context) -> bool:
            return True

        def search(self, _candidate):
            return []

        def get_detail(self, _match):
            return MetadataRecord(provider="bangumi", provider_id="subject:1", overview="Bangumi简介", actors=["张三"])

    provider = RecordingBangumiProvider()
    hydrator = MetadataHydrator(cache=cache, providers=[provider], binding_repository=bindings)

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="牧神记", vod_year="2024", category_name="动漫"), source_kind="browse"))

    assert updated.vod_content == "Bangumi简介"
    assert updated.vod_actor == "张三"
```

- [ ] **Step 2: Run the focused Bangumi metadata suite and verify any failures**

Run: `uv run pytest tests/test_metadata_bangumi_client.py tests/test_metadata_bangumi_provider.py tests/test_metadata_merge.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py tests/test_metadata_episode_title_resolver.py tests/test_storage.py tests/test_main_window_ui.py tests/test_app.py -k "bangumi or bangumi_token" -q`

Expected: Either PASS or a small number of targeted failures caused by naming, provider ordering, or filter assumptions.

- [ ] **Step 3: Fix the minimal regressions discovered by the focused suite**

```python
_PROVIDER_LABELS = {
    "bangumi": "Bangumi",
    "bilibili": "B站",
    "tencent": "腾讯",
    "tmdb": "TMDB",
}
```

```python
if provider.name == "bangumi" and not is_bangumi_anime_query(query):
    continue
```

```python
providers = [
    CustomPluginProvider(plugin_payload),
    BangumiMetadataProvider(bangumi_client),
    BilibiliMetadataProvider(),
    IqiyiMetadataProvider(),
    TencentMetadataProvider(),
]
```

- [ ] **Step 4: Re-run the focused Bangumi metadata suite and verify it passes**

Run: `uv run pytest tests/test_metadata_bangumi_client.py tests/test_metadata_bangumi_provider.py tests/test_metadata_merge.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py tests/test_metadata_episode_title_resolver.py tests/test_storage.py tests/test_main_window_ui.py tests/test_app.py -k "bangumi or bangumi_token" -q`

Expected: PASS with the Bangumi-specific metadata coverage green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_app.py tests/test_metadata_hydrator.py tests/test_metadata_scrape_service.py tests/test_main_window_ui.py tests/test_storage.py
git commit -m "test: cover bangumi metadata integration"
```

## Self-Review

- Spec coverage:
  - Optional token config: Task 1 and Task 2
  - Anonymous and token request modes: Task 2
  - Anime-only activation: Task 3 and Task 4
  - Automatic hydration and manual scrape integration: Task 4 and Task 6
  - Bangumi merge priority and text-field preference: Task 3
  - Anime episode-title enhancement: Task 5
- Placeholder scan:
  - No `TBD`, `TODO`, or “similar to previous task” placeholders remain.
- Type consistency:
  - New config field is consistently named `metadata_bangumi_access_token`
  - New provider is consistently named `BangumiMetadataProvider`
  - New provider name string is consistently `bangumi`

## Notes

- Keep Bangumi anonymous-by-default. Do not gate provider construction on the token being present.
- Do not make Bangumi visible in scrape options for non-anime entries.
- Do not let Bangumi override an existing TMDB poster unless the merge rule is explicitly weaker for that field.
