# Sohu Danmaku Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sohu as a generic danmaku provider that supports candidate search, grouped source switching, and danmaku resolution for drama, anime, movie, and variety content.

**Architecture:** Implement a new `SohuDanmakuProvider` that uses Sohu search and playlist APIs first, then falls back to playback-page parsing when `aid` or `vid` is missing. Keep `DanmakuService` unchanged at the contract level, but register Sohu in the provider exports, provider label map, and default provider order so the existing grouped-source UI can consume Sohu results without UI changes.

**Tech Stack:** Python 3.12, `httpx`, pytest, existing `atv_player.danmaku` provider and service architecture.

---

## File Map

- `src/atv_player/danmaku/providers/sohu.py`
  New provider implementation with search, playlist expansion, cached resolve context, page fallback parsing, segment fetching, and comment mapping.
- `src/atv_player/danmaku/providers/__init__.py`
  Export `SohuDanmakuProvider`.
- `src/atv_player/danmaku/service.py`
  Register the Sohu provider label and include Sohu in `create_default_danmaku_service()` provider order.
- `tests/test_danmaku_sohu_provider.py`
  New provider-focused tests for search filtering, candidate expansion, context priming, page fallback, and segment parsing.
- `tests/test_danmaku_service.py`
  Small service-level regressions proving default service order and grouped-source labels include Sohu.

### Task 1: Add the failing Sohu search-side provider tests

**Files:**
- Create: `tests/test_danmaku_sohu_provider.py`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_filters_trailer_noise_and_expands_episode_candidates`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_prefers_single_main_movie_candidate`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_keeps_variety_issue_candidates`

- [ ] **Step 1: Write the failing search-side tests**

Create `tests/test_danmaku_sohu_provider.py` with these helpers and tests:

```python
import httpx

from atv_player.danmaku.providers.sohu import SohuDanmakuProvider


def test_sohu_search_filters_trailer_noise_and_expands_episode_candidates() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            assert kwargs["params"]["key"] == "剑来"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "noise-1",
                                "album_name": "剑来预告",
                                "is_trailer": 1,
                            },
                            {
                                "aid": "200001",
                                "album_name": "剑来",
                                "year": 2026,
                                "meta": [{"txt": "动漫 | 内地 | 2026年"}],
                            },
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            assert kwargs["params"]["playlistid"] == "200001"
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "9001",
                            "video_name": "第1集",
                            "url_html5": "https://tv.sohu.com/v/dXMvOTAwMS8=.html",
                            "playLength": 1420,
                        },
                        {
                            "vid": "9002",
                            "video_name": "第2集",
                            "url_html5": "https://tv.sohu.com/v/dXMvOTAwMi8=.html",
                            "playLength": 1438,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("剑来", original_name="剑来 2集")

    assert [(item.provider, item.name, item.url, item.duration_seconds) for item in items] == [
        ("sohu", "剑来 第2集", "https://tv.sohu.com/v/dXMvOTAwMi8=.html", 1438),
    ]
    assert items[0].resolve_context["aid"] == "200001"
    assert items[0].resolve_context["vid"] == "9002"


def test_sohu_search_prefers_single_main_movie_candidate() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "300001",
                                "album_name": "疯狂动物城2",
                                "year": 2026,
                                "meta": [{"txt": "电影 | 美国 | 2026年"}],
                            }
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "movie-main",
                            "video_name": "疯狂动物城2",
                            "url_html5": "https://tv.sohu.com/v/movie-main.html",
                            "playLength": 5935,
                        },
                        {
                            "vid": "movie-trailer",
                            "video_name": "疯狂动物城2 预告片",
                            "url_html5": "https://tv.sohu.com/v/movie-trailer.html",
                            "playLength": 95,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("疯狂动物城2")

    assert [(item.name, item.url, item.duration_seconds) for item in items] == [
        ("疯狂动物城2", "https://tv.sohu.com/v/movie-main.html", 5935),
    ]


def test_sohu_search_keeps_variety_issue_candidates() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://m.so.tv.sohu.com/search/pc/keyword":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "aid": "400001",
                                "album_name": "哈哈哈哈哈第6季",
                                "year": 2026,
                                "meta": [{"txt": "综艺 | 内地 | 2026年"}],
                            }
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "vid": "issue-0405",
                            "video_name": "20260405期 第1期下",
                            "url_html5": "https://tv.sohu.com/v/issue-0405.html",
                            "playLength": 5480,
                        },
                        {
                            "vid": "issue-0411",
                            "video_name": "20260411期 第2期上",
                            "url_html5": "https://tv.sohu.com/v/issue-0411.html",
                            "playLength": 5511,
                        },
                    ]
                },
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)

    items = provider.search("哈哈哈哈哈第六季", original_name="哈哈哈哈哈第六季 20260411期 第2期上")

    assert [item.name for item in items] == ["哈哈哈哈哈第6季 20260411期 第2期上"]
    assert items[0].resolve_context["variety_year"] == "20260411"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py::test_sohu_search_filters_trailer_noise_and_expands_episode_candidates tests/test_danmaku_sohu_provider.py::test_sohu_search_prefers_single_main_movie_candidate tests/test_danmaku_sohu_provider.py::test_sohu_search_keeps_variety_issue_candidates -v
