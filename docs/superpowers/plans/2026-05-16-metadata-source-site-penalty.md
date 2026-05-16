# Metadata Source Site Penalty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Tencent and iQiyi metadata auto-match prefer native-site search results over third-party mirror results, and stop showing `来源站点` in metadata detail fields.

**Architecture:** Keep the global `score_match(...)` behavior unchanged and apply provider-specific score penalties inside `IqiyiMetadataProvider.search(...)` and `TencentMetadataProvider.search(...)`. Remove the `来源站点` row at the provider-detail layer so merge and player-detail UI change naturally without any extra rendering logic.

**Tech Stack:** Python 3.13, dataclasses, `httpx`, existing metadata provider layer, pytest

---

### Task 1: Lock iQiyi native-site scoring and detail-field behavior with tests

**Files:**
- Modify: `tests/test_metadata_iqiyi_provider.py`
- Test: `tests/test_metadata_iqiyi_provider.py`

- [ ] **Step 1: Write the failing iQiyi tests**

```python
def test_iqiyi_metadata_provider_search_penalizes_non_native_site_results() -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
        return JsonResponse(
            {
                "data": {
                    "templates": [
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来 第二季",
                                "siteId": "qq",
                                "siteName": "腾讯视频",
                                "pageUrl": "https://www.iqiyi.com/v_third_party.html",
                                "year": {"value": "2025"},
                            },
                        },
                        {
                            "template": 101,
                            "albumInfo": {
                                "title": "剑来 第二季",
                                "siteId": "iqiyi",
                                "siteName": "爱奇艺",
                                "pageUrl": "https://www.iqiyi.com/v_native.html",
                                "year": {"value": "2025"},
                            },
                        },
                    ]
                }
            }
        )

    provider = IqiyiMetadataProvider(get=fake_get)

    matches = provider.search(MetadataQuery(title="剑来 第二季", year="2025", category_name="动漫"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("剑来 第二季", "https://www.iqiyi.com/v_native.html"),
        ("剑来 第二季", "https://www.iqiyi.com/v_third_party.html"),
    ]
    assert matches[0].score > matches[1].score


def test_iqiyi_metadata_provider_detail_omits_source_site_field() -> None:
    payload = {
        "data": {
            "templates": [
                {
                    "template": 103,
                    "albumInfo": {
                        "title": "疯狂动物城2",
                        "siteId": "iqiyi",
                        "siteName": "爱奇艺",
                        "pageUrl": "https://www.iqiyi.com/v_demo.html",
                        "year": {"value": "2025"},
                        "brief": {"value": "兔子朱迪与狐狸尼克正式组成搭档。"},
                        "releaseTime": {"key": "上映时间", "value": "2025-11-26"},
                        "timeLength": {"key": "片长", "value": "01:43:26"},
                        "baseTags": [{"value": "冒险"}, {"value": "动画"}, {"value": "喜剧"}],
                    }
                }
            ]
        }
    }
    provider = IqiyiMetadataProvider(get=lambda url, **kwargs: JsonResponse(payload))

    match = provider.search(MetadataQuery(title="疯狂动物城2", year="2025", category_name="电影"))[0]
    record = provider.get_detail(match)

    assert record.detail_fields == [
        {"label": "上映时间", "value": "2025-11-26"},
        {"label": "片长", "value": "01:43:26"},
    ]
```

- [ ] **Step 2: Run the focused iQiyi tests and verify they fail**

Run: `uv run pytest tests/test_metadata_iqiyi_provider.py -k "penalizes_non_native_site_results or omits_source_site_field" -v`

Expected: FAIL because the provider still keeps the original score order and still emits `来源站点`.

- [ ] **Step 3: Confirm the minimal iQiyi implementation shape**

```python
class IqiyiMetadataProvider:
    name = "iqiyi"
    _SEARCH_URL = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"
    _SEARCH_HEADERS = {"user-agent": "Mozilla/5.0", "referer": "https://www.iqiyi.com/"}
    _ALLOWED_TEMPLATES = {101, 102, 103}
    _NON_NATIVE_SITE_PENALTY = 0.35

    def _apply_native_site_penalty(self, match: MetadataMatch) -> float:
        site_name = str(match.raw.get("siteName") or "").strip()
        if site_name and site_name != "爱奇艺":
            return max(0.0, float(match.score or 0.0) - self._NON_NATIVE_SITE_PENALTY)
        return float(match.score or 0.0)
```

The actual implementation step in Task 3 should call this helper from `search(...)` after `score_match(...)` and should remove the `来源站点` append from `get_detail(...)`.

- [ ] **Step 4: Run the focused iQiyi tests and verify they pass**

Run: `uv run pytest tests/test_metadata_iqiyi_provider.py -k "penalizes_non_native_site_results or omits_source_site_field" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_iqiyi_provider.py src/atv_player/metadata/providers/iqiyi.py
git commit -m "feat: prefer native iqiyi metadata results"
```

### Task 2: Lock Tencent native-site scoring and detail-field behavior with tests

**Files:**
- Modify: `tests/test_metadata_tencent_provider.py`
- Test: `tests/test_metadata_tencent_provider.py`

- [ ] **Step 1: Write the failing Tencent tests**

