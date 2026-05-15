# Metadata Hydration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an async player-detail metadata hydration pipeline for plugin and built-in remote detail sources, backed by new `alist-tvbox` metadata APIs, file-system caching, and provider-priority merges into the existing `VodItem` model.

**Architecture:** Add a new `atv_player.metadata` module with provider, cache, merge, and hydrator layers. Wire `OpenPlayerRequest` and `PlayerSession` with a dedicated `metadata_hydrator` callback, then have `PlayerWindow` run that callback once per session in the background and refresh poster/title/detail UI without restarting playback.

**Tech Stack:** Python 3.13, dataclasses, `httpx`, PySide6, existing Qt-threaded async signal pattern, pytest

---

### Task 1: Add metadata API client coverage for Douban search/detail

**Files:**
- Modify: `src/atv_player/api.py`
- Modify: `tests/test_api_client.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Write the failing API client tests**

```python
def test_metadata_douban_search_requests_backend_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"items": []})

    client = ApiClient(
        "http://127.0.0.1:4567",
        vod_token="Harold",
        transport=httpx.MockTransport(handler),
    )

    payload = client.search_douban_metadata("深空彼岸", year="2026")

    assert payload == {"items": []}
    assert seen == {
        "path": "/metadata/douban/search",
        "query": "title=%E6%B7%B1%E7%A9%BA%E5%BD%BC%E5%B2%B8&year=2026",
    }


def test_metadata_douban_detail_requests_backend_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"dbid": 35746415})

    client = ApiClient(
        "http://127.0.0.1:4567",
        vod_token="Harold",
        transport=httpx.MockTransport(handler),
    )

    payload = client.get_douban_metadata_detail(35746415)

    assert payload == {"dbid": 35746415}
    assert seen == {
        "path": "/metadata/douban/detail",
        "query": "dbid=35746415",
    }
```

- [ ] **Step 2: Run the focused API tests and verify they fail**

Run: `uv run pytest tests/test_api_client.py -k "metadata_douban_search or metadata_douban_detail" -v`

Expected: FAIL with `AttributeError` because `ApiClient` does not expose the new metadata methods yet.

- [ ] **Step 3: Add the new `ApiClient` methods**

```python
def search_douban_metadata(self, title: str, year: str = "") -> dict[str, Any]:
    params: dict[str, Any] = {"title": title}
    if year:
        params["year"] = year
    return self._request("GET", "/metadata/douban/search", params=params)


def get_douban_metadata_detail(self, dbid: int | str) -> dict[str, Any]:
    return self._request("GET", "/metadata/douban/detail", params={"dbid": dbid})
```

- [ ] **Step 4: Run the focused API tests and verify they pass**

Run: `uv run pytest tests/test_api_client.py -k "metadata_douban_search or metadata_douban_detail" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_client.py src/atv_player/api.py
git commit -m "feat: add metadata douban api client methods"
```

### Task 2: Add metadata core models and file-system cache utilities

**Files:**
- Create: `src/atv_player/metadata/__init__.py`
- Create: `src/atv_player/metadata/models.py`
- Create: `src/atv_player/metadata/cache.py`
- Create: `tests/test_metadata_cache.py`
- Test: `tests/test_metadata_cache.py`

- [ ] **Step 1: Write the failing metadata cache tests**

```python
from pathlib import Path

from atv_player.metadata.cache import MetadataCache
from atv_player.metadata.models import MetadataMatch, MetadataRecord