```

Expected: FAIL with `ModuleNotFoundError` for `atv_player.danmaku.providers.sohu` or missing `SohuDanmakuProvider`.

### Task 2: Implement the Sohu provider search path and register it

**Files:**
- Create: `src/atv_player/danmaku/providers/sohu.py`
- Modify: `src/atv_player/danmaku/providers/__init__.py`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_filters_trailer_noise_and_expands_episode_candidates`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_prefers_single_main_movie_candidate`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_search_keeps_variety_issue_candidates`

- [ ] **Step 1: Add the provider skeleton, constants, and constructor**

Create `src/atv_player/danmaku/providers/sohu.py` with this starting structure:

```python
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from atv_player.danmaku.errors import DanmakuResolveError, DanmakuSearchError
from atv_player.danmaku.models import DanmakuRecord, DanmakuSearchItem
from atv_player.danmaku.utils import extract_episode_number, extract_variety_issue_key, normalize_name


class SohuDanmakuProvider:
    key = "sohu"
    _SEARCH_URL = "https://m.so.tv.sohu.com/search/pc/keyword"
    _PLAYLIST_URL = "https://pl.hd.sohu.com/videolist"
    _NOISE_KEYWORDS = ("预告", "花絮", "片段", "特辑", "采访", "速看", "解说")
    _POSITION_MAP = {1: 1, 4: 5, 5: 4}

    def __init__(self, get=httpx.get) -> None:
        self._get = get
        self._resolve_context_by_url: dict[str, dict[str, str | int | None]] = {}
```

- [ ] **Step 2: Implement `supports()`, `prime_resolve_context()`, and the search entrypoint**

Add these methods:

```python
    def supports(self, page_url: str) -> bool:
        return "sohu.com" in page_url

    def prime_resolve_context(self, page_url: str, resolve_context: dict[str, str | int | None]) -> None:
        self._resolve_context_by_url[page_url] = dict(resolve_context)

    def search(self, name: str, original_name: str | None = None) -> list[DanmakuSearchItem]:
        response = self._get(
            self._SEARCH_URL,
            params={"key": name, "type": "1", "page": "1", "page_size": "20"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://so.tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("搜狐弹幕搜索结果解析失败") from exc
        items = (payload.get("data") or {}).get("items")
        if not isinstance(items, list):
            raise DanmakuSearchError("搜狐弹幕搜索结果解析失败")
        return self._expand_search_items(items, query_name=name, original_name=original_name or name)
```

- [ ] **Step 3: Implement album filtering and playlist expansion helpers**

Add helpers that produce `DanmakuSearchItem` objects:

