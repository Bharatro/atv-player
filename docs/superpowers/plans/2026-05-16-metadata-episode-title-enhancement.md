# Metadata Episode Title Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared Tencent/iQiyi/TMDB episode-title enhancement so plugin playback auto-enhancement and manual metadata scrape apply both rewrite playlist titles with the priority `tencent > iqiyi > tmdb`, while manual apply prefers the currently selected provider first.

**Architecture:** Extract a shared metadata episode-title resolver that can turn provider search hits or scrape candidates into an updated playlist using existing `infer_playlist_episode_number()` and `apply_episode_title_index_map()`. Keep metadata field updates in `MetadataScrapeService` and `PlayerWindow`, but route all playlist title rewriting through the shared resolver so auto-enhancement and manual-apply use the same provider-specific parsing and fallback rules.

**Tech Stack:** Python, `httpx`, pytest, existing metadata providers, `PlayItem`/`VodItem`, Qt player window async update flow

---

### Task 1: Add the shared resolver tests first

**Files:**
- Create: `tests/test_metadata_episode_title_resolver.py`
- Modify: `tests/test_metadata_tencent_provider.py`
- Modify: `tests/test_metadata_iqiyi_provider.py`
- Test: `tests/test_metadata_episode_title_resolver.py`

- [ ] **Step 1: Write failing resolver tests for Tencent and iQiyi title extraction**

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
)
from atv_player.metadata.models import MetadataMatch
from atv_player.models import PlayItem, VodItem


def test_build_provider_episode_playlist_prefers_tencent_episode_info_list() -> None:
    vod = VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", category_name="少儿")
    playlist = [
        PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4"),
        PlayItem(title="02.mp4", original_title="02.mp4", url="http://m/2.mp4"),
    ]
    match = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="米小圈上学记4",
        year="2026",
        raw={
            "title": "米小圈上学记4",
            "episode_sites": [
                {"episodeInfoList": [{"title": "第01话 金银米小圈1"}, {"title": "第02话 金银米小圈2"}]}
            ],
        },
    )

    updated = build_provider_episode_playlist(vod, playlist, match, source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY)

    assert updated is not None
    assert [item.episode_display_title for item in updated] == [
        "第1集 第01话 金银米小圈1",
        "第2集 第02话 金银米小圈2",
    ]


def test_build_provider_episode_playlist_maps_iqiyi_videos_for_multi_season_playlist() -> None:
    vod = VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧")
    playlist = [PlayItem(title="S05E01.mkv", original_title="S05E01.mkv", url="http://m/501.mp4")]
    match = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="黑袍纠察队 第五季",
        year="2026",
        raw={
            "title": "黑袍纠察队 第五季",
            "videos": [{"itemNumber": 1, "itemTitle": "终局开篇"}],
        },
    )

    updated = build_provider_episode_playlist(vod, playlist, match, source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY)

    assert updated is not None
    assert updated[0].episode_display_title == "第1集 终局开篇"
```

- [ ] **Step 2: Add failing provider-level raw-data tests for stored episode lists**

```python
def test_tencent_metadata_provider_search_preserves_episode_sites_in_raw() -> None:
    provider = TencentMetadataProvider(post=fake_post)
    match = provider.search(MetadataQuery(title="米小圈上学记4"))[0]

    assert "episode_sites" in match.raw
    assert match.raw["episode_sites"][0]["episodeInfoList"][0]["title"] == "第01话 金银米小圈1"


