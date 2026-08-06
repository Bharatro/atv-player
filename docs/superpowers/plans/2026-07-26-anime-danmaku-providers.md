# Anime Danmaku Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native DandanPlay, Bahamut, and Animeko danmaku providers with stable cached URLs, source settings, failure isolation, and regression coverage.

**Architecture:** Implement one synchronous `DanmakuProvider` per upstream and inject the existing proxy-aware `get`/`post` callables. Each search expands a bounded number of matching series into episode-specific `DanmakuSearchItem` values using a provider-owned URL scheme; each resolve call reconstructs the upstream episode ID from that URL and emits `DanmakuRecord` values without relying on in-memory search context. Register the providers after the existing eight sources so current ranking remains stable.

**Tech Stack:** Python 3.12, httpx, OpenCC (`opencc-python-reimplemented`), pytest, pytest-qt, Ruff, Pyright, uv.

---

## File structure

**Create:**

- `src/atv_player/danmaku/providers/dandan.py` — DandanPlay search, episode expansion, internal URL parsing, and comment conversion.
- `src/atv_player/danmaku/providers/bahamut.py` — Traditional Chinese search, Bahamut episode expansion, and comment conversion.
- `src/atv_player/danmaku/providers/animeko.py` — Bangumi search, Animeko node failover, episode expansion, and comment conversion.
- `tests/test_danmaku_dandan_provider.py` — DandanPlay provider contract tests.
- `tests/test_danmaku_bahamut_provider.py` — Bahamut provider contract tests.
- `tests/test_danmaku_animeko_provider.py` — Animeko provider contract and node failover tests.

**Modify:**

- `pyproject.toml` and `uv.lock` — add the pure-Python OpenCC dependency used by Bahamut search.
- `src/atv_player/danmaku/providers/__init__.py` — export all three provider classes.
- `src/atv_player/danmaku/service.py` — labels, construction, and fixed provider order.
- `src/atv_player/source_preferences.py` — settings entries and valid persisted IDs.
- `tests/test_danmaku_service.py` — service registration, ordering, labels, disabling, and cached URL routing.
- `tests/test_storage.py` — persistence of the three new disabled-source IDs.
- `tests/test_main_window_ui.py` — advanced-settings labels and source toggles.

Do not modify the user's existing `src/atv_player/app.py` or `tests/test_app.py` worktree changes.

---

### Task 1: DandanPlay provider

**Files:**

- Create: `tests/test_danmaku_dandan_provider.py`
- Create: `src/atv_player/danmaku/providers/dandan.py`

- [ ] **Step 1: Write the failing DandanPlay provider tests**

Create `tests/test_danmaku_dandan_provider.py` with these behaviors:

```python
import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.dandan import DandanDanmakuProvider


def test_dandan_search_expands_and_filters_requested_episode() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        path = kwargs["params"]["path"]
        calls.append(path)
        if path.startswith("/v2/search/anime?"):
            return httpx.Response(
                200,
                json={"animes": [{"animeId": 100, "animeTitle": "葬送的芙莉莲"}]},
            )
        if path == "/v2/bangumi/100":
            return httpx.Response(
                200,
                json={
                    "bangumi": {
                        "episodes": [
                            {"episodeId": 10001, "episodeNumber": "1", "episodeTitle": "冒险的终点"},
                            {"episodeId": 10002, "episodeNumber": "2", "episodeTitle": "无需魔法"},
                        ]
                    }
                },
            )
        raise AssertionError(path)

    provider = DandanDanmakuProvider(get=fake_get)

    items = provider.search("葬送的芙莉莲", original_name="葬送的芙莉莲 第2集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("dandan", "葬送的芙莉莲 第2集 无需魔法", "dandan://episode/10002")
    ]
    assert calls == [
        "/v2/search/anime?keyword=%E8%91%AC%E9%80%81%E7%9A%84%E8%8A%99%E8%8E%89%E8%8E%B2",
        "/v2/bangumi/100",
    ]


def test_dandan_resolve_maps_comments_and_skips_invalid_rows() -> None:
    def fake_get(url: str, **kwargs):
        assert kwargs["params"]["path"] == (
            "/v2/comment/10002?from=0&withRelated=true&chConvert=0"
        )
        return httpx.Response(
            200,
            json={
                "comments": [
                    {"cid": 1, "p": "1.25,1,16711680,[dandan]", "m": "滚动"},
                    {"cid": 2, "p": "2.5,5,65280,[dandan]", "m": "顶部"},
                    {"cid": 3, "p": "bad,1,255,[dandan]", "m": "坏时间"},
                    {"cid": 4, "p": "4,4,255,[dandan]", "m": ""},
                ]
            },
        )

    provider = DandanDanmakuProvider(get=fake_get)

    records = provider.resolve("dandan://episode/10002")

    assert [(r.time_offset, r.pos, r.color, r.content) for r in records] == [
        (1.25, 1, "16711680", "滚动"),
        (2.5, 5, "65280", "顶部"),
    ]


def test_dandan_supports_only_valid_internal_episode_urls() -> None:
    provider = DandanDanmakuProvider()

    assert provider.supports("dandan://episode/10002") is True
    assert provider.supports("dandan://episode/") is False
    assert provider.supports("animeko://episode/10002") is False


def test_dandan_search_failure_is_isolated() -> None:
    provider = DandanDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    assert provider.search("葬送的芙莉莲") == []


def test_dandan_resolve_failure_names_the_source() -> None:
    provider = DandanDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    with pytest.raises(DanmakuResolveError, match="弹弹Play弹幕获取失败"):
        provider.resolve("dandan://episode/10002")
```

