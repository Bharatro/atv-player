# Danmaku Search Title Size Suffix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove backend-added trailing file-size suffixes like `(1.74 GB)` from the default danmaku search title without dropping valid variety episode text such as `20250104期`.

**Architecture:** Keep the change inside `SpiderPluginController`'s default title resolution path. Add one focused helper in `src/atv_player/plugins/controller.py` to strip only trailing parenthesized size suffixes, then reuse the existing default title resolution flow so manual danmaku search overrides and provider logic remain unchanged.

**Tech Stack:** Python, pytest, existing spider plugin controller danmaku search flow

---

### Task 1: Lock The Regression With Controller Tests

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the failing tests**

Add two controller tests near the existing danmaku search title tests.

```python
def test_controller_refresh_danmaku_sources_strips_trailing_size_suffix_from_calendar_title() -> None:
    class FakeDanmakuService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
        ):
            self.calls.append(name)
            return DanmakuSourceSearchResult(
                groups=[
                    DanmakuSourceGroup(
                        provider="mgtv",
                        provider_label="芒果",
                        options=[DanmakuSourceOption(provider="mgtv", name="候选", url="https://www.mgtv.com/b/1/2.html")],
                    )
                ],
                default_option_url="https://www.mgtv.com/b/1/2.html",
                default_provider="mgtv",
            )

    service = FakeDanmakuService()
    controller = SpiderPluginController(
        PluginLevelDanmakuSpider(),
        plugin_name="你好星期六",
        search_enabled=True,
        danmaku_service=service,
    )
    item = PlayItem(
        title="你好星期六 20250104期(1.74 GB)",
        url="https://stream.example/1.m3u8",
        media_title="你好星期六 20250104期(1.74 GB)",
        vod_id="episode-1",
    )

    controller.refresh_danmaku_sources(item)

    assert service.calls == ["你好星期六 20250104期"]
    assert item.danmaku_search_title == "你好星期六 20250104期"
    assert item.danmaku_search_episode == "你好星期六 20250104期"
    assert item.danmaku_search_query == "你好星期六 20250104期"


def test_controller_refresh_danmaku_sources_strips_trailing_size_suffix_from_default_title() -> None:
    class FakeDanmakuService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
        ):
            self.calls.append(name)
            return DanmakuSourceSearchResult(
                groups=[
                    DanmakuSourceGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        options=[DanmakuSourceOption(provider="tencent", name="候选", url="https://v.qq.com/demo")],
                    )
                ],
                default_option_url="https://v.qq.com/demo",
                default_provider="tencent",
            )

    service = FakeDanmakuService()
    controller = SpiderPluginController(
        PluginLevelDanmakuSpider(),
        plugin_name="玄界之门",
        search_enabled=True,
        danmaku_service=service,
    )
    item = PlayItem(
        title="第12集(894.9 MB)",
        url="https://stream.example/12.m3u8",
        media_title="玄界之门 特别版(894.9 MB)",
        vod_id="episode-12",
    )

    controller.refresh_danmaku_sources(item)

    assert service.calls == ["玄界之门 特别版 12集"]
    assert item.danmaku_search_title == "玄界之门 特别版"
    assert item.danmaku_search_episode == "12集"
    assert item.danmaku_search_query == "玄界之门 特别版 12集"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "strips_trailing_size_suffix" -v
```

Expected: FAIL because the current default danmaku search title still includes `(1.74 GB)` / `(894.9 MB)`.

- [ ] **Step 3: Commit the red state test file**

```bash
git add tests/test_spider_plugin_controller.py
git commit -m "test: cover danmaku search title size suffix cleanup"
```

### Task 2: Strip The Default Title Size Suffix

**Files:**
- Modify: `src/atv_player/plugins/controller.py`
- Modify: `tests/test_spider_plugin_controller.py`
- Test: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Write the minimal implementation**

Add a focused helper near `_strip_trailing_title_year_suffix()` and apply it inside `_resolve_danmaku_search_title()`.

```python
def _strip_trailing_title_size_suffix(value: str) -> str:
    title = str(value or "").strip()
    if not title:
        return ""
    stripped = re.sub(
        r"\s*[\(（\[【]\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb|tb)\s*[\)）\]】]\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    stripped = stripped.strip()
    return stripped or title


def _normalize_default_danmaku_search_title(value: str) -> str:
    return _strip_trailing_title_year_suffix(_strip_trailing_title_size_suffix(value))
```

Update the default resolution path to use the new normalization:

```python
return (
    _normalize_default_danmaku_search_title(item.media_title)
    or _normalize_default_danmaku_search_title(item.title)
)
```

- [ ] **Step 2: Run the focused tests to verify they pass**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "strips_trailing_size_suffix" -v
```

Expected: PASS for both new regression tests.

- [ ] **Step 3: Run adjacent regression coverage**

Run:

```bash
uv run pytest tests/test_spider_plugin_controller.py -k "strips_trailing_year_from_default_media_title or strips_trailing_size_suffix" -v
```

Expected: PASS, proving the existing year cleanup still works after the new size cleanup is added.

- [ ] **Step 4: Commit the implementation**

```bash
git add src/atv_player/plugins/controller.py tests/test_spider_plugin_controller.py
git commit -m "fix: strip size suffix from danmaku search title"
```
