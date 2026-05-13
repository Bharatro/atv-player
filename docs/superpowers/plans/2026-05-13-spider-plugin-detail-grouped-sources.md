# Spider Plugin Detail Grouped Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `detailContent().group` support so spider plugins can explicitly return two-level playback source groups, with full fallback to `vod_play_from` and `vod_play_url` when `group` is absent or invalid.

**Architecture:** Keep the existing flat playlist and grouped-source player model intact, and teach `SpiderPluginController.build_request()` to prefer a new `group` payload when it parses into at least one valid leaf source. Parse `group` directly into `PlaybackSourceGroup` plus one-item `PlayItem` leaf playlists, and only call the legacy `vod_play_from` / `vod_play_url` path when the new payload is missing or unusable.

**Tech Stack:** Python 3.12, PySide6 dataclasses, pytest

---

## File Structure

- `src/atv_player/plugins/controller.py`
  Responsibility: parse the optional `group` payload, map it into `PlaybackSourceGroup` / `PlayItem`, and keep the old route parsing as fallback.
- `tests/test_spider_plugin_controller.py`
  Responsibility: lock the new `group` contract, fallback behavior, and direct-media vs share-link item mapping.

### Task 1: Add Failing Tests For `detailContent().group`

**Files:**
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_spider_controller_uses_detail_group_payload_when_present() -> None:
    class GroupPayloadSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "红果短剧",
                        "vod_play_from": "旧线路",
                        "vod_play_url": "第1集$http://legacy/1.m3u8",
                        "group": [
                            {
                                "name": "百度",
                                "media": [
                                    {"name": "影视标题1", "url": "https://pan.baidu.com/s/xxx"},
                                ],
                            },
                            {
                                "name": "夸克",
                                "media": [
                                    {"name": "影视标题10", "url": "https://pan.quark.cn/s/yyy"},
                                ],
                            },
                        ],
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(GroupPayloadSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert [group.label for group in request.source_groups] == ["百度", "夸克"]
    assert [source.label for source in request.source_groups[0].sources] == ["影视标题1"]
    assert [source.label for source in request.source_groups[1].sources] == ["影视标题10"]
    assert len(request.playlists) == 2
    assert request.playlists[0][0].title == "影视标题1"
    assert request.playlists[0][0].url == ""
    assert request.playlists[0][0].vod_id == "https://pan.baidu.com/s/xxx"


def test_spider_controller_falls_back_to_legacy_routes_when_group_payload_is_invalid() -> None:
    class InvalidGroupSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "电影",
                        "vod_play_from": "备用线$$$极速线",
                        "vod_play_url": "正片$http://a/1.m3u8$$$正片$http://b/1.m3u8",
                        "group": [
                            {"name": "百度", "media": []},
                            {"name": "", "media": [{"name": "坏数据", "url": "https://pan.baidu.com/s/bad"}]},
                        ],
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(InvalidGroupSpider(), plugin_name="电影", search_enabled=True)
    request = controller.build_request("detail-1")

    assert [group.label for group in request.source_groups] == ["备用线", "极速线"]
    assert request.playlists[0][0].url == "http://a/1.m3u8"
    assert request.playlists[1][0].url == "http://b/1.m3u8"


def test_spider_controller_maps_direct_media_urls_from_group_payload() -> None:
    class DirectMediaGroupSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "纪录片",
                        "group": [
                            {
                                "name": "直链",
                                "media": [
                                    {"name": "正片", "url": "https://media.example/movie.m3u8"},
                                ],
                            }
                        ],
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(DirectMediaGroupSpider(), plugin_name="纪录片", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.playlists[0][0].url == "https://media.example/movie.m3u8"
    assert request.playlists[0][0].vod_id == ""
    assert request.playlists[0][0].title == "正片"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_uses_detail_group_payload_when_present tests/test_spider_plugin_controller.py::test_spider_controller_falls_back_to_legacy_routes_when_group_payload_is_invalid tests/test_spider_plugin_controller.py::test_spider_controller_maps_direct_media_urls_from_group_payload -v`

Expected: FAIL because `SpiderPluginController.build_request()` ignores `raw_detail["group"]` and only parses `vod_play_from` / `vod_play_url`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_spider_plugin_controller.py
git commit -m "test: cover spider detail grouped source payload"
```

### Task 2: Parse `group` And Fall Back To Legacy Routes

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the minimal parsing helpers**

```python
def _build_grouped_play_item(self, detail: VodItem, raw_media: Mapping[object, object]) -> PlayItem | None:
    display_name = str(raw_media.get("name") or "").strip()
    raw_url = str(raw_media.get("url") or "").strip()
    if not raw_url:
        return None
    title = display_name or raw_url
    is_drive_link = _looks_like_drive_share_link(raw_url)
    is_media_url = _looks_like_media_url(raw_url) and not is_drive_link
    return PlayItem(
        title=title,
        url=raw_url if is_media_url else "",
        media_title=detail.vod_name,
        path=detail.vod_id if is_drive_link else "",
        vod_id="" if is_media_url else raw_url,
        index=0,
        play_source=title,
    )


def _build_grouped_sources_from_payload(
    self,
    detail: VodItem,
    payload: object,
) -> tuple[list[PlaybackSourceGroup], list[list[PlayItem]]]:
    if not isinstance(payload, list):
        return [], []
    source_groups: list[PlaybackSourceGroup] = []
    playlists: list[list[PlayItem]] = []
    for raw_group in payload:
        if not isinstance(raw_group, Mapping):
            continue
        group_name = str(raw_group.get("name") or "").strip()
        raw_media_list = raw_group.get("media")
        if not group_name or not isinstance(raw_media_list, list):
            continue
        sources: list[PlaybackSource] = []
        for raw_media in raw_media_list:
            if not isinstance(raw_media, Mapping):
                continue
            item = self._build_grouped_play_item(detail, raw_media)
            if item is None:
                continue
            playlist = [item]
            playlists.append(playlist)
            sources.append(PlaybackSource(label=item.title, playlist=playlist))
        if sources:
            source_groups.append(PlaybackSourceGroup(label=group_name, sources=sources))
    return source_groups, playlists
```

- [ ] **Step 2: Wire the new parsing into `build_request()`**

```python
try:
    raw_detail = payload["list"][0]
    detail = _map_vod_item(raw_detail)
    detail.detail_fields = _map_playback_detail_fields(
        raw_detail.get("ext") if isinstance(raw_detail, Mapping) else None
    )
except (KeyError, IndexError) as exc:
    raise ValueError(f"没有可播放的项目: {vod_id}") from exc

source_groups: list[PlaybackSourceGroup] = []
playlists: list[list[PlayItem]] = []
if isinstance(raw_detail, Mapping):
    source_groups, playlists = self._build_grouped_sources_from_payload(detail, raw_detail.get("group"))
if not playlists:
    playlists = self._build_playlist(detail)
    source_groups = self._build_source_groups_from_playlists(playlists)
```

```python
playlist = playlists[0]
...
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
...
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

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_spider_controller_uses_detail_group_payload_when_present tests/test_spider_plugin_controller.py::test_spider_controller_falls_back_to_legacy_routes_when_group_payload_is_invalid tests/test_spider_plugin_controller.py::test_spider_controller_maps_direct_media_urls_from_group_payload -v`

Expected: PASS

- [ ] **Step 4: Run the wider spider controller regression slice**

Run: `uv run pytest tests/test_spider_plugin_controller.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: support spider detail grouped sources"
```

## Self-Review

- Spec coverage:
  - `group` schema mapping is covered by Task 2 helper methods.
  - `group` valid -> ignore old routes is covered by Task 1 test 1.
  - `group` invalid -> fallback is covered by Task 1 test 2.
  - direct-media vs share-link item mapping is covered by Task 1 test 3.
- Placeholder scan:
  - No `TODO`, `TBD`, or vague “handle edge cases” steps remain.
  - Each code-changing step includes concrete code.
- Type consistency:
  - The plan uses `PlaybackSourceGroup`, `PlaybackSource`, `PlayItem`, `source_groups`, and `playlists` consistently with the current controller code.