- [ ] **Step 2: Run the DandanPlay tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_dandan_provider.py -q
```

Expected: collection fails with `ModuleNotFoundError: atv_player.danmaku.providers.dandan`.

- [ ] **Step 3: Implement the minimal DandanPlay provider**

Create `src/atv_player/danmaku/providers/dandan.py`. Use these exact constants and public methods:

```python
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote, urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_BASE_URL = "https://api.danmaku.weeblify.app/ddp/v1"
_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "atv-player/0.1.0",
}
_MAX_SERIES = 5
_MAX_EPISODES_PER_SERIES = 200


class DandanDanmakuProvider:
    key = "dandan"

    def __init__(self, get: Callable[..., httpx.Response] = httpx.get) -> None:
        self._get = get

    def supports(self, page_url: str) -> bool:
        parsed = urlparse(page_url)
        return (
            parsed.scheme == self.key
            and parsed.netloc == "episode"
            and bool(parsed.path.strip("/"))
        )

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name or name)
        try:
            payload = self._request_json(
                f"/v2/search/anime?keyword={quote(name)}"
            )
            animes = payload.get("animes") if isinstance(payload, dict) else None
            if not isinstance(animes, list):
                return []
            items: list[DanmakuSearchItem] = []
            for anime in animes[:_MAX_SERIES]:
                if not isinstance(anime, dict):
                    continue
                anime_id = str(anime.get("animeId") or "").strip()
                title = str(anime.get("animeTitle") or "").strip()
                if not anime_id or not title or should_filter_name(name, title):
                    continue
                details = self._request_json(f"/v2/bangumi/{anime_id}")
                bangumi = details.get("bangumi") if isinstance(details, dict) else None
                episodes = bangumi.get("episodes") if isinstance(bangumi, dict) else None
                if not isinstance(episodes, list):
                    continue
                for episode in episodes[:_MAX_EPISODES_PER_SERIES]:
                    item = self._episode_item(title, anime_id, episode)
                    if item is not None:
                        items.append(item)
        except (httpx.HTTPError, TypeError, ValueError):
            return []
        return self._prefer_requested_episode(items, requested_episode)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        episode_id = self._episode_id(page_url)
        try:
            payload = self._request_json(
                f"/v2/comment/{episode_id}?from=0&withRelated=true&chConvert=0"
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuResolveError("弹弹Play弹幕获取失败") from exc
        comments = payload.get("comments") if isinstance(payload, dict) else None
        if not isinstance(comments, list):
            raise DanmakuResolveError("弹弹Play弹幕响应解析失败")
        return [record for row in comments if (record := self._record(row)) is not None]

    def _request_json(self, path: str) -> object:
        response = self._get(
            _BASE_URL,
            params={"path": path},
            headers=_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise httpx.HTTPError(
                f"DandanPlay returned {response.status_code}"
            )
        return response.json()

    def _episode_item(
        self,
        title: str,
        anime_id: str,
        episode: object,
    ) -> DanmakuSearchItem | None:
        if not isinstance(episode, dict):
            return None
        episode_id = str(episode.get("episodeId") or "").strip()
        episode_number = str(episode.get("episodeNumber") or "").strip()
        if not episode_id or not episode_number:
            return None
        episode_title = str(episode.get("episodeTitle") or "").strip()
        candidate_name = f"{title} 第{episode_number}集 {episode_title}".strip()
        return DanmakuSearchItem(
            provider=self.key,
            name=candidate_name,
            url=f"dandan://episode/{episode_id}",
            resolve_context={"anime_id": anime_id, "episode_id": episode_id},
        )

    def _prefer_requested_episode(
        self,
        items: list[DanmakuSearchItem],
        requested_episode: int | None,
    ) -> list[DanmakuSearchItem]:
        if requested_episode is None:
            return items
        matched = [
            item
            for item in items
            if extract_episode_number(item.name) == requested_episode
        ]
        return matched if matched else items[:3]

    def _episode_id(self, page_url: str) -> str:
        if not self.supports(page_url):
            raise DanmakuResolveError("弹弹Play弹幕地址无效")
        return urlparse(page_url).path.strip("/")

    def _record(self, row: object) -> DanmakuRecord | None:
        if not isinstance(row, dict):
            return None
        content = str(row.get("m") or "").strip()
        parts = str(row.get("p") or "").split(",")
        if not content or len(parts) < 3:
            return None
        try:
            time_offset = max(0.0, float(parts[0]))
            mode = int(parts[1])
            color = int(parts[2])
        except (TypeError, ValueError):
            return None
        return DanmakuRecord(
            time_offset=time_offset,
            pos=mode if mode in {1, 4, 5} else 1,
            color=str(color if 0 <= color <= 0xFFFFFF else 0xFFFFFF),
            content=content,
        )
```

- [ ] **Step 4: Run the DandanPlay tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_dandan_provider.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit the DandanPlay provider**

```bash
git add src/atv_player/danmaku/providers/dandan.py tests/test_danmaku_dandan_provider.py
git commit -m "feat(danmaku): add DandanPlay provider"
```

---

### Task 2: Bahamut provider and Traditional Chinese conversion

**Files:**

- Create: `tests/test_danmaku_bahamut_provider.py`
- Create: `src/atv_player/danmaku/providers/bahamut.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Write the failing Bahamut provider tests**

Create `tests/test_danmaku_bahamut_provider.py`:

```python
import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.bahamut import BahamutDanmakuProvider


def test_bahamut_search_uses_traditional_query_and_expands_episode() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs.get("params") or {}))
        if url.endswith("/mobile_app/anime/v1/search.php"):
            assert kwargs["params"]["kw"] == "葬送的芙莉蓮"
            return httpx.Response(
                200,
                json={"anime": [{"title": "葬送的芙莉蓮", "video_sn": 5001}]},
            )
        if url.endswith("/anime/v1/video.php"):
            assert kwargs["params"]["videoSn"] == "5001"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "anime": {
                            "episodes": {
                                "0": [
                                    {"episode": "1", "videoSn": 5101},
                                    {"episode": "2", "videoSn": 5102},
                                ]
                            }
                        }
                    }
                },
            )
        raise AssertionError(url)

    provider = BahamutDanmakuProvider(
        get=fake_get,
        traditionalize=lambda value: value.replace("莲", "蓮").replace("莉", "莉"),
    )

    items = provider.search("葬送的芙莉莲", original_name="葬送的芙莉莲 第2集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("bahamut", "葬送的芙莉莲 第2集", "bahamut://episode/5102")
    ]
    assert len(calls) == 2


def test_bahamut_resolve_maps_time_position_and_hex_color() -> None:
    def fake_get(url: str, **kwargs):
        assert url.endswith("/anime/v1/danmu.php")
        assert kwargs["params"] == {"geo": "TW,HK", "videoSn": "5102"}
        return httpx.Response(
            200,
            json={
                "data": {
                    "danmu": [
                        {"sn": 1, "time": 15, "position": 0, "color": "#ff0000", "text": "滚动"},
                        {"sn": 2, "time": 25, "position": 1, "color": "#00ff00", "text": "顶部"},
                        {"sn": 3, "time": 35, "position": 2, "color": "bad", "text": "底部"},
                        {"sn": 4, "time": "bad", "position": 0, "color": "#ffffff", "text": "坏时间"},
                    ]
                }
            },
        )

    provider = BahamutDanmakuProvider(get=fake_get)

    records = provider.resolve("bahamut://episode/5102")

    assert [(r.time_offset, r.pos, r.color, r.content) for r in records] == [
        (1.5, 1, "16711680", "滚动"),
        (2.5, 5, "65280", "顶部"),
        (3.5, 4, "16777215", "底部"),
    ]


def test_bahamut_supports_only_valid_internal_episode_urls() -> None:
    provider = BahamutDanmakuProvider()

    assert provider.supports("bahamut://episode/5102") is True
    assert provider.supports("bahamut://episode/") is False
    assert provider.supports("dandan://episode/5102") is False


def test_bahamut_search_failure_is_isolated() -> None:
    provider = BahamutDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    assert provider.search("葬送的芙莉莲") == []


def test_bahamut_resolve_failure_names_the_source() -> None:
    provider = BahamutDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down"))
    )

    with pytest.raises(DanmakuResolveError, match="巴哈姆特弹幕获取失败"):
        provider.resolve("bahamut://episode/5102")
```

- [ ] **Step 2: Run the Bahamut tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_bahamut_provider.py -q
```

Expected: collection fails because `atv_player.danmaku.providers.bahamut` does not exist.

- [ ] **Step 3: Add the OpenCC dependency**

Run:

```bash
uv add "opencc-python-reimplemented>=0.1.7"
```

Expected: `pyproject.toml` gains the dependency and `uv.lock` resolves it successfully. Do not hand-edit `uv.lock`.

- [ ] **Step 4: Implement the Bahamut provider**

Create `src/atv_player/danmaku/providers/bahamut.py` with the following public shape and helpers:

```python
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx
from opencc import OpenCC

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_SEARCH_URL = "https://api.gamer.com.tw/mobile_app/anime/v1/search.php"
_DETAIL_URL = "https://api.gamer.com.tw/anime/v1/video.php"
_DANMAKU_URL = "https://api.gamer.com.tw/anime/v1/danmu.php"
_USER_AGENT = "Anime/2.29.2 (7N5749MM3F.tw.com.gamer.anime; build:972; iOS 26.0.0) Alamofire/5.6.4"
_HEADERS = {"Accept": "application/json", "User-Agent": _USER_AGENT}
_CONVERTER = OpenCC("s2twp")
_MAX_SERIES = 5


def _to_traditional(value: str) -> str:
    return _CONVERTER.convert(value)


class BahamutDanmakuProvider:
    key = "bahamut"

    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        traditionalize: Callable[[str], str] = _to_traditional,
    ) -> None:
        self._get = get
        self._traditionalize = traditionalize

    def supports(self, page_url: str) -> bool:
        parsed = urlparse(page_url)
        return (
            parsed.scheme == self.key
            and parsed.netloc == "episode"
            and bool(parsed.path.strip("/"))
        )

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name or name)
        traditional_name = self._traditionalize(name)
        try:
            search_payload = self._get_json(
                _SEARCH_URL,
                params={"kw": traditional_name},
            )
            animes = search_payload.get("anime") if isinstance(search_payload, dict) else None
            if not isinstance(animes, list):
                return []
            items: list[DanmakuSearchItem] = []
            for anime in animes[:_MAX_SERIES]:
                if not isinstance(anime, dict):
                    continue
                source_title = str(anime.get("title") or "").strip()
                video_sn = str(anime.get("video_sn") or anime.get("videoSn") or "").strip()
                if not source_title or not video_sn:
                    continue
                if should_filter_name(traditional_name, source_title):
                    continue
                detail_payload = self._get_json(
                    _DETAIL_URL,
                    params={"videoSn": video_sn},
                )
                data = detail_payload.get("data") if isinstance(detail_payload, dict) else None
                series = data.get("anime") if isinstance(data, dict) else None
                for episode in self._episodes(series):
                    episode_no = str(episode.get("episode") or "").strip()
                    episode_video_sn = str(episode.get("videoSn") or "").strip()
                    if not episode_no or not episode_video_sn:
                        continue
                    items.append(
                        DanmakuSearchItem(
                            provider=self.key,
                            name=f"{name} 第{episode_no}集",
                            url=f"bahamut://episode/{episode_video_sn}",
                            resolve_context={
                                "series_video_sn": video_sn,
                                "source_title": source_title,
                            },
                        )
                    )
        except (httpx.HTTPError, TypeError, ValueError):
            return []
        return self._prefer_requested_episode(items, requested_episode)

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        video_sn = self._episode_id(page_url)
        try:
            payload = self._get_json(
                _DANMAKU_URL,
                params={"geo": "TW,HK", "videoSn": video_sn},
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DanmakuResolveError("巴哈姆特弹幕获取失败") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        comments = data.get("danmu") if isinstance(data, dict) else None
        if not isinstance(comments, list):
            raise DanmakuResolveError("巴哈姆特弹幕响应解析失败")
        return [record for row in comments if (record := self._record(row)) is not None]

    def _get_json(self, url: str, *, params: dict[str, str]) -> object:
        response = self._get(
            url,
            params=params,
            headers=_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise httpx.HTTPError(f"Bahamut returned {response.status_code}")
        return response.json()

    def _episodes(self, series: object) -> list[dict]:
        if not isinstance(series, dict):
            return []
        groups = series.get("episodes")
        if isinstance(groups, list):
            return [item for item in groups if isinstance(item, dict)]
        if not isinstance(groups, dict):
            return []
        return [
            item
            for group in groups.values()
            if isinstance(group, list)
            for item in group
            if isinstance(item, dict)
        ]

    def _prefer_requested_episode(
        self,
        items: list[DanmakuSearchItem],
        requested_episode: int | None,
    ) -> list[DanmakuSearchItem]:
        if requested_episode is None:
            return items
        matched = [
            item
            for item in items
            if extract_episode_number(item.name) == requested_episode
        ]
        return matched if matched else items[:3]

    def _episode_id(self, page_url: str) -> str:
        if not self.supports(page_url):
            raise DanmakuResolveError("巴哈姆特弹幕地址无效")
        return urlparse(page_url).path.strip("/")

    def _record(self, row: object) -> DanmakuRecord | None:
        if not isinstance(row, dict):
            return None
        content = str(row.get("text") or "").strip()
        if not content:
            return None
        try:
            time_offset = max(0.0, float(row.get("time")) / 10.0)
        except (TypeError, ValueError):
            return None
        position = {0: 1, 1: 5, 2: 4}.get(row.get("position"), 1)
        color_text = str(row.get("color") or "").strip().lstrip("#")
        try:
            color = int(color_text, 16)
        except ValueError:
            color = 0xFFFFFF
        return DanmakuRecord(
            time_offset=time_offset,
            pos=position,
            color=str(color if 0 <= color <= 0xFFFFFF else 0xFFFFFF),
            content=content,
        )
```

- [ ] **Step 5: Run Bahamut tests and dependency import check**

Run:

```bash
uv run pytest tests/test_danmaku_bahamut_provider.py -q
uv run python -c "from opencc import OpenCC; assert OpenCC('s2twp').convert('莲') == '蓮'"
```

Expected: `5 passed`, then the import check exits zero.

- [ ] **Step 6: Commit the Bahamut provider**

```bash
git add pyproject.toml uv.lock src/atv_player/danmaku/providers/bahamut.py tests/test_danmaku_bahamut_provider.py
git commit -m "feat(danmaku): add Bahamut provider"
```

---

### Task 3: Animeko provider with bounded node failover

**Files:**

- Create: `tests/test_danmaku_animeko_provider.py`
- Create: `src/atv_player/danmaku/providers/animeko.py`

- [ ] **Step 1: Write failing Animeko provider tests**

Create `tests/test_danmaku_animeko_provider.py`:

```python
import httpx
import pytest

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.providers.animeko import AnimekoDanmakuProvider


def test_animeko_search_expands_main_episode_from_fallback_subject_node() -> None:
    get_calls: list[str] = []

    def fake_post(url: str, **kwargs):
        assert url == "https://api.bangumi.lol/v0/search/subjects"
        assert kwargs["json"] == {
            "keyword": "迷宫饭",
            "filter": {"type": [2]},
        }
        return httpx.Response(
            200,
            json={"data": [{"id": 42, "name": "ダンジョン飯", "name_cn": "迷宫饭"}]},
        )

    def fake_get(url: str, **kwargs):
        get_calls.append(url)
        if url == "https://node-a.example/v2/subjects/42":
            raise httpx.HTTPError("node a down")
        if url == "https://node-b.example/v2/subjects/42":
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "episodes": [
                        {"episodeId": 4201, "sort": 1, "type": "MAIN", "nameCn": "水炖史莱姆"},
                        {"episodeId": 4299, "sort": 1, "type": "SP", "nameCn": "特典"},
                    ],
                },
            )
        raise AssertionError(url)

    provider = AnimekoDanmakuProvider(
        get=fake_get,
        post=fake_post,
        nodes=("https://node-a.example", "https://node-b.example"),
        search_nodes=("https://api.bangumi.lol",),
    )

    items = provider.search("迷宫饭", original_name="迷宫饭 第1集")

    assert [(item.provider, item.name, item.url) for item in items] == [
        ("animeko", "迷宫饭 第1集 水炖史莱姆", "animeko://episode/4201")
    ]
    assert get_calls == [
        "https://node-a.example/v2/subjects/42",
        "https://node-b.example/v2/subjects/42",
    ]