```python
    def _expand_search_items(self, raw_items: list[dict], *, query_name: str, original_name: str) -> list[DanmakuSearchItem]:
        requested_episode = extract_episode_number(original_name)
        requested_issue_key = extract_variety_issue_key(normalize_name(original_name))
        candidates: list[DanmakuSearchItem] = []
        for raw in raw_items:
            album = self._normalize_album(raw)
            if album is None:
                continue
            expanded = self._expand_album(album, requested_episode=requested_episode, requested_issue_key=requested_issue_key)
            candidates.extend(expanded)
        return candidates

    def _normalize_album(self, raw: dict) -> dict[str, str | int] | None:
        aid = str(raw.get("aid") or "").strip()
        title = str(raw.get("album_name") or "").replace("<<<", "").replace(">>>", "").strip()
        if not aid or not title:
            return None
        if int(raw.get("is_trailer") or 0) == 1:
            return None
        corner_mark = raw.get("corner_mark") or {}
        if str(corner_mark.get("text") or "").strip() == "预告":
            return None
        if any(keyword in title for keyword in self._NOISE_KEYWORDS):
            return None
        return {
            "aid": aid,
            "title": title,
            "year": int(raw.get("year") or 0),
            "category_name": self._category_name(raw),
        }
```

- [ ] **Step 4: Implement movie, episodic, and variety candidate shaping**

Use one playlist fetch plus content-shape helpers:

```python
    def _expand_album(
        self,
        album: dict[str, str | int],
        *,
        requested_episode: int | None,
        requested_issue_key: str | None,
    ) -> list[DanmakuSearchItem]:
        videos = self._playlist_videos(str(album["aid"]))
        if not videos:
            return [self._album_fallback_item(album)]
        category_name = str(album.get("category_name") or "")
        if "电影" in category_name:
            best = self._pick_movie_video(str(album["title"]), videos)
            return [self._video_to_item(album, best)] if best is not None else [self._album_fallback_item(album)]
        items = [self._video_to_item(album, video) for video in videos if self._video_to_item(album, video) is not None]
        items = [item for item in items if item is not None]
        if requested_issue_key:
            matched = [item for item in items if item.resolve_context.get("variety_year") == requested_issue_key]
            if matched:
                return matched
        if requested_episode is not None:
            matched = [item for item in items if extract_episode_number(item.name) == requested_episode]
            if matched:
                return matched
            return items[:3]
        return items
```

- [ ] **Step 5: Export the provider**

Update `src/atv_player/danmaku/providers/__init__.py`:

```python
from atv_player.danmaku.providers.sohu import SohuDanmakuProvider

__all__ = [
    "BilibiliDanmakuProvider",
    "DanmakuProvider",
    "IqiyiDanmakuProvider",
    "MgtvDanmakuProvider",
    "SohuDanmakuProvider",
    "TencentDanmakuProvider",
    "YoukuDanmakuProvider",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py::test_sohu_search_filters_trailer_noise_and_expands_episode_candidates tests/test_danmaku_sohu_provider.py::test_sohu_search_prefers_single_main_movie_candidate tests/test_danmaku_sohu_provider.py::test_sohu_search_keeps_variety_issue_candidates -v
```

Expected: PASS with 3 passing tests.

- [ ] **Step 7: Commit the search-side implementation**

Run:

```bash
git add src/atv_player/danmaku/providers/sohu.py src/atv_player/danmaku/providers/__init__.py tests/test_danmaku_sohu_provider.py docs/superpowers/plans/2026-05-21-sohu-danmaku-provider.md
git commit -m "feat: add sohu danmaku search provider"
```

Expected: commit succeeds with only the Sohu provider search and plan/test changes staged.

### Task 3: Add the failing Sohu resolve-side tests

**Files:**
- Modify: `tests/test_danmaku_sohu_provider.py`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_resolve_uses_primed_context_and_maps_segment_comments`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_resolve_falls_back_to_page_html_for_aid_and_vid`
- Verify: `tests/test_danmaku_sohu_provider.py::test_sohu_resolve_raises_when_all_segments_are_unusable`

- [ ] **Step 1: Write the failing resolve-side tests**

Append these tests to `tests/test_danmaku_sohu_provider.py`:

```python
import pytest

from atv_player.danmaku.errors import DanmakuResolveError


def test_sohu_resolve_uses_primed_context_and_maps_segment_comments() -> None:
    calls: list[tuple[str, dict | None]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs.get("params")))
        if url == "https://api.danmu.tv.sohu.com/dmh5/dmListAll":
            return httpx.Response(
                200,
                json={
                    "info": {
                        "comments": [
                            {"i": "c1", "c": "第一条", "v": 12.5, "uid": "u1", "created": "1710000000", "t": {"p": 1, "c": "#ffffff"}},
                            {"i": "c2", "c": "顶部", "v": 18.0, "uid": "u2", "created": "1710000001", "t": {"p": 4, "c": "#ff0000"}},
                        ]
                    }
                },
            )
        if url == "https://pl.hd.sohu.com/videolist":
            return httpx.Response(200, json={"videos": [{"vid": "9002", "playLength": 120}]})
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)
    provider.prime_resolve_context(
        "https://tv.sohu.com/v/dXMvOTAwMi8=.html",
        {"aid": "200001", "vid": "9002", "duration_seconds": 120},
    )

    records = provider.resolve("https://tv.sohu.com/v/dXMvOTAwMi8=.html")

    assert [(record.time_offset, record.pos, record.color, record.content) for record in records] == [
        (12.5, 1, "16777215", "第一条"),
        (18.0, 5, "16711680", "顶部"),
    ]
    assert all(url != "https://tv.sohu.com/v/dXMvOTAwMi8=.html" for url, _ in calls)


def test_sohu_resolve_falls_back_to_page_html_for_aid_and_vid() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://tv.sohu.com/v/demo.html":
            return httpx.Response(
                200,
                text='<html><input id="aid" value="500001" /><script>var vid="9999";</script></html>',
            )
        if url == "https://api.danmu.tv.sohu.com/dmh5/dmListAll":
            return httpx.Response(
                200,
                json={"info": {"comments": [{"i": "c1", "c": "回退成功", "v": 3.0, "uid": "u1", "created": "1710000002", "t": {"p": 5, "c": "#00ff00"}}]}},
            )
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)
    provider._duration_for_video = lambda aid, vid: 60

    records = provider.resolve("https://tv.sohu.com/v/demo.html")

    assert [(record.time_offset, record.pos, record.color, record.content) for record in records] == [
        (3.0, 4, "65280", "回退成功"),
    ]


def test_sohu_resolve_raises_when_all_segments_are_unusable() -> None:
    def fake_get(url: str, **kwargs):
        if url == "https://api.danmu.tv.sohu.com/dmh5/dmListAll":
            return httpx.Response(200, text="{bad json")
        raise AssertionError(url)

    provider = SohuDanmakuProvider(get=fake_get)
    provider.prime_resolve_context("https://tv.sohu.com/v/demo.html", {"aid": "500001", "vid": "9999", "duration_seconds": 60})

    with pytest.raises(DanmakuResolveError, match="搜狐弹幕分段解析失败"):
        provider.resolve("https://tv.sohu.com/v/demo.html")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py::test_sohu_resolve_uses_primed_context_and_maps_segment_comments tests/test_danmaku_sohu_provider.py::test_sohu_resolve_falls_back_to_page_html_for_aid_and_vid tests/test_danmaku_sohu_provider.py::test_sohu_resolve_raises_when_all_segments_are_unusable -v
```

Expected: FAIL because `resolve()` and the helper methods are not implemented yet.

### Task 4: Implement the Sohu resolve path and make the provider tests pass

**Files:**
- Modify: `src/atv_player/danmaku/providers/sohu.py`
- Verify: `tests/test_danmaku_sohu_provider.py`

- [ ] **Step 1: Implement `resolve()` and identifier fallback**

Add the main resolve flow:

```python
    def resolve(self, page_url: str) -> list[DanmakuRecord]:
        context = dict(self._resolve_context_by_url.get(page_url) or {})
        aid = str(context.get("aid") or "").strip()
        vid = str(context.get("vid") or "").strip()
        duration_seconds = int(context.get("duration_seconds") or 0)
        if not aid or not vid:
            page_aid, page_vid = self._extract_ids_from_page(page_url)
            aid = aid or page_aid
            vid = vid or page_vid
        if not aid or not vid:
            raise DanmakuResolveError("搜狐页面缺少 aid 或 vid")
        duration_seconds = duration_seconds or self._duration_for_video(aid, vid)
        records = self._fetch_danmaku_records(aid, vid, duration_seconds or 300)
        if not records:
            raise DanmakuResolveError("搜狐弹幕分段解析失败")
        return sorted(records, key=lambda record: (record.time_offset, record.content))
```