def test_metadata_cache_round_trips_search_results(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    match = MetadataMatch(
        provider="douban",
        provider_id="35746415",
        title="深空彼岸",
        year="2026",
        score=0.98,
        raw={"dbid": 35746415},
    )

    cache.save_search("douban", "深空彼岸", "2026", [match])
    loaded = cache.load_search("douban", "深空彼岸", "2026", ttl_seconds=86400)

    assert loaded is not None
    assert loaded[0].provider_id == "35746415"


def test_metadata_cache_round_trips_detail_records(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        title="深空彼岸",
        year="2026",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    cache.save_detail("douban", "35746415", record)
    loaded = cache.load_detail("douban", "35746415", ttl_seconds=86400)

    assert loaded is not None
    assert loaded.overview == "豆瓣简介"
    assert loaded.douban_id == 35746415
```

- [ ] **Step 2: Run the focused metadata cache tests and verify they fail**

Run: `uv run pytest tests/test_metadata_cache.py -v`

Expected: FAIL with `ModuleNotFoundError` because the metadata package does not exist yet.

- [ ] **Step 3: Create the metadata models and cache**

```python
@dataclass(slots=True)
class MetadataQuery:
    title: str
    year: str = ""
    source_kind: str = ""
    source_key: str = ""
    vod_id: str = ""
    vod_dbid: int = 0
    type_name: str = ""
    category_name: str = ""


@dataclass(slots=True)
class MetadataContext:
    vod: VodItem
    source_kind: str
    source_key: str = ""
    current_item: PlayItem | None = None
    raw_detail: Mapping[str, object] | None = None

    def to_query(self) -> MetadataQuery:
        return MetadataQuery(
            title=(self.vod.vod_name or "").strip(),
            year=(self.vod.vod_year or "").strip(),
            source_kind=self.source_kind,
            source_key=self.source_key,
            vod_id=(self.vod.vod_id or "").strip(),
            vod_dbid=int(self.vod.dbid or 0),
            type_name=(self.vod.type_name or "").strip(),
            category_name=(self.vod.category_name or "").strip(),
        )


@dataclass(slots=True)
class MetadataMatch:
    provider: str
    provider_id: str
    title: str
    year: str = ""
    score: float = 0.0
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MetadataRecord:
    provider: str
    provider_id: str
    title: str = ""
    original_title: str = ""
    year: str = ""
    poster: str = ""
    backdrop: str = ""
    overview: str = ""
    rating: str = ""
    actors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    season: str = ""
    episode: str = ""
    imdb_id: str = ""
    tmdb_id: str = ""
    douban_id: int = 0
    detail_fields: list[dict[str, object]] = field(default_factory=list)
```

```python
class MetadataCache:
    def __init__(self, cache_root: Path) -> None:
        self._root = Path(cache_root)

    def load_search(self, provider: str, title: str, year: str, ttl_seconds: int) -> list[MetadataMatch] | None:
        payload = self._load_json(self._search_path(provider, title, year), ttl_seconds)
        if payload is None:
            return None
        return [MetadataMatch(**item) for item in payload.get("items", [])]

    def save_search(self, provider: str, title: str, year: str, matches: list[MetadataMatch]) -> None:
        self._save_json(
            self._search_path(provider, title, year),
            {"items": [asdict(match) for match in matches]},
        )

    def load_detail(self, provider: str, provider_id: str, ttl_seconds: int) -> MetadataRecord | None:
        payload = self._load_json(self._detail_path(provider, provider_id), ttl_seconds)
        if payload is None:
            return None
        return MetadataRecord(**payload)

    def save_detail(self, provider: str, provider_id: str, record: MetadataRecord) -> None:
        self._save_json(self._detail_path(provider, provider_id), asdict(record))
```

- [ ] **Step 4: Run the focused metadata cache tests and verify they pass**

Run: `uv run pytest tests/test_metadata_cache.py -v`

Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/__init__.py src/atv_player/metadata/models.py src/atv_player/metadata/cache.py tests/test_metadata_cache.py
git commit -m "feat: add metadata models and cache"
```

### Task 3: Add provider base classes, Douban provider, text cleanup, and merge rules

**Files:**
- Create: `src/atv_player/metadata/base.py`
- Create: `src/atv_player/metadata/providers/__init__.py`
- Create: `src/atv_player/metadata/providers/douban.py`
- Create: `src/atv_player/metadata/merge.py`
- Create: `tests/test_metadata_douban_provider.py`
- Create: `tests/test_metadata_merge.py`
- Test: `tests/test_metadata_douban_provider.py`
- Test: `tests/test_metadata_merge.py`

- [ ] **Step 1: Write the failing Douban provider and merge tests**

```python
def test_douban_provider_prefers_dbid_detail_lookup_before_search() -> None:
    api = FakeMetadataApiClient(
        detail_payload={"dbid": 35746415, "title": "深空彼岸", "intro": "豆瓣简介", "rating": "8.1"},
    )
    provider = DoubanProvider(api)
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸", dbid=35746415), source_kind="plugin")

    matches = provider.search(context.to_query())
    record = provider.get_detail(matches[0])

    assert record is not None
    assert record.douban_id == 35746415
    assert api.search_calls == []
    assert api.detail_calls == [35746415]


def test_douban_provider_cleans_fold_markers_and_prefers_douban_overview() -> None:
    api = FakeMetadataApiClient(
        search_payload={"items": [{"dbid": 35746415, "title": "深空彼岸", "year": "2026"}]},
        detail_payload={
            "dbid": 35746415,
            "title": "深空彼岸",
            "intro": "豆瓣简介[展开全部] 豆瓣简介[收起部分]",
            "rating": "8.1",
        },
    )
    provider = DoubanProvider(api)
    context = MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="plugin")

    matches = provider.search(context.to_query())
    record = provider.get_detail(matches[0])

    assert record is not None
    assert record.overview == "豆瓣简介"


def test_merge_metadata_overrides_overview_with_douban_and_preserves_existing_title() -> None:
    vod = VodItem(vod_id="v1", vod_name="插件标题", vod_content="插件简介", vod_pic="poster.jpg")
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        title="豆瓣标题",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    merge_metadata_record(vod, record, provider_priority=["douban"])

    assert vod.vod_name == "插件标题"
    assert vod.vod_content == "豆瓣简介"
    assert vod.vod_remarks == "8.1"
    assert vod.dbid == 35746415


def test_merge_metadata_replaces_same_label_detail_field_and_appends_new_labels() -> None:
    vod = VodItem(
        vod_id="v1",
        vod_name="深空彼岸",
        detail_fields=[
            PlaybackDetailField(label="别名", value="插件别名"),
            PlaybackDetailField(label="IMDb ID", value="tt-old"),
        ],
    )
    record = MetadataRecord(
        provider="douban",
        provider_id="35746415",
        detail_fields=[
            {"label": "别名", "value": "豆瓣别名"},
            {"label": "TMDB ID", "value": "12345"},
        ],
    )

    merge_metadata_record(vod, record, provider_priority=["douban"])

    assert [(field.label, field.value) for field in vod.detail_fields] == [
        ("别名", "豆瓣别名"),
        ("IMDb ID", "tt-old"),
        ("TMDB ID", "12345"),
    ]
```

- [ ] **Step 2: Run the focused provider and merge tests and verify they fail**

Run: `uv run pytest tests/test_metadata_douban_provider.py tests/test_metadata_merge.py -v`

Expected: FAIL because the provider base, Douban provider, and merge helpers do not exist yet.

- [ ] **Step 3: Add provider base, Douban provider, and merge helpers**

```python
class MetadataProvider(Protocol):
    name: str

    def can_enrich(self, context: MetadataContext) -> bool: ...
    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]: ...
    def get_detail(self, match: MetadataMatch) -> MetadataRecord: ...
```

```python
def clean_overview_text(value: str) -> str:
    cleaned = str(value or "")
    cleaned = cleaned.replace("[展开全部]", " ").replace("[收起部分]", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"(?<=[。！？])\s+", cleaned)
    deduped: list[str] = []
    for part in parts:
        normalized = part.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return "".join(deduped)
```

```python
class DoubanProvider:
    name = "douban"

    def __init__(self, api_client, cache: MetadataCache | None = None) -> None:
        self._api_client = api_client
        self._cache = cache

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if candidate.vod_dbid:
            return [
                MetadataMatch(
                    provider=self.name,
                    provider_id=str(candidate.vod_dbid),
                    title=candidate.title,
                    year=candidate.year,
                )
            ]
        if not candidate.title:
            return []
        payload = self._api_client.search_douban_metadata(candidate.title, year=candidate.year)
        items = payload.get("items") or []
        return [
            MetadataMatch(
                provider=self.name,
                provider_id=str(item.get("dbid") or item.get("id") or "").strip(),
                title=str(item.get("title") or ""),
                year=str(item.get("year") or ""),
                score=float(item.get("score") or 0.0),
                raw=dict(item),
            )
            for item in items
            if str(item.get("dbid") or item.get("id") or "").strip()
        ]

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        return self._record_from_detail(
            self._api_client.get_douban_metadata_detail(match.provider_id)
        )
```

```python
def merge_metadata_record(vod: VodItem, record: MetadataRecord, provider_priority: list[str]) -> VodItem:
    if not vod.vod_name and record.title:
        vod.vod_name = record.title
    if not vod.vod_pic and record.poster:
        vod.vod_pic = record.poster
    if not vod.vod_year and record.year:
        vod.vod_year = record.year
    if not vod.vod_actor and record.actors:
        vod.vod_actor = ",".join(record.actors)
    if record.overview and clean_overview_text(record.overview):
        vod.vod_content = clean_overview_text(record.overview)
    if record.rating:
        vod.vod_remarks = record.rating
    if not vod.dbid and record.douban_id:
        vod.dbid = record.douban_id
    if record.detail_fields:
        existing = {field.label: field for field in vod.detail_fields}
        merged: list[PlaybackDetailField] = []
        seen_labels: set[str] = set()
        for field in vod.detail_fields:
            replacement = next((item for item in record.detail_fields if item.get("label") == field.label), None)
            if replacement is not None:
                merged.append(PlaybackDetailField(label=field.label, value=str(replacement.get("value") or "")))
                seen_labels.add(field.label)
                continue
            merged.append(field)
            seen_labels.add(field.label)
        for item in record.detail_fields:
            label = str(item.get("label") or "").strip()
            if label and label not in seen_labels:
                merged.append(PlaybackDetailField(label=label, value=str(item.get("value") or "")))
                seen_labels.add(label)
        vod.detail_fields = merged
    return vod
```

- [ ] **Step 4: Run the focused provider and merge tests and verify they pass**

Run: `uv run pytest tests/test_metadata_douban_provider.py tests/test_metadata_merge.py -v`

Expected: PASS with all selected tests green.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/base.py src/atv_player/metadata/providers/__init__.py src/atv_player/metadata/providers/douban.py src/atv_player/metadata/merge.py tests/test_metadata_douban_provider.py tests/test_metadata_merge.py
git commit -m "feat: add douban metadata provider and merge rules"
```

### Task 4: Add plugin metadata provider and request wiring

**Files:**
- Create: `src/atv_player/metadata/providers/plugin.py`
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `src/atv_player/models.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing plugin metadata tests**

```python
def test_spider_plugin_request_exposes_metadata_hydrator_for_detail_sessions() -> None:
    controller = SpiderPluginController(FakeSpider(), "插件", metadata_hydrator_factory=lambda **_: object())

    request = controller.build_request("/detail/1")

    assert request.metadata_hydrator is not None


def test_plugin_metadata_provider_maps_custom_metadata_payload() -> None:
    payload = {
        "title": "插件标题",
        "overview": "插件简介",
        "rating": "9.3",
        "imdb_id": "tt1234567",
        "detail_fields": [{"label": "别名", "value": "深空彼岸"}],
    }

    record = CustomPluginProvider().record_from_payload(payload)

    assert record.title == "插件标题"
    assert record.overview == "插件简介"
    assert record.rating == "9.3"
    assert record.imdb_id == "tt1234567"
```

- [ ] **Step 2: Run the focused plugin metadata tests and verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "metadata_hydrator or custom_metadata_payload" -v`

Expected: FAIL because `OpenPlayerRequest` and `SpiderPluginController` do not support metadata hydrators yet.

- [ ] **Step 3: Add `metadata_hydrator` to `OpenPlayerRequest` and implement plugin provider plumbing**

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
    source_kind: str = "browse"
    source_key: str = ""
    source_mode: str = ""
    source_path: str = ""
    source_vod_id: str = ""
    source_clicked_vod_id: str = ""
    detail_resolver: Callable[[PlayItem], VodItem | None] | None = None
    resolved_vod_by_id: dict[str, VodItem] = field(default_factory=dict)
    use_local_history: bool = True
    restore_history: bool = False
    playback_loader: Callable[..., PlaybackLoadResult | None] | None = None
    async_playback_loader: bool = False
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None
    detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None
    metadata_hydrator: Callable[[object], VodItem | None] | None = None
    danmaku_controller: object | None = None
    playback_progress_reporter: Callable[[PlayItem, int, bool], None] | None = None
    playback_stopper: Callable[[PlayItem], None] | None = None
    playback_history_loader: Callable[[], HistoryRecord | None] | None = None
    playback_history_saver: Callable[[dict[str, object]], None] | None = None
    initial_log_message: str = ""
    is_placeholder: bool = False
```

```python
class CustomPluginProvider:
    name = "plugin"

    def record_from_payload(self, payload: Mapping[str, object]) -> MetadataRecord:
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or ""),
            title=str(payload.get("title") or ""),
            overview=str(payload.get("overview") or ""),
            rating=str(payload.get("rating") or ""),
            imdb_id=str(payload.get("imdb_id") or ""),
            tmdb_id=str(payload.get("tmdb_id") or ""),
            detail_fields=list(payload.get("detail_fields") or []),
        )
```

```python
return OpenPlayerRequest(
    vod=detail,
    playlist=playlist,
    playlists=playlists,
    playlist_index=0,
    source_groups=source_groups,
    source_group_index=0,
    source_index=0,
    clicked_index=0,
    source_kind="plugin",
    source_mode="detail",
    source_vod_id=source_vod_id,
    use_local_history=False,
    playback_loader=playback_loader,
    async_playback_loader=True,
    metadata_hydrator=None if self._metadata_hydrator_factory is None else self._metadata_hydrator_factory(
        source_kind="plugin",
        source_key=self._plugin_name,
        vod=detail,
        raw_detail=raw_detail,
    ),
    detail_action_runner=detail_action_runner,
    danmaku_controller=self if self._danmaku_enabled and self._danmaku_service is not None else None,
    playback_history_loader=history_loader,
    playback_history_saver=history_saver,
)
```

- [ ] **Step 4: Run the focused plugin metadata tests and verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "metadata_hydrator or custom_metadata_payload" -v`

Expected: PASS with both selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/models.py src/atv_player/metadata/providers/plugin.py src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: wire plugin metadata provider into player requests"
```

### Task 5: Add metadata hydrator service and wire built-in remote requests

**Files:**
- Create: `src/atv_player/metadata/hydrator.py`
- Modify: `src/atv_player/controllers/player_controller.py`
- Modify: `src/atv_player/ui/main_window.py`
- Modify: `tests/test_main_window_ui.py`
- Create: `tests/test_metadata_hydrator.py`
- Test: `tests/test_metadata_hydrator.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing hydrator and request-wiring tests**

```python
def test_metadata_hydrator_uses_douban_when_plugin_provider_returns_no_overview(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    plugin_provider = FakeProvider("plugin", record=MetadataRecord(provider="plugin", provider_id="p1", title="插件标题"))
    douban_provider = FakeProvider("douban", record=MetadataRecord(provider="douban", provider_id="d1", overview="豆瓣简介", rating="8.1"))
    hydrator = MetadataHydrator(cache=cache, providers=[plugin_provider, douban_provider])
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_content="插件简介")

    updated = hydrator.hydrate(MetadataContext(vod=vod, source_kind="plugin"))

    assert updated.vod_content == "豆瓣简介"
    assert updated.vod_remarks == "8.1"


def test_metadata_hydrator_uses_cached_detail_without_recrawling(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    cache.save_detail(
        "douban",
        "35746415",
        MetadataRecord(provider="douban", provider_id="35746415", overview="缓存简介", rating="8.1"),
    )
    douban_provider = FakeProvider(
        "douban",
        matches=[MetadataMatch(provider="douban", provider_id="35746415", title="深空彼岸")],
        record=MetadataRecord(provider="douban", provider_id="35746415", overview="不应命中", rating="9.9"),
    )
    hydrator = MetadataHydrator(cache=cache, providers=[douban_provider])

    updated = hydrator.hydrate(MetadataContext(vod=VodItem(vod_id="v1", vod_name="深空彼岸"), source_kind="browse"))

    assert updated.vod_content == "缓存简介"
    assert douban_provider.get_detail_calls == []


def test_main_window_prepares_metadata_hydrator_for_browse_request(qtbot) -> None:
    window = make_main_window(qtbot, metadata_hydrator_factory=lambda **_: object())
    request = OpenPlayerRequest(
        vod=VodItem(vod_id="v1", vod_name="Movie"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4")],
        clicked_index=0,
        source_kind="browse",
        source_mode="detail",
        source_vod_id="v1",
    )

    prepared = window._prepare_request_for_open(request)

    assert prepared.metadata_hydrator is not None
```

- [ ] **Step 2: Run the focused hydrator and main-window tests and verify they fail**

Run: `uv run pytest tests/test_metadata_hydrator.py tests/test_main_window_ui.py -k "metadata_hydrator or browse_request" -v`

Expected: FAIL because the hydrator service does not exist and `MainWindow` does not attach metadata hydrators.

- [ ] **Step 3: Implement the hydrator and request plumbing**

```python
class MetadataHydrator:
    def __init__(self, cache: MetadataCache, providers: list[MetadataProvider]) -> None:
        self._cache = cache
        self._providers = providers

    def hydrate(self, context: MetadataContext) -> VodItem:
        vod = replace(context.vod)
        for provider in self._providers:
            if not provider.can_enrich(context):
                continue
            matches = provider.search(context.to_query())
            if not matches:
                continue
            cached = self._cache.load_detail(provider.name, matches[0].provider_id, ttl_seconds=7 * 24 * 3600)
            if cached is not None:
                merge_metadata_record(vod, cached, provider_priority=[item.name for item in self._providers])
                continue
            record = provider.get_detail(matches[0])
            self._cache.save_detail(provider.name, matches[0].provider_id, record)
            merge_metadata_record(vod, record, provider_priority=[item.name for item in self._providers])
        return vod
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
    opening_seconds: int = 0
    ending_seconds: int = 0
    detail_resolver: Callable[[PlayItem], VodItem | None] | None = None
    resolved_vod_by_id: dict[str, VodItem] = field(default_factory=dict)
    use_local_history: bool = True
    playback_loader: Callable[[PlayItem], PlaybackLoadResult | None] | None = None
    async_playback_loader: bool = False
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None
    detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None
    metadata_hydrator: Callable[[object], VodItem | None] | None = None
    metadata_hydrated: bool = False
    danmaku_controller: object | None = None
    playback_progress_reporter: Callable[[PlayItem, int, bool], None] | None = None
    playback_stopper: Callable[[PlayItem], None] | None = None
    playback_history_saver: Callable[[dict[str, object]], None] | None = None
    initial_log_message: str = ""
    is_placeholder: bool = False
    video_cover_override: str = ""
    prefetched_next_danmaku_indices: set[int] = field(default_factory=set)
    pending_next_danmaku_prefetch_token: int = 0
```

```python
def _prepare_request_for_open(self, request: OpenPlayerRequest) -> OpenPlayerRequest:
    if request.metadata_hydrator is None and request.source_kind in {"browse", "plugin", "emby", "jellyfin", "feiniu", "bilibili"}:
        request.metadata_hydrator = self._build_metadata_hydrator_for_request(request)
    return request
```

- [ ] **Step 4: Run the focused hydrator and main-window tests and verify they pass**

Run: `uv run pytest tests/test_metadata_hydrator.py tests/test_main_window_ui.py -k "metadata_hydrator or browse_request" -v`

Expected: PASS with all selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/hydrator.py src/atv_player/controllers/player_controller.py src/atv_player/ui/main_window.py tests/test_metadata_hydrator.py tests/test_main_window_ui.py
git commit -m "feat: add metadata hydrator service and request wiring"
```

### Task 6: Add player-window async metadata hydration with stale-result protection

**Files:**
- Modify: `src/atv_player/ui/player_window.py`
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing player-window metadata hydration tests**

```python
def test_player_window_async_metadata_hydration_refreshes_metadata_without_reloading_video(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4", vod_id="ep1")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        metadata_hydrator=lambda session: VodItem(
            vod_id=session.vod.vod_id,
            vod_name=session.vod.vod_name,
            vod_content="豆瓣简介",
            vod_remarks="8.1",
        ),
    )

    window.open_session(session)

    qtbot.waitUntil(lambda: "豆瓣简介" in window.metadata_view.toPlainText(), timeout=1000)
    assert window.video.load_calls == [("https://media.example/1.mp4", False, 0, {})]
    assert "评分: 8.1" in window.metadata_view.toPlainText()


def test_player_window_ignores_stale_metadata_hydration_results(qtbot) -> None:
    ready = threading.Event()
    session = PlayerSession(
        vod=VodItem(vod_id="v1", vod_name="原始标题", vod_content="原始简介"),
        playlist=[PlayItem(title="第1集", url="https://media.example/1.mp4", vod_id="ep1")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )

    def hydrate(session: PlayerSession) -> VodItem:
        assert ready.wait(timeout=1)
        return VodItem(vod_id=session.vod.vod_id, vod_name="旧结果", vod_content="旧简介")

    session.metadata_hydrator = hydrate
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = RecordingVideo()

    window.open_session(session)
    window.session = PlayerSession(
        vod=VodItem(vod_id="v2", vod_name="新会话"),
        playlist=[PlayItem(title="第1集", url="https://media.example/2.mp4", vod_id="ep2")],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    ready.set()

    qtbot.wait(100)
    assert "旧简介" not in window.metadata_view.toPlainText()
```

- [ ] **Step 2: Run the focused player-window tests and verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_hydration_refreshes_metadata or stale_metadata_hydration_results" -v`

Expected: FAIL because `PlayerWindow` has no metadata hydration pipeline yet.

- [ ] **Step 3: Implement the dedicated async metadata hydration path**

```python
class _MetadataHydrationSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)
```

```python
def _start_metadata_hydration(self) -> None:
    if self.session is None or self.session.metadata_hydrator is None or self.session.metadata_hydrated:
        return
    self._metadata_request_id += 1
    request_id = self._metadata_request_id
    session = self.session
    session.metadata_hydrated = True

    def run() -> None:
        try:
            updated_vod = session.metadata_hydrator(session)
        except Exception as exc:
            if self._is_window_alive():
                self._metadata_hydration_signals.failed.emit(request_id, str(exc))
            return
        if self._is_window_alive():
            self._metadata_hydration_signals.succeeded.emit(request_id, updated_vod)

    threading.Thread(target=run, daemon=True).start()
```

```python
def _handle_metadata_hydration_succeeded(self, request_id: int, updated_vod: VodItem) -> None:
    if request_id != self._metadata_request_id:
        return
    if self.session is None:
        return
    self.session.vod = updated_vod
    self._render_poster()
    self._render_metadata()
    self._render_detail_fields()
    self._refresh_window_title()
    self._append_log("元数据已更新: 简介 / 评分 / 扩展字段")
```

Call it from `open_session()` after initial render and before playback starts:

```python
self._render_poster()
self._render_metadata()
self._render_detail_fields()
self._start_metadata_hydration()
```

- [ ] **Step 4: Run the focused player-window tests and verify they pass**

Run: `uv run pytest tests/test_player_window_ui.py -k "metadata_hydration_refreshes_metadata or stale_metadata_hydration_results" -v`

Expected: PASS with both selected tests.

- [ ] **Step 5: Run the broader verification suite**

Run: `uv run pytest tests/test_api_client.py tests/test_metadata_cache.py tests/test_metadata_douban_provider.py tests/test_metadata_merge.py tests/test_metadata_hydrator.py tests/test_spider_plugin_controller.py tests/test_main_window_ui.py tests/test_player_window_ui.py -q`

Expected: PASS with no failures.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/player_window.py tests/test_player_window_ui.py
git commit -m "feat: add async player metadata hydration"
```

### Task 7: Final cleanup for provider registration and package exports

**Files:**
- Modify: `src/atv_player/metadata/__init__.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_metadata_hydrator.py`
- Test: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write the failing registration tests**

```python
def test_main_window_metadata_hydrator_factory_orders_plugin_before_douban(qtbot) -> None:
    window = make_main_window(qtbot)

    providers = window._build_metadata_providers_for_source("plugin")

    assert [provider.name for provider in providers] == ["plugin", "douban"]


def test_main_window_metadata_hydrator_factory_uses_only_douban_for_browse(qtbot) -> None:
    window = make_main_window(qtbot)

    providers = window._build_metadata_providers_for_source("browse")

    assert [provider.name for provider in providers] == ["douban"]
```

- [ ] **Step 2: Run the focused registration tests and verify they fail**

Run: `uv run pytest tests/test_metadata_hydrator.py tests/test_main_window_ui.py -k "orders_plugin_before_douban or uses_only_douban_for_browse" -v`

Expected: FAIL because provider registration helpers do not exist yet.

- [ ] **Step 3: Finalize registration helpers and exports**

```python
def _build_metadata_providers_for_source(self, source_kind: str) -> list[MetadataProvider]:
    douban = DoubanProvider(self.api_client, MetadataCache(app_cache_dir() / "metadata"))
    if source_kind == "plugin":
        return [CustomPluginProvider(), douban]
    if source_kind in {"browse", "emby", "jellyfin", "feiniu", "bilibili"}:
        return [douban]
    return []
```

```python
__all__ = [
    "MetadataCache",
    "MetadataContext",
    "MetadataHydrator",
    "MetadataMatch",
    "MetadataRecord",
]
```

- [ ] **Step 4: Run the focused registration tests and verify they pass**

Run: `uv run pytest tests/test_metadata_hydrator.py tests/test_main_window_ui.py -k "orders_plugin_before_douban or uses_only_douban_for_browse" -v`

Expected: PASS with both selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/__init__.py src/atv_player/ui/main_window.py tests/test_metadata_hydrator.py tests/test_main_window_ui.py
git commit -m "feat: finalize metadata provider registration"
```