def test_animeko_resolve_falls_back_and_remembers_healthy_node() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if url.startswith("https://node-a.example"):
            raise httpx.HTTPError("node a down")
        return httpx.Response(
            200,
            json={
                "danmakuList": [
                    {
                        "id": 1,
                        "danmakuInfo": {
                            "playTime": 1250,
                            "location": "TOP",
                            "color": -1,
                            "text": "顶部",
                        },
                    }
                ]
            },
        )

    provider = AnimekoDanmakuProvider(
        get=fake_get,
        post=lambda *args, **kwargs: httpx.Response(200, json={"data": []}),
        nodes=("https://node-a.example", "https://node-b.example"),
    )

    first = provider.resolve("animeko://episode/4201")
    second = provider.resolve("animeko://episode/4202")

    assert [(r.time_offset, r.pos, r.color, r.content) for r in first] == [
        (1.25, 5, "16777215", "顶部")
    ]
    assert len(second) == 1
    assert calls == [
        "https://node-a.example/v1/danmaku/4201",
        "https://node-b.example/v1/danmaku/4201",
        "https://node-b.example/v1/danmaku/4202",
    ]


def test_animeko_valid_empty_comments_do_not_try_other_nodes() -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"danmakuList": []})

    provider = AnimekoDanmakuProvider(
        get=fake_get,
        post=lambda *args, **kwargs: httpx.Response(200, json={"data": []}),
        nodes=("https://node-a.example", "https://node-b.example"),
    )

    assert provider.resolve("animeko://episode/4201") == []
    assert calls == ["https://node-a.example/v1/danmaku/4201"]