- [ ] **Step 2: Implement page extraction, duration lookup, and segment requests**

Add these helpers:

```python
    def _extract_ids_from_page(self, page_url: str) -> tuple[str, str]:
        response = self._get(
            page_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        aid = re.search(r'id="aid"[^>]*value=["\\\'](\\d+)["\\\']', response.text)
        playlist_id = re.search(r'playlistId="(\\d+)"', response.text)
        vid = re.search(r'vid="(\\d+)"', response.text)
        return (
            (aid.group(1) if aid else (playlist_id.group(1) if playlist_id else "")),
            vid.group(1) if vid else "",
        )

    def _duration_for_video(self, aid: str, vid: str) -> int:
        for video in self._playlist_videos(aid):
            if str(video.get("vid") or "") == vid:
                return int(video.get("playLength") or 0)
        return 0

    def _fetch_danmaku_records(self, aid: str, vid: str, duration_seconds: int) -> list[DanmakuRecord]:
        records: list[DanmakuRecord] = []
        failures = 0
        seen: set[tuple[float, str]] = set()
        for start in range(0, max(duration_seconds, 1), 300):
            response = self._get(
                "https://api.danmu.tv.sohu.com/dmh5/dmListAll",
                params={
                    "act": "dmlist_v2",
                    "vid": vid,
                    "aid": aid,
                    "pct": "2",
                    "time_begin": start,
                    "time_end": min(start + 300, duration_seconds),
                    "dct": "1",
                    "request_from": "h5_js",
                },
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
                follow_redirects=True,
                timeout=10.0,
            )
            try:
                payload = response.json()
            except Exception:
                failures += 1
                continue
            for comment in ((payload.get("info") or {}).get("comments") or []):
                record = self._comment_to_record(comment)
                if record is None:
                    continue
                key = (record.time_offset, record.content)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
        if failures > 0 and not records:
            raise DanmakuResolveError("搜狐弹幕分段解析失败")
        return records
```

- [ ] **Step 3: Implement comment mapping and search-side helpers used by resolve**

Add the remaining helpers:

```python
    def _playlist_videos(self, aid: str) -> list[dict]:
        response = self._get(
            self._PLAYLIST_URL,
            params={"playlistid": aid, "api_key": "f351515304020cad28c92f70f002261c"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://tv.sohu.com/"},
            follow_redirects=True,
            timeout=10.0,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise DanmakuSearchError("搜狐播放列表解析失败") from exc
        videos = payload.get("videos")
        return videos if isinstance(videos, list) else []

    def _comment_to_record(self, comment: dict) -> DanmakuRecord | None:
        content = str(comment.get("c") or "").strip()
        if not content:
            return None
        raw_color = str(((comment.get("t") or {}).get("c")) or "#ffffff").lstrip("#")
        position = int(((comment.get("t") or {}).get("p")) or 1)
        return DanmakuRecord(
            time_offset=round(float(comment.get("v") or 0), 3),
            pos=self._POSITION_MAP.get(position, 1),
            color=str(int(raw_color, 16)),
            content=content,
        )
```

- [ ] **Step 4: Run the full provider test file**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py -v
```

Expected: PASS for all new Sohu provider search and resolve tests.

- [ ] **Step 5: Commit the resolve-side implementation**

Run:

```bash
git add src/atv_player/danmaku/providers/sohu.py tests/test_danmaku_sohu_provider.py docs/superpowers/plans/2026-05-21-sohu-danmaku-provider.md
git commit -m "feat: add sohu danmaku resolution"
```

Expected: commit succeeds with the resolve implementation and tests staged.

### Task 5: Add service integration tests and wire Sohu into the default service

**Files:**
- Modify: `tests/test_danmaku_service.py`
- Modify: `src/atv_player/danmaku/service.py`
- Verify: `tests/test_danmaku_service.py::test_default_service_has_fixed_provider_order`
- Verify: `tests/test_danmaku_service.py::test_search_danmu_sources_uses_sohu_provider_label`

- [ ] **Step 1: Add the failing service tests**

Update `tests/test_danmaku_service.py` with these assertions:

```python
def test_default_service_has_fixed_provider_order() -> None:
    service = create_default_danmaku_service()

    assert service.provider_order == ["tencent", "youku", "bilibili", "iqiyi", "mgtv", "sohu"]


