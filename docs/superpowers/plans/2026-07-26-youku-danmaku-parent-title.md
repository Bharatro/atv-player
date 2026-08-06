# Youku Danmaku Parent Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the Youku series title in episode danmaku candidates so titles such as `第1集 矢量` become `悬案 第1集 矢量` without duplicating an existing series title.

**Architecture:** Keep the change inside `YoukuDanmakuProvider`. Carry the parent title through the existing `resolve_context`, use one helper to compose candidate names from both search-component and detail-page data, and group candidate-page expansion by parent title.

**Tech Stack:** Python 3.12+, pytest, httpx test responses

---

### Task 1: Preserve the parent title across Youku candidate extraction

**Files:**
- Modify: `tests/test_danmaku_youku_provider.py`
- Modify: `src/atv_player/danmaku/providers/youku.py:237-396`

- [ ] **Step 1: Write the failing regression test**

Add this test after `test_youku_provider_search_maps_episode_candidates_from_page_component_payload`:

```python
def test_youku_provider_search_prefixes_parent_title_when_episode_titles_omit_it() -> None:
    def fake_get(
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        follow_redirects: bool = True,
        timeout: float = 10.0,
    ):
        if "search.youku.com" in url:
            return httpx.Response(
                200,
                json={
                    "pageComponentList": [
                        {
                            "commonData": {
                                "isYouku": 1,
                                "hasYouku": 1,
                                "titleDTO": {"displayName": "悬案"},
                                "videoLink": "https://v.youku.com/v_show/id_episode01.html",
                            },
                            "componentMap": {
                                "1035": {
                                    "data": [
                                        {
                                            "videoId": "episode01",
                                            "title": "第1集 矢量",
                                        },
                                        {
                                            "videoId": "episode02",
                                            "title": "第2集 打砸抢杀",
                                        },
                                    ]
                                }
                            },
                        }
                    ]
                },
            )
        if url == "https://v.youku.com/v_show/id_episode01.html":
            return httpx.Response(
                200,
                text=(
                    '<a href="//v.youku.com/video?vid=episode01" aria-label="第1集 矢量"></a>'
                    '<a href="//v.youku.com/video?vid=episode02" aria-label="第2集 打砸抢杀"></a>'
                ),
            )
        raise AssertionError(url)

    provider = YoukuDanmakuProvider(get=fake_get)

    items = provider.search("悬案")

    assert [(item.name, item.url) for item in items] == [
        ("悬案 第1集 矢量", "https://v.youku.com/v_show/id_episode01.html"),
        ("悬案 第2集 打砸抢杀", "https://v.youku.com/v_show/id_episode02.html"),
    ]
```

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py::test_youku_provider_search_prefixes_parent_title_when_episode_titles_omit_it -q
```

Expected: FAIL because the actual names are `第1集 矢量` and `第2集 打砸抢杀` without the `悬案` prefix.

- [ ] **Step 3: Add the minimal parent-title propagation**

In `YoukuDanmakuProvider`, add these helpers near `_component_primary_title`:

```python
    def _component_parent_title(self, common: dict) -> str:
        return str((common.get("titleDTO") or {}).get("displayName") or "").strip()

    def _episode_candidate_title(self, parent_title: str, episode_title: str) -> str:
        parent = str(parent_title or "").strip()
        episode = str(episode_title or "").strip()
        if not parent:
            return episode
        if not episode:
            return parent
        compact_parent = re.sub(r"[\W_]+", "", normalize_name(parent).casefold())
        compact_episode = re.sub(r"[\W_]+", "", normalize_name(episode).casefold())
        if compact_parent and compact_parent in compact_episode:
            return episode
        return f"{parent} {episode}"
```

Update `_extract_page_component_items` to read the raw parent title, pass it to episode extraction, and retain it on a primary fallback candidate:

```python
            parent_title = self._component_parent_title(common)
            component_results = self._component_episode_items(item, parent_title=parent_title)
            title = self._component_primary_title(common)
            url = self._component_primary_url(common)
            if title and url and not component_results:
                component_results.append(
                    DanmakuSearchItem(
                        provider=self.key,
                        name=title,
                        url=url,
                        duration_seconds=self._to_duration_seconds(common.get("duration")),
                        resolve_context={"parent_title": parent_title} if parent_title else {},
                    )
                )