def test_animeko_supports_only_valid_internal_episode_urls() -> None:
    provider = AnimekoDanmakuProvider()

    assert provider.supports("animeko://episode/4201") is True
    assert provider.supports("animeko://episode/") is False
    assert provider.supports("bahamut://episode/4201") is False


def test_animeko_all_nodes_fail_with_named_error() -> None:
    provider = AnimekoDanmakuProvider(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("down")),
        nodes=("https://node-a.example", "https://node-b.example"),
    )

    with pytest.raises(DanmakuResolveError, match="Animeko弹幕获取失败"):
        provider.resolve("animeko://episode/4201")
```

- [ ] **Step 2: Run Animeko tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_animeko_provider.py -q
```

Expected: collection fails because `atv_player.danmaku.providers.animeko` does not exist.

- [ ] **Step 3: Implement Animeko search, subject failover, and resolve failover**

Create `src/atv_player/danmaku/providers/animeko.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, should_filter_name

_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "atv-player/0.1.0",
}
_MAX_SUBJECTS = 5


def _default_nodes() -> tuple[str, ...]:
    utc_offset = datetime.now().astimezone().utcoffset()
    if utc_offset == timedelta(hours=8):
        return (
            "https://api.animeko.org",
            "https://danmaku-global.myani.org",
            "https://danmaku-cn.myani.org",
            "https://s1.animeko.openani.org",
        )
    return (
        "https://danmaku-global.myani.org",
        "https://api.animeko.org",
        "https://s1.animeko.openani.org",
        "https://danmaku-cn.myani.org",
    )


class AnimekoDanmakuProvider:
    key = "animeko"

    def __init__(
        self,
        get: Callable[..., httpx.Response] = httpx.get,
        post: Callable[..., httpx.Response] = httpx.post,
        nodes: Sequence[str] | None = None,
        search_nodes: Sequence[str] = (
            "https://api.bangumi.lol",
            "https://api.bgm.tv",
        ),
    ) -> None:
        self._get = get
        self._post = post
        self._nodes = tuple(nodes or _default_nodes())
        self._search_nodes = tuple(search_nodes)
        self._subject_host = ""
        self._danmaku_host = ""

    def supports(self, page_url: str) -> bool:
        parsed = urlparse(page_url)
        return (
            parsed.scheme == self.key
            and parsed.netloc == "episode"
            and bool(parsed.path.strip("/"))
        )

    def search(
        self,
        name: str,
        original_name: str | None = None,
    ) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name or name)
        subjects = self._search_subjects(name)
        items: list[DanmakuSearchItem] = []
        for subject in subjects[:_MAX_SUBJECTS]:
            if not isinstance(subject, dict):
                continue
            subject_id = str(subject.get("id") or "").strip()
            titles = [
                str(subject.get("name_cn") or "").strip(),
                str(subject.get("name") or "").strip(),
            ]
            title = next(
                (
                    candidate
                    for candidate in titles
                    if candidate and not should_filter_name(name, candidate)
                ),
                "",
            )
            if not subject_id or not title:
                continue
            details = self._subject(subject_id)
            episodes = details.get("episodes") if isinstance(details, dict) else None
            if not isinstance(episodes, list):
                continue
            for episode in episodes:
                if not isinstance(episode, dict) or episode.get("type") != "MAIN":
                    continue
                episode_id = str(episode.get("episodeId") or "").strip()
                episode_no = str(episode.get("sort") or episode.get("ep") or "").strip()
                if not episode_id or not episode_no:
                    continue
                episode_title = str(
                    episode.get("nameCn") or episode.get("name") or ""
                ).strip()
                items.append(
                    DanmakuSearchItem(
                        provider=self.key,
                        name=f"{title} 第{episode_no}集 {episode_title}".strip(),
                        url=f"animeko://episode/{episode_id}",
                        resolve_context={
                            "subject_id": subject_id,
                            "episode_id": episode_id,
                        },
                    )
                )
        if requested_episode is None:
            return items
        matched = [
            item
            for item in items
            if extract_episode_number(item.name) == requested_episode
        ]
        return matched if matched else items[:3]

    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        episode_id = self._episode_id(page_url)
        failures: list[Exception] = []
        for host in self._ordered_nodes(self._danmaku_host):
            try:
                payload = self._get_json(f"{host}/v1/danmaku/{episode_id}")
            except (httpx.HTTPError, TypeError, ValueError) as exc:
                failures.append(exc)
                continue
            comments = payload.get("danmakuList") if isinstance(payload, dict) else None
            if not isinstance(comments, list):
                failures.append(ValueError("missing danmakuList"))
                continue
            self._danmaku_host = host
            return [
                record
                for row in comments
                if (record := self._record(row)) is not None
            ]
        error = DanmakuResolveError("Animeko弹幕获取失败")
        if failures:
            raise error from failures[-1]
        raise error

    def _search_subjects(self, keyword: str) -> list[object]:
        for host in self._search_nodes:
            try:
                response = self._post(
                    f"{host}/v0/search/subjects",
                    json={"keyword": keyword, "filter": {"type": [2]}},
                    headers=_HEADERS,
                    params={"limit": 20, "offset": 0},
                    timeout=5.0,
                    follow_redirects=True,
                )
                if response.status_code >= 400:
                    continue
                payload = response.json()
            except (httpx.HTTPError, TypeError, ValueError):
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                return data
        return []

    def _subject(self, subject_id: str) -> object:
        for host in self._ordered_nodes(self._subject_host):
            try:
                payload = self._get_json(f"{host}/v2/subjects/{subject_id}")
            except (httpx.HTTPError, TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("id"):
                self._subject_host = host
                return payload
        return {}

    def _get_json(self, url: str) -> object:
        response = self._get(
            url,
            headers=_HEADERS,
            timeout=3.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise httpx.HTTPError(f"Animeko returned {response.status_code}")
        return response.json()

    def _ordered_nodes(self, preferred: str) -> tuple[str, ...]:
        if preferred not in self._nodes:
            return self._nodes
        return (preferred, *(node for node in self._nodes if node != preferred))

    def _episode_id(self, page_url: str) -> str:
        if not self.supports(page_url):
            raise DanmakuResolveError("Animeko弹幕地址无效")
        return urlparse(page_url).path.strip("/")

    def _record(self, row: object) -> DanmakuRecord | None:
        if not isinstance(row, dict):
            return None
        info = row.get("danmakuInfo")
        if not isinstance(info, dict):
            return None
        content = str(info.get("text") or "").strip()
        if not content:
            return None
        try:
            time_offset = max(0.0, float(info.get("playTime")) / 1000.0)
            color = int(info.get("color"))
        except (TypeError, ValueError):
            return None
        if color < 0 or color > 0xFFFFFF:
            color = 0xFFFFFF
        return DanmakuRecord(
            time_offset=time_offset,
            pos={"NORMAL": 1, "TOP": 5, "BOTTOM": 4}.get(
                str(info.get("location") or "").upper(),
                1,
            ),
            color=str(color),
            content=content,
        )
```