def test_search_danmu_sources_uses_sohu_provider_label() -> None:
    sohu = FakeProvider(
        "sohu",
        [DanmakuSearchItem(provider="sohu", name="剑来 第1集", url="https://tv.sohu.com/v/demo.html", ratio=0.8, simi=0.8)],
        [],
    )
    service = DanmakuService({"sohu": sohu}, provider_order=["sohu"])

    result = service.search_danmu_sources("剑来 第1集")

    assert result.groups[0].provider == "sohu"
    assert result.groups[0].provider_label == "搜狐"
    assert result.default_option_url == "https://tv.sohu.com/v/demo.html"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_danmaku_service.py::test_default_service_has_fixed_provider_order tests/test_danmaku_service.py::test_search_danmu_sources_uses_sohu_provider_label -v
```

Expected: FAIL because `service.provider_order` does not include `sohu` and `_PROVIDER_LABELS` lacks `搜狐`.

- [ ] **Step 3: Register Sohu in `DanmakuService`**

Update `src/atv_player/danmaku/service.py`:

```python
from atv_player.danmaku.providers import (
    BilibiliDanmakuProvider,
    IqiyiDanmakuProvider,
    MgtvDanmakuProvider,
    SohuDanmakuProvider,
    TencentDanmakuProvider,
    YoukuDanmakuProvider,
)

_PROVIDER_LABELS = {
    "tencent": "腾讯",
    "youku": "优酷",
    "bilibili": "B站",
    "iqiyi": "爱奇艺",
    "mgtv": "芒果",
    "sohu": "搜狐",
}

def create_default_danmaku_service(get=httpx.get, post=httpx.post) -> DanmakuService:
    providers = {
        "tencent": TencentDanmakuProvider(get=get, post=post),
        "youku": YoukuDanmakuProvider(get=get, post=post),
        "bilibili": BilibiliDanmakuProvider(get=get),
        "iqiyi": IqiyiDanmakuProvider(get=get),
        "mgtv": MgtvDanmakuProvider(get=get),
        "sohu": SohuDanmakuProvider(get=get),
    }
    return DanmakuService(providers, provider_order=["tencent", "youku", "bilibili", "iqiyi", "mgtv", "sohu"])
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run:

```bash
uv run pytest tests/test_danmaku_service.py::test_default_service_has_fixed_provider_order tests/test_danmaku_service.py::test_search_danmu_sources_uses_sohu_provider_label -v
```

Expected: PASS with 2 passing tests.

- [ ] **Step 5: Run the focused danmaku regression subset**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py tests/test_danmaku_service.py -k "sohu or fixed_provider_order or provider_label" -v
```

Expected: PASS for the new Sohu provider tests and the updated service integration tests.

- [ ] **Step 6: Commit the service integration**

Run:

```bash
git add src/atv_player/danmaku/service.py tests/test_danmaku_service.py docs/superpowers/plans/2026-05-21-sohu-danmaku-provider.md
git commit -m "feat: register sohu danmaku provider"
```

Expected: commit succeeds with the service integration changes staged.

### Task 6: Final verification and cleanup

**Files:**
- Verify only: `tests/test_danmaku_sohu_provider.py`
- Verify only: `tests/test_danmaku_service.py`

- [ ] **Step 1: Run the complete targeted verification suite**

Run:

```bash
uv run pytest tests/test_danmaku_sohu_provider.py tests/test_danmaku_service.py -v
```

Expected: PASS with the new provider coverage plus the full danmaku service regression file staying green.

- [ ] **Step 2: Review the diff before handoff**

Run:

```bash
git diff --stat HEAD~3..HEAD
```

Expected: only Sohu provider, provider registry, service integration, tests, and this plan file appear in the summary.
