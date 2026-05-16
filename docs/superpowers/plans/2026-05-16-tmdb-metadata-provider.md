# TMDB Metadata Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real `TMDBProvider` to the media-enhancement pipeline, split local and remote Douban into explicit providers, and enforce the final provider order `本地豆瓣 > TMDB > alist-tvbox豆瓣`.

**Architecture:** Keep the existing `MetadataHydrator` entry point, but replace the current implicit Douban fallback logic with an explicit provider chain: `LocalDoubanProvider`, optional `TMDBProvider`, and `RemoteDoubanProvider`. Upgrade metadata merging from a single provider-priority list to field-level priorities so Douban can keep control of overview/rating while TMDB supplies posters, backdrops, aliases, and IDs.

**Tech Stack:** Python 3.14, dataclasses, `httpx`, PySide6, pytest

---

## File Map

**Create:**
- `src/atv_player/metadata/providers/tmdb_client.py`
- `src/atv_player/metadata/providers/tmdb.py`
- `src/atv_player/metadata/providers/local_douban.py`
- `src/atv_player/metadata/providers/remote_douban.py`
- `tests/test_metadata_tmdb_client.py`
- `tests/test_metadata_tmdb_provider.py`
- `tests/test_metadata_douban_source_providers.py`

**Modify:**
- `src/atv_player/metadata/providers/__init__.py`
- `src/atv_player/metadata/merge.py`
- `src/atv_player/metadata/hydrator.py`
- `src/atv_player/app.py`
- `tests/test_metadata_merge.py`
- `tests/test_metadata_hydrator.py`
- `tests/test_app.py`

**Existing references to inspect while implementing:**
- `src/atv_player/metadata/models.py`
- `src/atv_player/metadata/providers/douban.py`
- `src/atv_player/metadata/providers/local_douban_client.py`
- `src/atv_player/api.py`

### Task 1: Add the TMDB HTTP client

**Files:**
- Create: `src/atv_player/metadata/providers/tmdb_client.py`
- Create: `tests/test_metadata_tmdb_client.py`
- Test: `tests/test_metadata_tmdb_client.py`

- [ ] **Step 1: Write the failing TMDB client tests**

```python
import httpx

from atv_player.metadata.providers.tmdb_client import TMDBClient


def test_tmdb_client_search_movie_sends_api_key_language_and_year() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        if request.url.path == "/3/search/movie":
            return httpx.Response(200, json={"results": [{"id": 1, "title": "深空彼岸"}]})
        raise AssertionError(request.url.path)

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    results = client.search_movie("深空彼岸", year="2026")

    assert results == [{"id": 1, "title": "深空彼岸"}]
    assert seen["path"] == "/3/search/movie"
    assert seen["query"] == {
        "api_key": "tmdb-key",
        "language": "zh-CN",
        "query": "深空彼岸",
        "year": "2026",
    }


def test_tmdb_client_get_movie_detail_appends_response_and_builds_image_urls() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/3/configuration":
            return httpx.Response(
                200,
                json={
                    "images": {
                        "secure_base_url": "https://image.tmdb.org/t/p/",
                        "poster_sizes": ["w185", "w500"],
                        "backdrop_sizes": ["w300", "w1280"],
                    }
                },
            )
        if request.url.path == "/3/movie/42":
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "title": "深空彼岸",
                    "poster_path": "/poster.jpg",
                    "backdrop_path": "/backdrop.jpg",
                    "external_ids": {"imdb_id": "tt123"},
                },
            )
        raise AssertionError(request.url.path)

    client = TMDBClient(api_key="tmdb-key", transport=httpx.MockTransport(handler))

    detail = client.get_movie_detail("42")

    assert detail["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert detail["backdrop_url"] == "https://image.tmdb.org/t/p/w1280/backdrop.jpg"
    assert detail["external_ids"] == {"imdb_id": "tt123"}
    assert calls == ["/3/configuration", "/3/movie/42"]
```

- [ ] **Step 2: Run the focused TMDB client tests and verify they fail**