- [ ] **Step 4: Run Animeko tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_animeko_provider.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit the Animeko provider**

```bash
git add src/atv_player/danmaku/providers/animeko.py tests/test_danmaku_animeko_provider.py
git commit -m "feat(danmaku): add Animeko provider"
```

---

### Task 4: Register providers, labels, ordering, and cached URL routing

**Files:**

- Modify: `src/atv_player/danmaku/providers/__init__.py`
- Modify: `src/atv_player/danmaku/service.py`
- Modify: `tests/test_danmaku_service.py`

- [ ] **Step 1: Update service tests first**

Change both fixed-order assertions in `tests/test_danmaku_service.py` to end with:

```python
        "migu",
        "renren",
        "dandan",
        "bahamut",
        "animeko",
```

Add label and cached-routing tests:

```python
def test_new_anime_provider_labels_are_user_facing() -> None:
    providers = {
        key: FakeProvider(
            key,
            [DanmakuSearchItem(provider=key, name="迷宫饭 第1集", url=f"{key}://episode/1")],
            [],
        )
        for key in ("dandan", "bahamut", "animeko")
    }
    service = DanmakuService(
        providers,
        provider_order=["dandan", "bahamut", "animeko"],
    )

    result = service.search_danmu_sources("迷宫饭 第1集")

    assert [(group.provider, group.provider_label) for group in result.groups] == [
        ("dandan", "弹弹Play"),
        ("bahamut", "巴哈姆特"),
        ("animeko", "Animeko"),
    ]


def test_resolve_routes_cached_internal_url_without_context() -> None:
    animeko = FakeProvider("animeko", [], [DanmakuRecord(1.0, 1, "16777215", "缓存")])
    service = DanmakuService(
        {"animeko": animeko},
        provider_order=["animeko"],
    )

    xml = service.resolve_danmu("animeko://episode/4201")

    assert "缓存" in xml
    assert animeko.resolve_calls == ["animeko://episode/4201"]
```