```

Change `_component_episode_items` to compose each name and carry the parent title:

```python
    def _component_episode_items(self, item: dict, parent_title: str = "") -> list[DanmakuSearchItem]:
        component_map = item.get("componentMap") or {}
        episodes = (component_map.get("1035") or {}).get("data") or []
        output: list[DanmakuSearchItem] = []
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            episode_title = str(episode.get("title") or "").strip()
            url = self._component_episode_url(episode)
            if not episode_title or not url:
                continue
            output.append(
                DanmakuSearchItem(
                    provider=self.key,
                    name=self._episode_candidate_title(parent_title, episode_title),
                    url=url,
                    duration_seconds=self._to_duration_seconds(episode.get("duration")),
                    resolve_context={"parent_title": parent_title} if parent_title else {},
                )
            )
        return output
```

Update `_expand_items_from_candidate_pages` so the parent title controls grouping and detail extraction:

```python
        for item in items:
            parent_title = str(item.resolve_context.get("parent_title") or "").strip()
            group_key = normalize_name(parent_title or strip_episode_suffix(item.name)) or item.url
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            if len(seen_groups) > 3:
                break
            try:
                response = self._get(
                    item.url,
                    headers={"user-agent": self._SEARCH_USER_AGENT, "referer": "https://www.youku.com/"},
                    follow_redirects=True,
                    timeout=10.0,
                )
            except Exception:
                continue
            expanded.extend(self._extract_detail_episode_items(response.text, parent_title=parent_title))
```

Change detail extraction to apply the same naming rule:

```python
    def _extract_detail_episode_items(
        self, html_text: str, parent_title: str = ""
    ) -> list[DanmakuSearchItem]:
        output: list[DanmakuSearchItem] = []
        for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]+aria-label="([^"]+)"', html_text, re.I):
            url = self._normalize_youku_url(html.unescape(match.group(1)))
            episode_title = self._clean_detail_episode_title(html.unescape(match.group(2)).strip())
            if not url or not episode_title:
                continue
            output.append(
                DanmakuSearchItem(
                    provider=self.key,
                    name=self._episode_candidate_title(parent_title, episode_title),
                    url=url,
                    resolve_context={"parent_title": parent_title} if parent_title else {},
                )
            )
        return output
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py::test_youku_provider_search_prefixes_parent_title_when_episode_titles_omit_it tests/test_danmaku_youku_provider.py::test_youku_provider_search_maps_episode_candidates_from_page_component_payload tests/test_danmaku_youku_provider.py::test_youku_provider_search_expands_full_episode_list_from_candidate_detail_page -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run the full relevant regression suite**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py tests/test_danmaku_service.py -q
```

Expected: all tests pass with no failures.

- [ ] **Step 6: Check the patch and commit**

Run:

```bash
git diff --check
git diff -- src/atv_player/danmaku/providers/youku.py tests/test_danmaku_youku_provider.py
git add src/atv_player/danmaku/providers/youku.py tests/test_danmaku_youku_provider.py
git commit -m "fix(danmaku): preserve youku parent titles"
```

Expected: no whitespace errors; the commit contains only the provider and regression test changes.

### Task 2: Verify the final repository state

**Files:**
- Verify: `src/atv_player/danmaku/providers/youku.py`
- Verify: `tests/test_danmaku_youku_provider.py`

- [ ] **Step 1: Run the final focused suite from a clean command invocation**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py tests/test_danmaku_service.py -q
```

Expected: all tests pass with exit code 0.

- [ ] **Step 2: Verify repository status and commit contents**

Run:

```bash
git status --short
git show --stat --oneline HEAD
```

Expected: the implementation commit contains only `youku.py` and `test_danmaku_youku_provider.py`; no unintended working-tree changes remain.
