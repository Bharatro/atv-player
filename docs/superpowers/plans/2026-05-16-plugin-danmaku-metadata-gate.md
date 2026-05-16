# Plugin Danmaku Metadata Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate plugin-source media enhancement so `metadata_hydrator` is only attached when the plugin capability switch `spider.danmaku()` returns `True`.

**Architecture:** Keep the global media-enhancement switch and provider chain unchanged. Apply a plugin-only gate in `SpiderPluginController.build_request()` by reusing the already-computed `self._danmaku_enabled` capability flag when deciding whether to attach `metadata_hydrator` to `OpenPlayerRequest`.

**Tech Stack:** Python 3.14, dataclasses, pytest

---

## File Map

**Modify:**
- `src/atv_player/plugins/controller.py`
- `tests/test_spider_plugin_controller.py`

**Existing references to inspect while implementing:**
- `src/atv_player/plugins/compat/base/spider.py`
- `src/atv_player/controllers/player_controller.py`

### Task 1: Gate plugin `metadata_hydrator` on the danmaku capability flag

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Modify: `src/atv_player/plugins/controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing plugin-controller tests**

```python
def test_controller_attaches_metadata_hydrator_when_plugin_danmaku_is_enabled() -> None:
    marker = object()

    controller = SpiderPluginController(
        PluginLevelDanmakuSpider(),
        plugin_name="红果短剧",
        search_enabled=True,
        metadata_hydrator_factory=lambda **kwargs: marker,
    )

    request = controller.build_request("/detail/1")

    assert request.metadata_hydrator is marker


def test_controller_disables_metadata_hydrator_when_plugin_danmaku_is_disabled() -> None:
    marker = object()

    controller = SpiderPluginController(
        SimpleSpider(),
        plugin_name="红果短剧",
        search_enabled=True,
        metadata_hydrator_factory=lambda **kwargs: marker,
    )

    request = controller.build_request("/detail/1")

    assert request.metadata_hydrator is None
```

- [ ] **Step 2: Run the focused plugin-controller tests and verify they fail**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "metadata_hydrator_when_plugin_danmaku" -q`

Expected: FAIL because plugin requests currently attach `metadata_hydrator` whenever `_metadata_hydrator_factory` is present, regardless of `self._danmaku_enabled`.

- [ ] **Step 3: Implement the plugin-only metadata gate**

```python
metadata_hydrator = None
if self._metadata_hydrator_factory is not None and self._danmaku_enabled:
    metadata_hydrator = self._metadata_hydrator_factory(
        source_kind="plugin",
        source_key=self._plugin_name,
        vod=detail,
        raw_detail=raw_detail,
    )

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
    detail_action_runner=detail_action_runner,
    metadata_hydrator=metadata_hydrator,
    danmaku_controller=self if self._danmaku_enabled and self._danmaku_service is not None else None,
    playback_history_loader=history_loader,
    playback_history_saver=history_saver,
)
```

- [ ] **Step 4: Run the focused plugin-controller tests and verify they pass**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "metadata_hydrator_when_plugin_danmaku" -q`

Expected: PASS with 2 selected tests.

- [ ] **Step 5: Run the plugin playback regression tests**

Run: `uv run pytest tests/test_spider_plugin_controller.py -k "plugin_level_danmaku or metadata_hydrator_when_plugin_danmaku" -q`

Expected: PASS, confirming the metadata gate does not change existing plugin danmaku behavior.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: gate plugin metadata enhancement on danmaku"
```

## Self-Review

- Spec coverage: the plan implements the exact gate described in the spec, keeps the change scoped to plugin requests, and validates both `danmaku=True` and `danmaku=False`.
- Placeholder scan: no `TODO`/`TBD` markers remain; each step includes exact files, tests, commands, and implementation snippets.
- Type consistency: the plan consistently uses `metadata_hydrator_factory`, `metadata_hydrator`, and `self._danmaku_enabled`, matching the current controller implementation.
