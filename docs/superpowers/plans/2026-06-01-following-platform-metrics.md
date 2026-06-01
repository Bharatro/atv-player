# Following Platform Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show provider-specific official-site metrics on following detail pages for iQiyi, Tencent Video, Youku, and Bilibili, with a compact merged-row metric and full source-view fields.

**Architecture:** Keep provider extraction local to each metadata provider, using existing `MetadataRecord.detail_fields` to carry the new labels. Let `following_metadata` derive a single compact platform metric from the provider record when it builds `FollowingPlaybackPlatformEntry` objects, and keep `FollowingDetailPage` responsible only for rendering that compact metric in the merged platform row. Bilibili uses `播放` as its compact merged-row metric; iQiyi, Tencent Video, and Youku use `热度`.

**Tech Stack:** Python 3.12, PySide6, pytest, existing `atv_player.metadata` and `atv_player.ui.following_detail_page` modules.

---

### Task 1: Add provider tests for site metrics

**Files:**
- Modify: `tests/test_metadata_iqiyi_provider.py`
- Modify: `tests/test_metadata_tencent_provider.py`
- Modify: `tests/test_metadata_youku_provider.py`
- Modify: `tests/test_metadata_bilibili_provider.py`

- [ ] **Step 1: Write the failing tests**

Add assertions that each provider returns the new scalar labels when present:

```python
def test_iqiyi_metadata_provider_detail_exposes_site_metrics() -> None:
    provider = IqiyiMetadataProvider(
        get=lambda url, **kwargs: JsonResponse(
            {
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
                                "siteScore": {"key": "站内评分", "value": "9.4"},
                                "heat": {"key": "热度", "value": "24567"},
                                "commentCount": {"key": "评论", "value": "1.2万"},
                            }
                        }
                    ]
                }
            }
        )
    )
    match = provider.search(MetadataQuery(title="疯狂动物城2", year="2025", category_name="电影"))[0]
    record = provider.get_detail(match)
    assert {"label": "站内评分", "value": "9.4"} in record.detail_fields
    assert {"label": "热度", "value": "24567"} in record.detail_fields
    assert {"label": "评论", "value": "1.2万"} in record.detail_fields
```

Mirror the same idea for Tencent and Youku. For Bilibili, add a test that `detail_fields` still includes the existing activity metrics and that the merged-row source should later use `播放` instead of `热度`:

```python
def test_bilibili_metadata_provider_get_detail_keeps_activity_fields() -> None:
    provider = BilibiliMetadataProvider(get=lambda url, **kwargs: JsonResponse({"code": 0, "data": {}}))
    match = MetadataMatch(
        provider="bilibili",
        provider_id="https://www.bilibili.com/bangumi/play/ss45969",
        title="牧神记",
        year="2024",
        raw={
            "title": "牧神记",
            "desc": "主角秦牧在大墟成长。",
            "styles": "小说改/玄幻/热血/战斗",
            "genres": ["小说改", "玄幻", "热血", "战斗"],
            "areas": "中国大陆",
            "cover": "https://i0.hdslb.com/bfs/bangumi/image/demo.png",
            "media_score": {"score": 9.6, "user_count": 19280},
            "stat": {"views": 19280, "follow_text": "19280追番"},
            "staff": "总导演：沈乐平",
            "cv": "少年秦牧：张若瑜",
            "season_type_name": "国创",
            "index_show": "更新至第82话",
            "subtitle": "国创 · 更新至第82话",
        },
    )
    record = provider.get_detail(match)
    assert {"label": "播放", "value": "19280"} in record.detail_fields
    assert {"label": "追番", "value": "19280追番"} in record.detail_fields
```

- [ ] **Step 2: Run the provider tests and confirm they fail**

Run:

```bash
uv run pytest \
  tests/test_metadata_iqiyi_provider.py \
  tests/test_metadata_tencent_provider.py \
  tests/test_metadata_youku_provider.py \
  tests/test_metadata_bilibili_provider.py -q
```

Expected: FAIL because the new labels are not yet extracted.

- [ ] **Step 3: Implement minimal provider extraction**

Update each provider `get_detail()` to append the new scalar fields only when present. Keep the field names stable:

```python
for key in ("siteScore", "heat", "commentCount"):
    item = payload.get(key)
    if not isinstance(item, dict):
        continue
    label = str(item.get("key") or "").strip()
    value = str(item.get("value") or "").strip()
    if label and value:
        detail_fields.append({"label": label, "value": value})
```

For Tencent and Youku, adapt the actual payload keys to whatever the provider already sees from its raw response. For Bilibili, keep the existing stat mapping and do not invent a heat field.

- [ ] **Step 4: Run the provider tests and confirm they pass**

Run the same `pytest` command again.

- [ ] **Step 5: Commit**

```bash
git add tests/test_metadata_iqiyi_provider.py tests/test_metadata_tencent_provider.py tests/test_metadata_youku_provider.py tests/test_metadata_bilibili_provider.py src/atv_player/metadata/providers/iqiyi.py src/atv_player/metadata/providers/tencent.py src/atv_player/metadata/providers/youku.py src/atv_player/metadata/providers/bilibili.py
git commit -m "feat: extract official site metrics"
```

### Task 2: Carry a compact merged-row metric through following metadata

**Files:**
- Modify: `src/atv_player/following_models.py`
- Modify: `src/atv_player/following_metadata.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Modify: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing UI test**

Add an assertion that the merged playback row contains one compact metric per platform:

```python
def test_following_detail_page_shows_compact_platform_metrics(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    page.load_record(1)
    platform_html = page.playback_platform_widgets[0].text()
    assert "爱奇艺" in platform_html
    assert "腾讯" in platform_html
    assert "热度" in platform_html or "播放" in platform_html
```

Refine this assertion to check exact formatting after the model carries the compact metric.

- [ ] **Step 2: Run the UI test and confirm it fails**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "playback_platforms or compact_platform_metrics" -v
```

Expected: FAIL because platform entries have no compact metric field yet.

- [ ] **Step 3: Extend the platform entry model and render path**

Add a defaulted field to `FollowingPlaybackPlatformEntry` for the compact merged-row metric, then have `following_metadata` populate it when it creates or merges platform entries.

```python
@dataclass(slots=True)
class FollowingPlaybackPlatformEntry:
    provider: str
    label: str
    url: str = ""
    latest_episode: int = 0
    update_time_text: str = ""
    status_text: str = ""
    metric_label: str = ""
    metric_value: str = ""
```

In `following_metadata`, map provider records to the compact metric:

```python
def _compact_platform_metric(provider: str, record: MetadataRecord) -> tuple[str, str]:
    field_map = {str(item.get("label") or ""): str(item.get("value") or "") for item in record.detail_fields if isinstance(item, dict)}
    if provider == "bilibili":
        return "播放", field_map.get("播放", "")
    return "热度", field_map.get("热度", "")
```

Use that helper in `_playback_platform_entries_from_record()` and `_merge_playback_platform_updates()` so the merged row retains the metric when a provider gets updated.

Update `FollowingDetailPage._playback_platform_entry_html()` to append the metric only when `metric_value` is present:

```python
if entry.metric_value:
    parts.append(html.escape(f"{entry.metric_label} {entry.metric_value}"))
```

- [ ] **Step 4: Run the UI test and confirm it passes**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "playback_platforms or compact_platform_metrics" -v
```

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/following_models.py src/atv_player/following_metadata.py src/atv_player/ui/following_detail_page.py tests/test_following_detail_page_ui.py
git commit -m "feat: show compact following platform metrics"
```

### Task 3: Add a source-view regression for full scalar fields

**Files:**
- Modify: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing regression test**

Add a source-view assertion that switching to Tencent or iQiyi shows `站内评分`, `热度`, and `评论` in the raw source text when present:

```python
def test_following_detail_page_shows_full_metrics_in_source_view(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)
    page.load_record(1)
    page.metadata_source_buttons[1].click()
    assert "站内评分:" in page.overview_label.text()
    assert "热度:" in page.overview_label.text()
    assert "评论:" in page.overview_label.text()
```

- [ ] **Step 2: Run the regression test and confirm it passes**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_detail_page_ui.py -k "full_metrics_in_source_view" -v
```

Expected: PASS once provider fields are wired through.

- [ ] **Step 3: Commit**

```bash
git add tests/test_following_detail_page_ui.py
git commit -m "test: cover full following source metrics"
```