- [ ] **Step 2: Run the service tests and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_service.py -q
```

Expected: fixed-order and label tests fail because the providers are not registered.

- [ ] **Step 3: Export and register the providers**

In `src/atv_player/danmaku/providers/__init__.py`, import the three classes and add their names to `__all__`:

```python
from atv_player.danmaku.providers.animeko import AnimekoDanmakuProvider
from atv_player.danmaku.providers.bahamut import BahamutDanmakuProvider
from atv_player.danmaku.providers.dandan import DandanDanmakuProvider
```

In `src/atv_player/danmaku/service.py`:

1. Add the three classes to the provider import tuple.
2. Extend `_PROVIDER_LABELS` with:

```python
    "dandan": "弹弹Play",
    "bahamut": "巴哈姆特",
    "animeko": "Animeko",
```

3. Extend the `providers` mapping in `create_default_danmaku_service()`:

```python
        "dandan": DandanDanmakuProvider(get=get),
        "bahamut": BahamutDanmakuProvider(get=get),
        "animeko": AnimekoDanmakuProvider(get=get, post=post),
```

4. Replace the inline fixed-order list with:

```python
    fixed_order = [
        "tencent",
        "youku",
        "bilibili",
        "iqiyi",
        "mgtv",
        "sohu",
        "migu",
        "renren",
        "dandan",
        "bahamut",
        "animeko",
    ]
    provider_order = [key for key in fixed_order if key not in disabled]
