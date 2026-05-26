# Following Detail Merged Metadata Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the following detail merged metadata view so it reads as curated media information, renames the merged source button to `媒体信息`, and removes duplicated update information from the merged text block.

**Architecture:** Keep the merged metadata bundle intact and apply presentation filtering only in the following detail page formatting layer. Rename only the merged source button label in UI code, while preserving the internal `merged` source key and provider raw views.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Add failing UI regression coverage

**Files:**
- Modify: `tests/test_following_detail_page_ui.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write the failing test**

```python
def test_following_detail_page_shows_rating_strip_source_switcher_and_playback_platforms(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.rating_strip.text() == "TMDB 8.1  ·  豆瓣 7.9  ·  Bangumi 8.4"
    assert [button.text() for button in page.metadata_source_buttons] == ["媒体信息", "TMDB", "豆瓣", "Bangumi", "爱奇艺"]
    assert "最近更新:" not in page.overview_label.text()
    assert "更新时间:" not in page.overview_label.text()
    assert "更新状态:" not in page.overview_label.text()
    assert "播放:" not in page.overview_label.text()
    assert "追番:" not in page.overview_label.text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_following_detail_page_ui.py::test_following_detail_page_shows_rating_strip_source_switcher_and_playback_platforms -q`
Expected: FAIL because the current merged button text is `合并` and the merged overview still includes provider operational fields.

- [ ] **Step 3: Add provider-view guard coverage**

```python
def test_following_detail_page_switches_between_merged_and_provider_raw_views(qtbot) -> None:
    controller = FakeController()
    page = FollowingDetailPage(controller)
    qtbot.addWidget(page)

    page.load_record(1)
    page.metadata_source_buttons[2].click()

    assert "豆瓣简介" in page.overview_label.text()
    assert "TMDB简介" not in page.overview_label.text()

    page.metadata_source_buttons[4].click()

    assert "播放:" in page.overview_label.text()
    assert "追番:" in page.overview_label.text()
```

- [ ] **Step 4: Run provider-view test to verify current behavior**

Run: `uv run pytest tests/test_following_detail_page_ui.py::test_following_detail_page_switches_between_merged_and_provider_raw_views -q`
Expected: PASS before implementation, confirming provider raw views should remain unchanged.

### Task 2: Implement merged-view filtering and label rename

**Files:**
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Add merged-view whitelist formatter**

```python
_MERGED_METADATA_LABEL_WHITELIST = {
    "类型",
    "年代",
    "地区",
    "语言",
    "导演",
    "演员",
    "别名",
    "豆瓣ID",
    "IMDb ID",
    "TMDB ID",
}


def _format_merged_source_snapshot_text(snapshot: FollowingMetadataSourceSnapshot) -> str:
    parts: list[str] = []
    for field in snapshot.metadata_fields:
        label = str(field.get("label", "")).strip()
        value = str(field.get("value", "")).strip()
        if label not in _MERGED_METADATA_LABEL_WHITELIST or not value:
            continue
        parts.append(f"{label}: {value}")
    overview = str(snapshot.overview or "").strip()
    if overview:
        parts.append("")
        parts.append(f"简介:\n{overview}")
    return "\n".join(parts) if parts else "暂无简介"
```

- [ ] **Step 2: Route merged view through the whitelist formatter**

```python
def _render_metadata_bundle(self, snapshot: FollowingDetailSnapshot) -> None:
    bundle = snapshot.metadata_bundle
    if bundle is None:
        ...
        return
    ...
    if current_key == "merged":
        self.overview_label.setText(_format_merged_source_snapshot_text(bundle.merged_snapshot))
    else:
        self.overview_label.setText(_format_source_snapshot_text(current))
```

- [ ] **Step 3: Rename merged source button label**

```python
def _render_source_buttons(
    self,
    source_keys: list[str],
    *,
    source_snapshots: dict[str, FollowingMetadataSourceSnapshot],
) -> None:
    ...
    for source_key in source_keys:
        if source_key == "merged":
            label = "媒体信息"
        else:
            snapshot = source_snapshots.get(source_key)
            label = snapshot.provider_label if snapshot is not None else source_key
```

- [ ] **Step 4: Run targeted UI tests**

Run: `uv run pytest tests/test_following_detail_page_ui.py::test_following_detail_page_shows_rating_strip_source_switcher_and_playback_platforms tests/test_following_detail_page_ui.py::test_following_detail_page_switches_between_merged_and_provider_raw_views -q`
Expected: PASS

### Task 3: Run focused regression suite

**Files:**
- Modify: `src/atv_player/ui/following_detail_page.py`
- Modify: `tests/test_following_detail_page_ui.py`
- Test: `tests/test_following_detail_page_ui.py`
- Test: `tests/test_following_metadata.py`
- Test: `tests/test_metadata_merge.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_following_detail_page_ui.py tests/test_following_metadata.py tests/test_metadata_merge.py -q`
Expected: PASS with zero failures

- [ ] **Step 2: Review diff**

Run: `git diff -- src/atv_player/ui/following_detail_page.py tests/test_following_detail_page_ui.py`
Expected: Only merged-view formatting, merged button label, and UI regression coverage changes are present.