def test_iqiyi_metadata_provider_search_preserves_album_videos_in_raw() -> None:
    provider = IqiyiMetadataProvider(get=fake_get)
    match = provider.search(MetadataQuery(title="黑袍纠察队第五季"))[0]

    assert match.raw["videos"][0]["itemTitle"] == "终局开篇"
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py -q`

Expected: FAIL because `metadata.episode_title_resolver` does not exist yet and provider raw payloads do not preserve the resolver-facing episode list shape.

- [ ] **Step 4: Commit the red tests**

```bash
git add tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py
git commit -m "test: cover metadata episode title resolver"
```

### Task 2: Implement the shared metadata episode-title resolver

**Files:**
- Create: `src/atv_player/metadata/episode_title_resolver.py`
- Modify: `src/atv_player/metadata/providers/tencent.py`
- Modify: `src/atv_player/metadata/providers/iqiyi.py`
- Modify: `src/atv_player/metadata/__init__.py`
- Test: `tests/test_metadata_episode_title_resolver.py`

- [ ] **Step 1: Write the minimal resolver module**

```python
from __future__ import annotations

from dataclasses import replace

from atv_player.controllers.browse_controller import infer_playlist_episode_number
from atv_player.episode_titles import apply_episode_title_index_map, extract_season_number, playlist_has_title_variants, seed_original_titles
from atv_player.models import PlayItem, VodItem

METADATA_EPISODE_TITLE_SOURCE_PRIORITY = ["plugin", "tencent", "iqiyi", "tmdb"]


def build_provider_episode_playlist(vod: VodItem, playlist: list[PlayItem], candidate, *, source_priority: list[str]) -> list[PlayItem] | None:
    provider = str(getattr(candidate, "provider", "") or "")
    raw = dict(getattr(candidate, "raw", {}) or {})
    copied = seed_original_titles([replace(item) for item in playlist])
    titles_by_index = _titles_by_index_for_provider(vod, copied, provider, raw)
    if not titles_by_index:
        return None
    apply_episode_title_index_map(copied, titles_by_index, source=provider, source_priority=source_priority)
    return copied if playlist_has_title_variants(copied) else None