Run: `uv run pytest tests/test_metadata_tmdb_client.py -q`

Expected: FAIL with `ModuleNotFoundError` because `tmdb_client.py` does not exist yet.

- [ ] **Step 3: Create the minimal TMDB client implementation**

```python
from __future__ import annotations

from typing import Any

import httpx


class TMDBClient:
    _BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = str(api_key or "").strip()
        self._client = httpx.Client(base_url=self._BASE_URL, transport=transport, timeout=20.0)
        self._image_config: dict[str, Any] | None = None

    def _request(self, path: str, **params: object) -> dict[str, Any]:
        query = {"api_key": self._api_key, "language": "zh-CN"}
        query.update({key: value for key, value in params.items() if value not in ("", None)})
        response = self._client.get(path, params=query)
        response.raise_for_status()
        return dict(response.json())

    def _image_base(self, kind: str) -> str:
        if self._image_config is None:
            self._image_config = self._request("/configuration").get("images") or {}
        sizes = list(self._image_config.get(f"{kind}_sizes") or [])
        size = sizes[-1] if sizes else "original"
        base = str(self._image_config.get("secure_base_url") or "https://image.tmdb.org/t/p/")
        return f"{base}{size}"

    def _with_image_urls(self, payload: dict[str, Any]) -> dict[str, Any]:
        detail = dict(payload)
        poster_path = str(detail.get("poster_path") or "").strip()
        backdrop_path = str(detail.get("backdrop_path") or "").strip()
        detail["poster_url"] = f"{self._image_base('poster')}{poster_path}" if poster_path else ""
        detail["backdrop_url"] = f"{self._image_base('backdrop')}{backdrop_path}" if backdrop_path else ""
        return detail

    def search_movie(self, title: str, year: str = "") -> list[dict[str, object]]:
        return list((self._request("/search/movie", query=title, year=year).get("results") or []))

    def search_tv(self, title: str, year: str = "") -> list[dict[str, object]]:
        return list((self._request("/search/tv", query=title, first_air_date_year=year).get("results") or []))

    def get_movie_detail(self, tmdb_id: str | int) -> dict[str, Any]:
        payload = self._request(
            f"/movie/{tmdb_id}",
            append_to_response="external_ids,images,alternative_titles,credits",
        )
        return self._with_image_urls(payload)

    def get_tv_detail(self, tmdb_id: str | int) -> dict[str, Any]:
        payload = self._request(
            f"/tv/{tmdb_id}",
            append_to_response="external_ids,images,alternative_titles,aggregate_credits",
        )
        return self._with_image_urls(payload)
```

- [ ] **Step 4: Run the focused TMDB client tests and verify they pass**

Run: `uv run pytest tests/test_metadata_tmdb_client.py -q`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/tmdb_client.py tests/test_metadata_tmdb_client.py
git commit -m "feat: add tmdb metadata client"
```

### Task 2: Add `TMDBProvider` with `category_name`-driven movie/tv inference

**Files:**
- Create: `src/atv_player/metadata/providers/tmdb.py`
- Create: `tests/test_metadata_tmdb_provider.py`
- Modify: `src/atv_player/metadata/providers/__init__.py`
- Test: `tests/test_metadata_tmdb_provider.py`

- [ ] **Step 1: Write the failing TMDB provider tests**

```python
from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.tmdb import TMDBProvider, infer_tmdb_media_type


class FakeTMDBClient:
    def __init__(self) -> None:
        self.movie_search_results: list[dict] = []
        self.tv_search_results: list[dict] = []
        self.movie_detail: dict = {}
        self.tv_detail: dict = {}
        self.calls: list[tuple[str, str, str]] = []

    def search_movie(self, title: str, year: str = "") -> list[dict]:
        self.calls.append(("search_movie", title, year))
        return list(self.movie_search_results)

    def search_tv(self, title: str, year: str = "") -> list[dict]:
        self.calls.append(("search_tv", title, year))
        return list(self.tv_search_results)

    def get_movie_detail(self, tmdb_id: str | int) -> dict:
        self.calls.append(("get_movie_detail", str(tmdb_id), ""))
        return dict(self.movie_detail)

    def get_tv_detail(self, tmdb_id: str | int) -> dict:
        self.calls.append(("get_tv_detail", str(tmdb_id), ""))
        return dict(self.tv_detail)