```python
def test_tencent_metadata_provider_search_penalizes_non_native_site_results() -> None:
    def fake_post(url: str, **kwargs):
        assert url == "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
        return JsonResponse(
            {
                "data": {
                    "normalList": {
                        "itemList": [
                            {
                                "doc": {"dataType": 2, "id": "third"},
                                "videoInfo": {
                                    "title": "米小圈上学记4",
                                    "year": 2026,
                                    "playSites": [
                                        {
                                            "showName": "爱奇艺",
                                            "episodeInfoList": [
                                                {"url": "https://v.qq.com/x/cover/third/ep1.html"}
                                            ],
                                        }
                                    ],
                                },
                            },
                            {
                                "doc": {"dataType": 2, "id": "native"},
                                "videoInfo": {
                                    "title": "米小圈上学记4",
                                    "year": 2026,
                                    "playSites": [
                                        {
                                            "showName": "腾讯视频",
                                            "episodeInfoList": [
                                                {"url": "https://v.qq.com/x/cover/native/ep1.html"}
                                            ],
                                        }
                                    ],
                                },
                            },
                        ]
                    }
                }
            }
        )

    provider = TencentMetadataProvider(post=fake_post)

    matches = provider.search(MetadataQuery(title="米小圈上学记4", year="2026", category_name="少儿"))

    assert [(match.title, match.provider_id) for match in matches] == [
        ("米小圈上学记4", "https://v.qq.com/x/cover/native/ep1.html"),
        ("米小圈上学记4", "https://v.qq.com/x/cover/third/ep1.html"),
    ]
    assert matches[0].score > matches[1].score


def test_tencent_metadata_provider_detail_omits_source_site_field() -> None:
    def fake_post(url: str, **kwargs):
        return JsonResponse(
            {
                "data": {
                    "normalList": {
                        "itemList": [
                            {
                                "doc": {"dataType": 2, "id": "mzc002008bgugk0"},
                                "videoInfo": {
                                    "title": "米小圈上学记4",
                                    "year": 2026,
                                    "typeName": "少儿",
                                    "area": "内地",
                                    "language": ["普通话版"],
                                    "directors": ["赵聪"],
                                    "actors": ["郭赫轩", "陈芷琰"],
                                    "richTags": [{"text": "儿童剧", "type": 80, "uiType": 1}],
                                    "descrip": "第一条不应被使用",
                                    "playSites": [
                                        {
                                            "showName": "腾讯视频",
                                            "episodeInfoList": [
                                                {
                                                    "url": "https://v.qq.com/x/cover/mzc002008bgugk0/d4101lrdi9t.html"
                                                }
                                            ],
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                }
            }
        )

    provider = TencentMetadataProvider(post=fake_post)

    match = provider.search(MetadataQuery(title="米小圈上学记4", year="2026", category_name="少儿"))[0]
    record = provider.get_detail(match)

    assert record.detail_fields == []
```

- [ ] **Step 2: Run the focused Tencent tests and verify they fail**

Run: `uv run pytest tests/test_metadata_tencent_provider.py -k "penalizes_non_native_site_results or omits_source_site_field" -v`

Expected: FAIL because the provider still keeps the original score order and still emits `来源站点`.

- [ ] **Step 3: Confirm the minimal Tencent implementation shape**

```python
class TencentMetadataProvider:
    name = "tencent"
    _SEARCH_URL = "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch"
    _SEARCH_PARAMS = {"vversion_platform": "2"}
    _NON_NATIVE_SITE_PENALTY = 0.35

    def _apply_native_site_penalty(self, match: MetadataMatch) -> float:
        site_name = str(match.raw.get("site_name") or "").strip()
        if site_name and site_name != "腾讯视频":
            return max(0.0, float(match.score or 0.0) - self._NON_NATIVE_SITE_PENALTY)
        return float(match.score or 0.0)
```

The actual implementation step in Task 3 should call this helper from `search(...)` after `score_match(...)` and should replace `detail_fields = [{"label": "来源站点", "value": site_name}] if site_name else []` with `detail_fields = []`.

- [ ] **Step 4: Run the focused Tencent tests and verify they pass**

Run: `uv run pytest tests/test_metadata_tencent_provider.py -k "penalizes_non_native_site_results or omits_source_site_field" -v`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_tencent_provider.py src/atv_player/metadata/providers/tencent.py
git commit -m "feat: prefer native tencent metadata results"
```

### Task 3: Run provider regression verification

**Files:**
- Modify: `src/atv_player/metadata/providers/iqiyi.py`
- Modify: `src/atv_player/metadata/providers/tencent.py`
- Test: `tests/test_metadata_iqiyi_provider.py`
- Test: `tests/test_metadata_tencent_provider.py`

- [ ] **Step 1: Run the full provider test files**

Run: `uv run pytest tests/test_metadata_iqiyi_provider.py tests/test_metadata_tencent_provider.py -v`

Expected: PASS with all provider tests green, including the new native-site ranking assertions and existing mapping assertions.

- [ ] **Step 2: Run the metadata hydrator regression check**

Run: `uv run pytest tests/test_metadata_hydrator.py -k "highest_scored_primary_match" -v`

Expected: PASS, proving the hydrator still trusts provider ranking and now consumes the updated native-site ordering without additional code changes.

- [ ] **Step 3: Commit the verification-safe final state**

```bash
git add src/atv_player/metadata/providers/iqiyi.py src/atv_player/metadata/providers/tencent.py tests/test_metadata_iqiyi_provider.py tests/test_metadata_tencent_provider.py
git commit -m "fix: penalize third-party metadata search results"
```
