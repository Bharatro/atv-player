# Spider Plugin Secondary Group Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Only enable plugin secondary source grouping when `detailContent().group` exists and parses into valid grouped sources.

**Architecture:** Keep `SpiderPluginController.build_request()` on the same two-stage parse flow: try explicit `group` first, then fall back to legacy `vod_play_from` / `vod_play_url` playlists. The behavior change is isolated to the fallback branch: legacy playlists remain, but `source_groups` stop being inferred from route labels.

**Tech Stack:** Python, pytest, existing `atv_player.plugins.controller.SpiderPluginController`

---

### File Structure

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Reference: `docs/superpowers/specs/2026-05-14-spider-plugin-secondary-group-gate-design.md`

`src/atv_player/plugins/controller.py` owns request construction and the current fallback that infers `PlaybackSourceGroup` from legacy `play_source` text. `tests/test_spider_plugin_controller.py` already covers both implicit route grouping and explicit `group` payload parsing, so the regression coverage belongs there instead of a new test file.

### Task 1: Lock The New Fallback Contract In Tests

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing test for legacy numbered routes staying flat**

```python
def test_spider_controller_does_not_infer_secondary_groups_from_legacy_routes() -> None:
    class GroupedRouteSpider:
        def detailContent(self, ids):
            return {
                "list": [
                    {
                        "vod_id": ids[0],
                        "vod_name": "红果短剧",
                        "vod_play_from": "解析1$$$百度1$$$百度2",
                        "vod_play_url": (
                            "第1集$http://parse/1.m3u8"
                            "$$$第1集$http://baidu1/1.m3u8"
                            "$$$第1集$http://baidu2/1.m3u8"
                        ),
                    }
                ]
            }

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id}

    controller = SpiderPluginController(GroupedRouteSpider(), plugin_name="红果短剧", search_enabled=True)
    request = controller.build_request("detail-1")

    assert request.source_groups == []
    assert len(request.playlists) == 3
    assert [playlist[0].play_source for playlist in request.playlists] == ["解析1", "百度1", "百度2"]
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "does_not_infer_secondary_groups_from_legacy_routes" -v`

Expected: FAIL because `request.source_groups` is currently populated from legacy route labels.

- [ ] **Step 3: Replace outdated expectations for invalid `group` fallback**

```python
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

    assert request.source_groups == []
    assert request.playlists[0][0].url == "http://a/1.m3u8"
    assert request.playlists[1][0].url == "http://b/1.m3u8"
```

This keeps explicit `group` coverage intact while asserting that an invalid `group` no longer re-enables secondary groups via the legacy branch.

- [ ] **Step 4: Run the focused fallback tests**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "does_not_infer_secondary_groups_from_legacy_routes or falls_back_to_legacy_routes_when_group_payload_is_invalid or uses_detail_group_payload_when_present" -v`

Expected: at least the two legacy-fallback assertions fail before production code changes; the explicit `group` test should continue to pass.

- [ ] **Step 5: Commit the red test changes**

```bash
git add tests/test_spider_plugin_controller.py
git commit -m "test: lock plugin secondary group gate"
```

### Task 2: Remove Implicit Secondary Group Inference From The Legacy Fallback

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the minimal implementation in `build_request()`**

Replace the fallback branch with:

```python
        source_groups: list[PlaybackSourceGroup] = []
        playlists: list[list[PlayItem]] = []
        if isinstance(raw_detail, Mapping):
            source_groups, playlists = self._build_grouped_sources_from_payload(detail, raw_detail.get("group"))
        if not playlists:
            playlists = self._build_playlist(detail)
```

Delete the legacy inference call:

```python
            source_groups = self._build_source_groups_from_playlists(playlists)
```

Do not change `_build_playlist()` itself. Legacy `playlists` must still preserve route count, route names, direct media URLs, and drive-link behavior.

- [ ] **Step 2: Leave the explicit grouped-source parser untouched**

Keep this behavior exactly as-is:

```python
        if isinstance(raw_detail, Mapping):
            source_groups, playlists = self._build_grouped_sources_from_payload(detail, raw_detail.get("group"))
```

That preserves the valid `group` path as the only place that can populate `request.source_groups`.

- [ ] **Step 3: Run the focused regression tests to verify green**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "does_not_infer_secondary_groups_from_legacy_routes or falls_back_to_legacy_routes_when_group_payload_is_invalid or uses_detail_group_payload_when_present" -v`

Expected: PASS for all selected tests.

- [ ] **Step 4: Run the broader spider controller suite**

Run: `uv run pytest tests/test_spider_plugin_controller.py -q`

Expected: PASS with 0 failures, confirming no other plugin-controller behaviors depended on implicit legacy `source_groups`.

- [ ] **Step 5: Commit the implementation**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: gate plugin secondary groups on detail payload"
```

### Task 3: Final Verification Against The Approved Spec

**Files:**
- Reference: `docs/superpowers/specs/2026-05-14-spider-plugin-secondary-group-gate-design.md`
- Verify: `src/atv_player/plugins/controller.py`
- Verify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Re-check the approved behavior against the diff**

Use this checklist while reviewing the final diff:

```text
[ ] Valid detail `group` still produces request.source_groups
[ ] Missing detail `group` leaves request.source_groups empty
[ ] Invalid detail `group` leaves request.source_groups empty
[ ] Legacy vod_play_from / vod_play_url fallback still produces multiple playlists
```

- [ ] **Step 2: Run the final proof command**

Run: `uv run pytest tests/test_spider_plugin_controller.py -q`

Expected: PASS with exit code 0.

- [ ] **Step 3: Inspect the final diff**

Run: `git diff -- src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py`

Expected: only the fallback `source_groups` assignment is removed and the tests are updated to assert the new gate.

- [ ] **Step 4: Create the finishing commit if verification is clean**

```bash
git status --short
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "test: verify plugin secondary group gate"
```

Only do this if the verification step required follow-up edits after Task 2. If no files changed during final verification, skip this step.