```

- [ ] **Step 4: Run provider and service tests**

Run:

```bash
uv run pytest tests/test_danmaku_dandan_provider.py tests/test_danmaku_bahamut_provider.py tests/test_danmaku_animeko_provider.py tests/test_danmaku_service.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit provider registration**

```bash
git add src/atv_player/danmaku/providers/__init__.py src/atv_player/danmaku/service.py tests/test_danmaku_service.py
git commit -m "feat(danmaku): register anime providers"
```

---

### Task 5: Settings toggles and persistence

**Files:**

- Modify: `src/atv_player/source_preferences.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_main_window_ui.py`

- [ ] **Step 1: Write persistence and UI assertions first**

In `tests/test_storage.py`, change the disabled-source round-trip test values to:

```python
    config.disabled_danmaku_provider_ids = [
        "youku",
        "dandan",
        "bahamut",
        "animeko",
    ]
```

and assert the same four-item list after loading.

In `tests/test_main_window_ui.py`, add:

```python
def test_advanced_settings_dialog_exposes_anime_danmaku_sources(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig()
    dialog = AdvancedSettingsDialog(config, save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert {
        key: dialog.danmaku_source_checkboxes[key].text()
        for key in ("dandan", "bahamut", "animeko")
    } == {
        "dandan": "弹弹Play",
        "bahamut": "巴哈姆特",
        "animeko": "Animeko",
    }

    dialog.danmaku_source_checkboxes["dandan"].setChecked(False)
    dialog.danmaku_source_checkboxes["bahamut"].setChecked(False)
    dialog.danmaku_source_checkboxes["animeko"].setChecked(False)
    dialog._save()

    assert config.disabled_danmaku_provider_ids[-3:] == [
        "dandan",
        "bahamut",
        "animeko",
    ]
```

- [ ] **Step 2: Run settings tests and verify RED**

Run:

```bash
uv run pytest tests/test_storage.py::test_settings_repository_round_trips_disabled_source_preferences -q
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py::test_advanced_settings_dialog_exposes_anime_danmaku_sources -q
```