def test_infer_tmdb_media_type_uses_category_name() -> None:
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="电影")) == "movie"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="动漫")) == "tv"
    assert infer_tmdb_media_type(MetadataQuery(title="深空彼岸", category_name="")) == ""


def test_tmdb_provider_searches_movie_when_category_name_marks_movie() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = [{"id": 42, "title": "深空彼岸", "release_date": "2026-01-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name="电影"))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="movie:42", title="深空彼岸", year="2026")]
    assert client.calls == [("search_movie", "深空彼岸", "2026")]


def test_tmdb_provider_falls_back_from_movie_to_tv_when_category_name_is_ambiguous() -> None:
    client = FakeTMDBClient()
    client.movie_search_results = []
    client.tv_search_results = [{"id": 99, "name": "深空彼岸", "first_air_date": "2026-09-01"}]
    provider = TMDBProvider(client)

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026", category_name=""))

    assert matches == [MetadataMatch(provider="tmdb", provider_id="tv:99", title="深空彼岸", year="2026")]
    assert client.calls == [
        ("search_movie", "深空彼岸", "2026"),
        ("search_tv", "深空彼岸", "2026"),
    ]
```

- [ ] **Step 2: Run the focused TMDB provider tests and verify they fail**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py -q`

Expected: FAIL with `ModuleNotFoundError` because `tmdb.py` does not exist yet.

- [ ] **Step 3: Implement `TMDBProvider` and media-type inference**

```python
from __future__ import annotations

import re

from atv_player.metadata.models import MetadataMatch, MetadataQuery, MetadataRecord


def infer_tmdb_media_type(query: MetadataQuery) -> str:
    category = str(query.category_name or "").strip().lower()
    if any(token in category for token in ("电影", "影片", "movie")):
        return "movie"
    if any(token in category for token in ("电视剧", "剧集", "动漫", "番剧", "综艺", "纪录片", "tv")):
        return "tv"
    return ""


def _normalize_title(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    return text


class TMDBProvider:
    name = "tmdb"

    def __init__(self, client) -> None:
        self._client = client

    def can_enrich(self, _context) -> bool:
        return True

    def _match_from_payload(self, media_type: str, item: dict[str, object], title: str, year: str) -> MetadataMatch | None:
        aliases = [str(alias or "").strip() for alias in item.get("aliases") or [] if str(alias or "").strip()]
        item_title = str(item.get("title") or item.get("name") or "").strip()
        normalized_title = _normalize_title(title)
        normalized_item = _normalize_title(item_title)
        normalized_aliases = {_normalize_title(alias) for alias in aliases}
        item_year = str(item.get("year") or "").strip()
        if normalized_title not in {normalized_item, *normalized_aliases}:
            return None
        if year and item_year and item_year != year:
            return None
        provider_id = f"{media_type}:{item.get('id')}"
        return MetadataMatch(provider=self.name, provider_id=provider_id, title=item_title, year=item_year)

    def _search_media_type(self, media_type: str, candidate: MetadataQuery) -> list[MetadataMatch]:
        search_fn = self._client.search_movie if media_type == "movie" else self._client.search_tv
        payload = search_fn(candidate.title, year=candidate.year)
        matches = []
        for item in payload:
            match = self._match_from_payload(media_type, dict(item), candidate.title, candidate.year)
            if match is not None:
                matches.append(match)
        return matches

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title:
            return []
        inferred = infer_tmdb_media_type(candidate)
        if inferred:
            return self._search_media_type(inferred, candidate)
        for media_type in ("movie", "tv"):
            matches = self._search_media_type(media_type, candidate)
            if matches:
                return matches
        return []

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        media_type, provider_id = str(match.provider_id).split(":", 1)
        payload = self._client.get_movie_detail(provider_id) if media_type == "movie" else self._client.get_tv_detail(provider_id)
        return MetadataRecord(
            provider=self.name,
            provider_id=match.provider_id,
            title=str(payload.get("title") or payload.get("name") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("poster_url") or "").strip(),
            backdrop=str(payload.get("backdrop_url") or "").strip(),
            overview=str(payload.get("overview") or "").strip(),
            rating=str(payload.get("vote_average") or "").strip(),
            actors=list(payload.get("actors") or []),
            directors=list(payload.get("directors") or []),
            genres=list(payload.get("genres") or []),
            aliases=list(payload.get("aliases") or []),
            imdb_id=str(payload.get("imdb_id") or "").strip(),
            tmdb_id=str(payload.get("id") or "").strip(),
        )
```

- [ ] **Step 4: Run the focused TMDB provider tests and verify they pass**

Run: `uv run pytest tests/test_metadata_tmdb_provider.py -q`

Expected: PASS with 3 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/tmdb.py src/atv_player/metadata/providers/__init__.py tests/test_metadata_tmdb_provider.py
git commit -m "feat: add tmdb metadata provider"
```

### Task 3: Split current Douban provider into local and remote source providers

**Files:**
- Create: `src/atv_player/metadata/providers/local_douban.py`
- Create: `src/atv_player/metadata/providers/remote_douban.py`
- Create: `tests/test_metadata_douban_source_providers.py`
- Modify: `src/atv_player/metadata/providers/__init__.py`
- Delete or stop using: `src/atv_player/metadata/providers/douban.py`
- Test: `tests/test_metadata_douban_source_providers.py`

- [ ] **Step 1: Write the failing split-provider tests**

```python
from atv_player.metadata.models import MetadataMatch, MetadataQuery
from atv_player.metadata.providers.local_douban import LocalDoubanProvider
from atv_player.metadata.providers.remote_douban import RemoteDoubanProvider
from atv_player.metadata.providers.local_douban_client import DoubanBlockedError


class FakeLocalClient:
    def __init__(self, *, search_results=None, detail_result=None, search_error=None, detail_error=None) -> None:
        self.search_results = list(search_results or [])
        self.detail_result = detail_result
        self.search_error = search_error
        self.detail_error = detail_error

    def search(self, title: str, year: str = "") -> list[dict]:
        if self.search_error is not None:
            raise self.search_error
        return list(self.search_results)

    def get_detail(self, dbid: str) -> dict | None:
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result


class FakeRemoteApi:
    def search_douban_metadata(self, title: str, year: str = "") -> dict:
        return {"items": [{"id": 35746415, "name": title, "year": year or 2026}]}

    def get_douban_metadata_detail(self, dbid: str) -> dict:
        return {"id": dbid, "name": "深空彼岸", "description": "远程豆瓣简介", "dbScore": "8.1"}


def test_local_douban_provider_returns_no_matches_when_blocked() -> None:
    provider = LocalDoubanProvider(FakeLocalClient(search_error=DoubanBlockedError("blocked")))

    assert provider.search(MetadataQuery(title="深空彼岸", year="2026")) == []


def test_remote_douban_provider_maps_search_and_detail_from_api() -> None:
    provider = RemoteDoubanProvider(FakeRemoteApi())

    matches = provider.search(MetadataQuery(title="深空彼岸", year="2026"))
    record = provider.get_detail(matches[0])

    assert matches == [MetadataMatch(provider="remote_douban", provider_id="35746415", title="深空彼岸", year="2026")]
    assert record.provider == "remote_douban"
    assert record.overview == "远程豆瓣简介"
    assert record.rating == "8.1"
```

- [ ] **Step 2: Run the focused split-provider tests and verify they fail**

Run: `uv run pytest tests/test_metadata_douban_source_providers.py -q`

Expected: FAIL with `ModuleNotFoundError` because the split provider modules do not exist yet.

- [ ] **Step 3: Implement `LocalDoubanProvider` and `RemoteDoubanProvider`**

```python
class LocalDoubanProvider:
    name = "local_douban"

    def __init__(self, local_client) -> None:
        self._local_client = local_client

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if candidate.vod_dbid:
            return [MetadataMatch(provider=self.name, provider_id=str(candidate.vod_dbid), title=candidate.title, year=candidate.year)]
        if not candidate.title:
            return []
        try:
            items = self._local_client.search(candidate.title, year=candidate.year)
        except DoubanBlockedError:
            return []
        return [
            MetadataMatch(provider=self.name, provider_id=str(item.get("id") or ""), title=str(item.get("title") or ""), year=str(item.get("year") or ""))
            for item in items
            if str(item.get("id") or "").strip()
        ]

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        try:
            payload = self._local_client.get_detail(match.provider_id)
        except DoubanBlockedError:
            payload = None
        if payload is None:
            raise RuntimeError("local douban detail missing")
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or match.provider_id),
            title=str(payload.get("name") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("cover") or "").strip(),
            overview=clean_overview_text(str(payload.get("description") or "")),
            rating=str(payload.get("dbScore") or "").strip(),
            actors=_split_people(payload.get("actors")),
            directors=_split_people(payload.get("directors") or payload.get("director")),
            genres=[part.strip() for part in re.split(r"[,/]", str(payload.get("genre") or "")) if part.strip()],
            country=str(payload.get("country") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            douban_id=int(payload.get("id") or 0),
        )
```

```python
class RemoteDoubanProvider:
    name = "remote_douban"

    def __init__(self, api_client) -> None:
        self._api_client = api_client

    def can_enrich(self, _context) -> bool:
        return True

    def search(self, candidate: MetadataQuery) -> list[MetadataMatch]:
        if not candidate.title and not candidate.vod_dbid:
            return []
        if candidate.vod_dbid:
            return [MetadataMatch(provider=self.name, provider_id=str(candidate.vod_dbid), title=candidate.title, year=candidate.year)]
        payload = self._api_client.search_douban_metadata(candidate.title, year=candidate.year)
        items = payload.get("items") or payload.get("content") or payload.get("records") or []
        return [
            MetadataMatch(provider=self.name, provider_id=str(item.get("id") or item.get("dbid") or ""), title=str(item.get("name") or item.get("title") or "").strip(), year=str(item.get("year") or "").strip())
            for item in items
            if str(item.get("id") or item.get("dbid") or "").strip()
        ]

    def get_detail(self, match: MetadataMatch) -> MetadataRecord:
        payload = self._api_client.get_douban_metadata_detail(match.provider_id)
        return MetadataRecord(
            provider=self.name,
            provider_id=str(payload.get("id") or payload.get("dbid") or match.provider_id),
            title=str(payload.get("name") or payload.get("title") or match.title or "").strip(),
            year=str(payload.get("year") or match.year or "").strip(),
            poster=str(payload.get("cover") or payload.get("poster") or "").strip(),
            overview=clean_overview_text(str(payload.get("description") or payload.get("intro") or "")),
            rating=str(payload.get("dbScore") or payload.get("rating") or "").strip(),
            actors=_split_people(payload.get("actors")),
            directors=_split_people(payload.get("directors") or payload.get("director")),
            genres=[part.strip() for part in re.split(r"[,/]", str(payload.get("genre") or "")) if part.strip()],
            country=str(payload.get("country") or payload.get("region") or "").strip(),
            language=str(payload.get("language") or "").strip(),
            douban_id=int(payload.get("id") or payload.get("dbid") or 0),
        )
```

- [ ] **Step 4: Run the focused split-provider tests and verify they pass**

Run: `uv run pytest tests/test_metadata_douban_source_providers.py -q`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/providers/local_douban.py src/atv_player/metadata/providers/remote_douban.py src/atv_player/metadata/providers/__init__.py tests/test_metadata_douban_source_providers.py
git commit -m "refactor: split douban metadata providers"
```

### Task 4: Upgrade metadata merge to field-level provider priorities

**Files:**
- Modify: `src/atv_player/metadata/merge.py`
- Modify: `tests/test_metadata_merge.py`
- Modify: `tests/test_metadata_hydrator.py`
- Test: `tests/test_metadata_merge.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing merge-priority tests**

```python
def test_merge_metadata_prefers_tmdb_visual_fields_but_keeps_douban_overview_and_rating() -> None:
    vod = VodItem(vod_id="v1", vod_name="深空彼岸", vod_content="原始简介")
    tmdb_record = MetadataRecord(
        provider="tmdb",
        provider_id="movie:42",
        poster="https://img.example/tmdb-poster.jpg",
        backdrop="https://img.example/tmdb-backdrop.jpg",
        year="2026",
        actors=["梁达伟"],
        directors=["周琛"],
        genres=["动画"],
        aliases=["The First Sequence"],
        imdb_id="tt123",
        tmdb_id="42",
        overview="TMDB简介",
        rating="7.2",
    )
    douban_record = MetadataRecord(
        provider="local_douban",
        provider_id="35746415",
        overview="豆瓣简介",
        rating="8.1",
        douban_id=35746415,
    )

    merge_metadata_record(vod, tmdb_record, provider_priority=["tmdb"])
    merge_metadata_record(vod, douban_record, provider_priority=["local_douban", "tmdb"])

    assert vod.vod_pic == "https://img.example/tmdb-poster.jpg"
    assert vod.vod_content == "豆瓣简介"
    assert vod.vod_remarks == "8.1"
    assert vod.vod_year == "2026"
```

- [ ] **Step 2: Run the focused merge tests and verify they fail**

Run: `uv run pytest tests/test_metadata_merge.py tests/test_metadata_hydrator.py -k "tmdb or visual_fields or douban_overview" -q`

Expected: FAIL because `merge_metadata_record()` only supports a flat provider-priority list and does not encode field-level precedence.

- [ ] **Step 3: Implement field-level merge priorities**

```python
_FIELD_PROVIDER_PRIORITY = {
    "overview": ["local_douban", "remote_douban", "tmdb", "plugin"],
    "rating": ["local_douban", "remote_douban", "tmdb", "plugin"],
    "poster": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "backdrop": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "year": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "actors": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "directors": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "genres": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "aliases": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "imdb_id": ["tmdb", "local_douban", "remote_douban", "plugin"],
    "tmdb_id": ["tmdb", "plugin"],
    "douban_id": ["local_douban", "remote_douban", "plugin"],
}
```

```python
def _provider_rank(field_name: str, provider: str) -> int:
    order = _FIELD_PROVIDER_PRIORITY.get(field_name, [])
    return order.index(provider) if provider in order else len(order) + 100
```

```python
if record.poster and (_provider_rank("poster", record.provider) <= _provider_rank("poster", current_poster_provider)):
    vod.vod_pic = record.poster
    current_poster_provider = record.provider
```

- [ ] **Step 4: Run the focused merge tests and verify they pass**

Run: `uv run pytest tests/test_metadata_merge.py tests/test_metadata_hydrator.py -q`

Expected: PASS with all selected tests, including the new TMDB-vs-Douban precedence case.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/metadata/merge.py tests/test_metadata_merge.py tests/test_metadata_hydrator.py
git commit -m "feat: add field-level metadata merge priorities"
```

### Task 5: Wire the provider chain into the app and verify regressions

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `tests/test_app.py`
- Test: `tests/test_app.py`
- Test: `tests/test_metadata_tmdb_provider.py`
- Test: `tests/test_metadata_douban_source_providers.py`
- Test: `tests/test_metadata_merge.py`
- Test: `tests/test_metadata_hydrator.py`

- [ ] **Step 1: Write the failing app-wiring tests**

```python
def test_app_coordinator_builds_tmdb_provider_when_api_key_present(monkeypatch, tmp_path) -> None:
    class FakeRepo:
        def load_config(self) -> AppConfig:
            return AppConfig(
                metadata_enhancement_enabled=True,
                metadata_douban_cookie="bid=demo;",
                metadata_tmdb_api_key="tmdb-key",
            )

    seen: dict[str, object] = {}

    class RecordingTMDBClient:
        def __init__(self, api_key: str, transport=None) -> None:
            del transport
            seen["api_key"] = api_key

    class RecordingTMDBProvider:
        name = "tmdb"

        def __init__(self, client) -> None:
            seen["client"] = client

        def can_enrich(self, _context) -> bool:
            return False

        def search(self, _candidate):
            return []

        def get_detail(self, _match):
            raise AssertionError("not used")

    coordinator = AppCoordinator(FakeRepo())
    monkeypatch.setattr(app_module, "TMDBClient", RecordingTMDBClient)
    monkeypatch.setattr(app_module, "TMDBProvider", RecordingTMDBProvider)
    monkeypatch.setattr(app_module, "LocalDoubanProvider", lambda client: type("P", (), {"name": "local_douban", "can_enrich": lambda self, _c: False, "search": lambda self, _q: [], "get_detail": lambda self, _m: None})())
    monkeypatch.setattr(app_module, "RemoteDoubanProvider", lambda api: type("P", (), {"name": "remote_douban", "can_enrich": lambda self, _c: False, "search": lambda self, _q: [], "get_detail": lambda self, _m: None})())

    factory = coordinator._build_metadata_hydrator_factory(object())
    hydrate = factory(source_kind="browse", vod=VodItem(vod_id="v1", vod_name="深空彼岸"))

    assert callable(hydrate)
    assert seen["api_key"] == "tmdb-key"
```

- [ ] **Step 2: Run the focused app-wiring tests and verify they fail**

Run: `uv run pytest tests/test_app.py -k "tmdb_provider_when_api_key_present" -q`

Expected: FAIL because `AppCoordinator` still wires only the old Douban provider.

- [ ] **Step 3: Update app wiring to the explicit provider chain**

```python
cache = MetadataCache(app_cache_dir() / "metadata")
local_douban_provider = LocalDoubanProvider(LocalDoubanClient(cookie=config.metadata_douban_cookie))
providers: list[object] = []
if source_kind == "plugin" and plugin_payload is not None:
    providers.append(CustomPluginProvider(plugin_payload))
providers.append(local_douban_provider)
if config.metadata_tmdb_api_key:
    providers.append(TMDBProvider(TMDBClient(api_key=config.metadata_tmdb_api_key)))
providers.append(RemoteDoubanProvider(api_client))
hydrator = MetadataHydrator(cache=cache, providers=providers)
```

- [ ] **Step 4: Run the focused regression suite and verify it passes**

Run: `uv run pytest tests/test_app.py tests/test_metadata_tmdb_client.py tests/test_metadata_tmdb_provider.py tests/test_metadata_douban_source_providers.py tests/test_metadata_merge.py tests/test_metadata_hydrator.py -q`

Expected: PASS across the provider chain, merge priority, and app-wiring suites.

- [ ] **Step 5: Run the UI regression suite and verify it still passes**

Run: `uv run pytest tests/test_main_window_ui.py tests/test_player_window_ui.py -k "advanced_settings or metadata_hydration or metadata_hydrator" -q`

Expected: PASS with the advanced settings dialog and async metadata refresh tests still green.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/app.py tests/test_app.py
git commit -m "feat: wire tmdb into metadata enhancement chain"
```

## Self-Review

- Spec coverage: the plan covers TMDB client/API usage, `category_name`-based movie/tv inference, explicit provider chaining, field-level merge precedence, app wiring, and regression verification.
- Placeholder scan: no `TODO`/`TBD` markers remain; each task includes exact file paths, tests, commands, and code snippets.
- Type consistency: provider names are consistently `local_douban`, `tmdb`, and `remote_douban`; TMDB `provider_id` uses `movie:{id}` / `tv:{id}` throughout; app wiring references `TMDBClient`, `TMDBProvider`, `LocalDoubanProvider`, and `RemoteDoubanProvider` consistently.