```

- [ ] **Step 2: Implement Tencent episode list normalization in the resolver**

```python
def _titles_by_index_for_tencent(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    episode_rows: list[str] = []
    for site in raw.get("episode_sites") or []:
        if not isinstance(site, dict):
            continue
        for episode in site.get("episodeInfoList") or []:
            if not isinstance(episode, dict):
                continue
            title = str(episode.get("title") or "").strip()
            if title:
                episode_rows.append(title)
    titles_by_index: dict[int, str] = {}
    for index, item in enumerate(playlist):
        episode_number = infer_playlist_episode_number(item, playlist)
        if episode_number is None or episode_number <= 0 or episode_number > len(episode_rows):
            continue
        titles_by_index[index] = f"第{episode_number}集 {episode_rows[episode_number - 1]}"
    return titles_by_index
```

- [ ] **Step 3: Implement iQiyi episode list normalization in the resolver**

```python
def _titles_by_index_for_iqiyi(vod: VodItem, playlist: list[PlayItem], raw: dict[str, object]) -> dict[int, str]:
    titles_by_episode: dict[int, str] = {}
    for video in raw.get("videos") or []:
        if not isinstance(video, dict):
            continue
        try:
            episode_number = int(video.get("itemNumber") or video.get("episodeNumber") or 0)
        except (TypeError, ValueError):
            continue
        episode_title = str(video.get("itemTitle") or video.get("title") or "").strip()
        if episode_number > 0 and episode_title:
            titles_by_episode[episode_number] = f"第{episode_number}集 {episode_title}"
    return _map_episode_numbers_to_indices(playlist, titles_by_episode)
```

- [ ] **Step 4: Preserve resolver-facing raw data in Tencent and iQiyi search matches**

```python
# src/atv_player/metadata/providers/tencent.py
return {
    "title": str(video_info.get("title") or "").strip(),
    "year": self._year_value(video_info),
    "overview": str(video_info.get("descrip") or "").strip(),
    "country": str(video_info.get("area") or "").strip(),
    "language": self._language_value(video_info.get("language")),
    "directors": self._string_list(video_info.get("directors")),
    "actors": self._string_list(video_info.get("actors")),
    "genres": self._genres(video_info),
    "site_name": self._site_name(video_info),
    "episode_sites": self._episode_sites(video_info),
    "provider_id": self._provider_id(video_info, doc),
}


# src/atv_player/metadata/providers/iqiyi.py
match = MetadataMatch(
    provider=self.name,
    provider_id=provider_id,
    title=match_title,
    year=self._year_value(album_info),
    raw={
        **dict(album_info),
        "videos": list(album_info.get("videos") or []),
    },
)
```

- [ ] **Step 5: Run the resolver/provider tests to verify they pass**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py -q`

Expected: PASS

- [ ] **Step 6: Commit the resolver implementation**

```bash
git add src/atv_player/metadata/episode_title_resolver.py src/atv_player/metadata/providers/tencent.py src/atv_player/metadata/providers/iqiyi.py src/atv_player/metadata/__init__.py tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py
git commit -m "feat: add metadata episode title resolver"
```

### Task 3: Switch plugin auto-enhancement from TMDB-only to shared provider fallback

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing auto-enhancement tests for provider priority and fallback**

```python
def test_app_coordinator_episode_title_enhancer_prefers_tencent_over_iqiyi_and_tmdb(tmp_path, monkeypatch) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(metadata_enhancement_enabled=True, metadata_tmdb_api_key="tmdb-key", episode_title_enhancement_enabled=True)

    class FakeSearchProvider:
        def __init__(self, provider_name: str, title: str) -> None:
            self.name = provider_name
            self._title = title

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [
                MetadataMatch(
                    provider=self.name,
                    provider_id=f"{self.name}:1",
                    title=candidate.title,
                    year=candidate.year,
                    raw=(
                        {"episode_sites": [{"episodeInfoList": [{"title": self._title}]}]}
                        if self.name == "tencent"
                        else {"videos": [{"itemNumber": 1, "itemTitle": self._title}]}
                    ),
                )
            ]

    class FakeTMDBClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "tmdb-key"

        def search_tv(self, title: str, year: str = "") -> list[dict[str, object]]:
            return [{"id": 42, "name": title, "first_air_date": "2026-01-01"}]

        def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, object]:
            return {"episodes": [{"episode_number": 1, "name": "TMDB标题"}]}

    monkeypatch.setattr(app_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(app_module, "TencentMetadataProvider", lambda: FakeSearchProvider("tencent", "第01话 金银米小圈1"), raising=False)
    monkeypatch.setattr(app_module, "IqiyiMetadataProvider", lambda: FakeSearchProvider("iqiyi", "终局开篇"), raising=False)
    monkeypatch.setattr(app_module, "TMDBClient", FakeTMDBClient, raising=False)

    coordinator = AppCoordinator(FakeRepo())
    enhance = coordinator._build_episode_title_enhancer_factory(object())(
        source_kind="plugin",
        vod=VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", category_name="少儿"),
    )

    updated = enhance(SimpleNamespace(vod=VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026"), playlist=[PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")]))

    assert updated is not None
    assert updated[0].episode_title_source == "tencent"
    assert updated[0].episode_display_title == "第1集 第01话 金银米小圈1"


def test_app_coordinator_episode_title_enhancer_falls_back_from_tencent_to_iqiyi(tmp_path, monkeypatch) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(metadata_enhancement_enabled=True, metadata_tmdb_api_key="tmdb-key", episode_title_enhancement_enabled=True)

    class EmptyTencentProvider:
        name = "tencent"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [MetadataMatch(provider="tencent", provider_id="tencent:1", title=candidate.title, year=candidate.year, raw={})]

    class FakeIqiyiProvider:
        name = "iqiyi"

        def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
            return [
                MetadataMatch(
                    provider="iqiyi",
                    provider_id="iqiyi:1",
                    title=candidate.title,
                    year=candidate.year,
                    raw={"videos": [{"itemNumber": 1, "itemTitle": "终局开篇"}]},
                )
            ]

    class FakeTMDBClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "tmdb-key"

        def search_tv(self, title: str, year: str = "") -> list[dict[str, object]]:
            return [{"id": 42, "name": title, "first_air_date": "2026-01-01"}]

        def get_tv_season_detail(self, tmdb_id: str | int, season_number: int) -> dict[str, object]:
            return {"episodes": [{"episode_number": 1, "name": "TMDB标题"}]}

    monkeypatch.setattr(app_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(app_module, "TencentMetadataProvider", EmptyTencentProvider, raising=False)
    monkeypatch.setattr(app_module, "IqiyiMetadataProvider", FakeIqiyiProvider, raising=False)
    monkeypatch.setattr(app_module, "TMDBClient", FakeTMDBClient, raising=False)

    coordinator = AppCoordinator(FakeRepo())
    enhance = coordinator._build_episode_title_enhancer_factory(object())(
        source_kind="plugin",
        vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
    )

    updated = enhance(
        SimpleNamespace(
            vod=VodItem(vod_id="v1", vod_name="黑袍纠察队第五季", vod_year="2026", category_name="电视剧"),
            playlist=[PlayItem(title="S05E01.mkv", original_title="S05E01.mkv", url="http://m/1.mp4")],
        )
    )

    assert updated is not None
    assert updated[0].episode_title_source == "iqiyi"
```

- [ ] **Step 2: Run the targeted app tests to verify they fail**

Run: `uv run pytest tests/test_app.py::test_app_coordinator_episode_title_enhancer_prefers_tencent_over_iqiyi_and_tmdb tests/test_app.py::test_app_coordinator_episode_title_enhancer_falls_back_from_tencent_to_iqiyi -q`

Expected: FAIL because `_build_episode_title_enhancer_factory()` still only uses TMDB.

- [ ] **Step 3: Replace the TMDB-only logic in `app.py` with shared resolver orchestration**

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
)