Expected: storage drops the unknown provider IDs and the UI test raises `KeyError: 'dandan'`.

- [ ] **Step 3: Add the three preferences**

Append these entries to `DANMAKU_SOURCE_PREFERENCES` in `src/atv_player/source_preferences.py`:

```python
    SourcePreference("dandan", "弹弹Play"),
    SourcePreference("bahamut", "巴哈姆特"),
    SourcePreference("animeko", "Animeko"),
```

No storage schema migration is needed: `VALID_DANMAKU_PROVIDER_IDS` is derived from this tuple and the database column already stores JSON.

- [ ] **Step 4: Run settings tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_storage.py::test_settings_repository_round_trips_disabled_source_preferences -q
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py::test_advanced_settings_dialog_exposes_anime_danmaku_sources -q
```

Expected: both tests pass.

- [ ] **Step 5: Verify disabling affects default service construction**

Add to `tests/test_danmaku_service.py`:

```python
def test_default_service_can_disable_new_anime_providers() -> None:
    service = create_default_danmaku_service(
        disabled_provider_ids=["dandan", "bahamut", "animeko"]
    )

    assert "dandan" not in service.provider_order
    assert "bahamut" not in service.provider_order
    assert "animeko" not in service.provider_order
```

Run:

```bash
uv run pytest tests/test_danmaku_service.py::test_default_service_can_disable_new_anime_providers -q
```

Expected: pass.

- [ ] **Step 6: Commit settings support**

```bash
git add src/atv_player/source_preferences.py tests/test_storage.py tests/test_main_window_ui.py tests/test_danmaku_service.py
git commit -m "feat(settings): add anime danmaku source toggles"
```

---

### Task 6: Quality gates and full regression verification

**Files:** No new product files unless a verification failure exposes a defect in the preceding tasks.

- [ ] **Step 1: Format and lint the touched Python files**

Run:

```bash
uv run ruff format src/atv_player/danmaku/providers/dandan.py src/atv_player/danmaku/providers/bahamut.py src/atv_player/danmaku/providers/animeko.py src/atv_player/danmaku/providers/__init__.py src/atv_player/danmaku/service.py src/atv_player/source_preferences.py tests/test_danmaku_dandan_provider.py tests/test_danmaku_bahamut_provider.py tests/test_danmaku_animeko_provider.py tests/test_danmaku_service.py tests/test_storage.py tests/test_main_window_ui.py
uv run ruff check src/atv_player/danmaku/providers/dandan.py src/atv_player/danmaku/providers/bahamut.py src/atv_player/danmaku/providers/animeko.py src/atv_player/danmaku/providers/__init__.py src/atv_player/danmaku/service.py src/atv_player/source_preferences.py tests/test_danmaku_dandan_provider.py tests/test_danmaku_bahamut_provider.py tests/test_danmaku_animeko_provider.py tests/test_danmaku_service.py tests/test_storage.py tests/test_main_window_ui.py
```

Expected: formatting completes and Ruff reports no errors. Review the format diff before continuing.

- [ ] **Step 2: Run the focused danmaku and settings suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_danmaku_dandan_provider.py tests/test_danmaku_bahamut_provider.py tests/test_danmaku_animeko_provider.py tests/test_danmaku_service.py tests/test_storage.py tests/test_main_window_ui.py -q
```

Expected: all selected tests pass. The unrelated pre-existing `src/atv_player/app.py` and `tests/test_app.py` changes are not part of this command and must remain untouched.

- [ ] **Step 3: Run static type checking**

Run:

```bash
npx --yes pyright
```

Expected: zero Pyright errors.

- [ ] **Step 4: Run the complete test suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest -q
```

Expected: the complete suite passes. Record the exact pass count in the final handoff.

- [ ] **Step 5: Verify dependency packaging and module imports**

Run:

```bash
uv build
uv run python -c "from atv_player.danmaku.providers import AnimekoDanmakuProvider, BahamutDanmakuProvider, DandanDanmakuProvider; assert AnimekoDanmakuProvider.key == 'animeko'; assert BahamutDanmakuProvider.key == 'bahamut'; assert DandanDanmakuProvider.key == 'dandan'"
```

Expected: wheel and sdist build successfully and the import command exits zero.

- [ ] **Step 6: Inspect final scope and commit formatting-only changes if any**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Expected: only files named in this plan plus the user's pre-existing `src/atv_player/app.py` and `tests/test_app.py` modifications are changed. If Ruff changed planned files after the preceding commits, commit only those planned files:

```bash
git add src/atv_player/danmaku/providers/dandan.py src/atv_player/danmaku/providers/bahamut.py src/atv_player/danmaku/providers/animeko.py src/atv_player/danmaku/providers/__init__.py src/atv_player/danmaku/service.py src/atv_player/source_preferences.py tests/test_danmaku_dandan_provider.py tests/test_danmaku_bahamut_provider.py tests/test_danmaku_animeko_provider.py tests/test_danmaku_service.py tests/test_storage.py tests/test_main_window_ui.py
git commit -m "style: format anime danmaku providers"
```

Do not stage or commit `src/atv_player/app.py` or `tests/test_app.py` unless the user explicitly confirms those changes belong to this feature.