def _build_episode_title_enhancer_factory(self, api_client: ApiClient):
    del api_client
    cache = MetadataCache(app_cache_dir() / "metadata")

    def _search_metadata_candidates(vod: VodItem) -> list[object]:
        query = MetadataContext(vod=vod, source_kind="plugin").to_query()
        providers = [TencentMetadataProvider(), IqiyiMetadataProvider()]
        candidates: list[object] = []
        for provider in providers:
            try:
                matches = provider.search(query)
            except Exception:
                continue
            if matches:
                candidates.append(matches[0])
        return candidates

    def _enhance_from_tmdb(session_vod: VodItem, playlist: list[PlayItem]) -> list[PlayItem] | None:
        tmdb_client = TMDBClient(api_key=config.metadata_tmdb_api_key)
        season_playlist = _build_tmdb_titles(cache, tmdb_client, session_vod, playlist)
        return season_playlist if season_playlist is not None else None

    def _reorder_playlist_by_episode_numbers(playlist: list[PlayItem], session_vod: VodItem) -> list[PlayItem]:
        season_episode_pairs: list[tuple[int, int] | None] = []
        default_season = _guess_season_number(session_vod)
        for item in playlist:
            episode_number = infer_playlist_episode_number(item, playlist)
            if episode_number is None:
                season_episode_pairs.append(None)
                continue
            season_episode_pairs.append((extract_season_number(item.original_title) or default_season, episode_number))
        indexed_playlist = list(enumerate(playlist))
        indexed_playlist.sort(key=lambda entry: season_episode_pairs[entry[0]] or (_EPISODE_SORT_SENTINEL, _EPISODE_SORT_SENTINEL))
        return [item for _index, item in indexed_playlist]

    def enhance(session) -> list | None:
        session_vod = getattr(session, "vod", None) or vod
        current_playlist = list(getattr(session, "playlist", []) or [])
        if not current_playlist:
            return None
        playlist = seed_original_titles([replace(item) for item in current_playlist])
        for candidate in _search_metadata_candidates(session_vod):
            updated = build_provider_episode_playlist(session_vod, playlist, candidate, source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY)
            if updated is not None:
                return _reorder_playlist_by_episode_numbers(updated, session_vod)
        return _enhance_from_tmdb(session_vod, playlist)
```

- [ ] **Step 4: Run the focused app tests plus existing TMDB enhancer regression tests**

Run: `uv run pytest tests/test_app.py::test_app_coordinator_episode_title_enhancer_prefers_tencent_over_iqiyi_and_tmdb tests/test_app.py::test_app_coordinator_episode_title_enhancer_falls_back_from_tencent_to_iqiyi tests/test_app.py::test_app_coordinator_episode_title_enhancer_maps_shuffled_playlist_by_episode_marker tests/test_app.py::test_app_coordinator_episode_title_enhancer_maps_multi_season_playlist -q`

Expected: PASS

- [ ] **Step 5: Commit the auto-enhancement changes**

```bash
git add src/atv_player/app.py tests/test_app.py
git commit -m "feat: prefer metadata providers for episode titles"
```

### Task 4: Extend manual scrape apply to rewrite playlist titles

**Files:**
- Modify: `src/atv_player/metadata/scrape.py`
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_metadata_scrape_service.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write failing scrape-service and player-window tests for playlist title updates**

```python
def test_metadata_scrape_service_can_build_episode_title_playlist_for_selected_candidate(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = FakeProvider(
        "tencent",
        matches=[MetadataMatch(provider="tencent", provider_id="tx:1", title="米小圈上学记4", raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 金银米小圈1"}]}]})],
    )
    service = MetadataScrapeService(cache=cache, providers=[provider])

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026"),
        [PlayItem(title="01.mp4", original_title="01.mp4", url="http://m/1.mp4")],
        preferred_candidate=MetadataScrapeCandidate(provider="tencent", provider_label="腾讯", provider_id="tx:1", title="米小圈上学记4", year="2026", raw=provider.matches[0].raw),
    )

    assert updated is not None
    assert updated[0].episode_title_source == "tencent"


def test_player_window_metadata_scrape_apply_refreshes_playlist_titles_from_selected_provider(qtbot) -> None:
    service = FakeMetadataScrapeService()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="米小圈上学记4", vod_year="2026", vod_content="原始简介"),
        playlist=[PlayItem(title="01.mp4", original_title="01.mp4", url="https://media.example/1.mp4")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_scrape_service=service,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.open_session(session)
    window._open_metadata_scrape_dialog()
    window._metadata_scrape_groups = [
        MetadataScrapeGroup(
            provider="tencent",
            provider_label="腾讯",
            items=[
                MetadataScrapeCandidate(
                    provider="tencent",
                    provider_label="腾讯",
                    provider_id="tx:1",
                    title="米小圈上学记4",
                    year="2026",
                    raw={"episode_sites": [{"episodeInfoList": [{"title": "第01话 金银米小圈1"}]}]},
                )
            ],
        )
    ]
    window._populate_metadata_scrape_groups(window._metadata_scrape_groups)
    window._populate_metadata_scrape_results(0)
    window._apply_selected_metadata_scrape_result()
    qtbot.waitUntil(lambda: window.session.playlist[0].episode_display_title == "第1集 第01话 金银米小圈1", timeout=1000)
    assert window.playlist_title_mode == "episode"
```

- [ ] **Step 2: Run the targeted manual-apply tests to verify they fail**

Run: `uv run pytest tests/test_metadata_scrape_service.py::test_metadata_scrape_service_can_build_episode_title_playlist_for_selected_candidate tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_refreshes_playlist_titles_from_selected_provider -q`

Expected: FAIL because `MetadataScrapeService` has no playlist-title API and `PlayerWindow` does not update playlists on scrape apply.

- [ ] **Step 3: Add a shared playlist-title entry point to `MetadataScrapeService`**

```python
from atv_player.metadata.episode_title_resolver import (
    METADATA_EPISODE_TITLE_SOURCE_PRIORITY,
    build_provider_episode_playlist,
)


def build_episode_title_playlist(
    self,
    vod: VodItem,
    playlist: list[PlayItem],
    *,
    preferred_candidate: MetadataScrapeCandidate | None = None,
) -> list[PlayItem] | None:
    ordered_candidates: list[object] = []
    if preferred_candidate is not None:
        ordered_candidates.append(preferred_candidate)
    for provider_name in ("tencent", "iqiyi", "tmdb"):
        if preferred_candidate is not None and provider_name == preferred_candidate.provider:
            continue
        match = self._best_match_for_provider(vod, provider_name)
        if match is not None:
            ordered_candidates.append(match)
    for candidate in ordered_candidates:
        updated = build_provider_episode_playlist(vod, playlist, candidate, source_priority=METADATA_EPISODE_TITLE_SOURCE_PRIORITY)
        if updated is not None:
            return updated
    return None
```

- [ ] **Step 4: Update `PlayerWindow` apply success handling to reuse the existing playlist-refresh path**

```python
def _handle_metadata_scrape_apply_succeeded(self, request_id: int, updated_vod: VodItem, candidate) -> None:
    if request_id != self._metadata_scrape_request_id or self.session is None:
        return
    self._metadata_request_id += 1
    self._pending_metadata_session = None
    updated_playlist = None
    build_playlist = getattr(self.session.metadata_scrape_service, "build_episode_title_playlist", None)
    if callable(build_playlist):
        try:
            updated_playlist = build_playlist(updated_vod, self.session.playlist, preferred_candidate=candidate)
        except Exception as exc:
            self._append_log(f"剧集标题增强失败: {exc}")
    if updated_playlist is not None:
        self._episode_title_request_id += 1
        self._handle_episode_title_enhancement_succeeded(self._episode_title_request_id, updated_playlist)
```

- [ ] **Step 5: Run the targeted manual-apply tests plus existing scrape regressions**

Run: `uv run pytest tests/test_metadata_scrape_service.py tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_refreshes_metadata_and_saves_binding tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_refreshes_playlist_titles_from_selected_provider tests/test_player_window_ui.py::test_player_window_metadata_scrape_apply_replaces_current_item_detail_fields -q`

Expected: PASS

- [ ] **Step 6: Commit the manual-apply integration**

```bash
git add src/atv_player/metadata/scrape.py src/atv_player/ui/player_window.py tests/test_metadata_scrape_service.py tests/test_player_window_ui.py
git commit -m "feat: apply scraped episode titles to playlist"
```

### Task 5: Final verification

**Files:**
- Verify: `tests/test_metadata_episode_title_resolver.py`
- Verify: `tests/test_metadata_tencent_provider.py`
- Verify: `tests/test_metadata_iqiyi_provider.py`
- Verify: `tests/test_metadata_scrape_service.py`
- Verify: `tests/test_player_window_ui.py`
- Verify: `tests/test_app.py`

- [ ] **Step 1: Run the focused end-to-end verification suite**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py tests/test_metadata_scrape_service.py tests/test_app.py tests/test_player_window_ui.py -q`

Expected: PASS

- [ ] **Step 2: If any regression appears, fix it before proceeding**

Run: `uv run pytest <paste the first failing test from the previous step> -q`

Expected: reproduce exactly one failure, then patch only the touched files from Tasks 2-4 before rerunning the isolated test.

- [ ] **Step 3: Re-run the verification suite until green**

Run: `uv run pytest tests/test_metadata_episode_title_resolver.py tests/test_metadata_tencent_provider.py tests/test_metadata_iqiyi_provider.py tests/test_metadata_scrape_service.py tests/test_app.py tests/test_player_window_ui.py -q`

Expected: PASS
