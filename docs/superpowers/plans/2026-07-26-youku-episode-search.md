# 优酷剧集弹幕搜索修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `悬案 4集` 精确命中优酷第 4 集正片，并从优酷弹幕候选中移除预告、看点和推荐视频。

**Architecture:** 搜索接口解析负责把 `showVideoStage` / `displayName` 规范化为显式集数；详情页解析使用 `json.JSONDecoder.raw_decode()` 读取 `window.__INITIAL_DATA__`，只接受 `type=10013` 选集组件中的正片。结构化选集对所属剧集具有权威性，旧页面仅回退到受限的 `box-anthology-item` HTML 解析。

**Tech Stack:** Python 3.12、httpx、标准库 `json` / `html.parser`、pytest、现有 `DanmakuService` 与 `DanmakuSearchItem`。

---

## 文件结构

- Modify: `src/atv_player/danmaku/providers/youku.py`
  - 规范化搜索响应集数。
  - 解析详情页结构化选集。
  - 限制旧 HTML 选集回退并实现按剧集权威替换。
- Modify: `tests/test_danmaku_youku_provider.py`
  - 覆盖新版搜索响应、结构化选集、非正片过滤和旧 HTML 兼容。
- Modify: `tests/test_danmaku_service.py`
  - 覆盖 `悬案 4集` 经真实优酷 provider 进入服务层后的精确结果。

### Task 1: 规范化搜索接口的集数并过滤非正片标记

**Files:**
- Modify: `src/atv_player/danmaku/providers/youku.py:333-363`
- Test: `tests/test_danmaku_youku_provider.py:79-143`

- [ ] **Step 1: 写入新版搜索响应的失败测试**

在 `tests/test_danmaku_youku_provider.py` 增加：

```python
def test_youku_search_uses_stage_for_subtitle_and_filters_preview() -> None:
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
                            },
                            "componentMap": {
                                "1035": {
                                    "data": [
                                        {
                                            "videoId": "XNjUxODE2NjYyOA==",
                                            "title": "专线",
                                            "displayName": "4",
                                            "showVideoStage": "4",
                                            "iconCorner": {"tagText": "VIP"},
                                        },
                                        {
                                            "videoId": "preview04",
                                            "title": "专线（预告）",
                                            "displayName": "4",
                                            "showVideoStage": None,
                                            "iconCorner": {"tagText": "预告"},
                                        },
                                    ]
                                }
                            },
                        }
                    ]
                },
            )
        if url == "https://v.youku.com/v_show/id_XNjUxODE2NjYyOA==.html":
            return httpx.Response(200, text="<html></html>")
        raise AssertionError(url)

    items = YoukuDanmakuProvider(get=fake_get).search("悬案")

    assert [(item.name, item.url) for item in items] == [
        ("悬案 第4集 专线", "https://v.youku.com/v_show/id_XNjUxODE2NjYyOA==.html"),
    ]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py::test_youku_search_uses_stage_for_subtitle_and_filters_preview -v
```

Expected: FAIL；现有实现返回 `悬案 专线`，并保留预告候选。

- [ ] **Step 3: 实现最小的搜索候选规范化**

在 `YoukuDanmakuProvider` 中增加并由 `_component_episode_items()` 调用：

```python
    _NON_MAIN_EPISODE_MARKERS = ("预告", "看点", "片花")

    def _component_episode_number(self, episode: dict, title: str) -> int | None:
        for value in (
            episode.get("showVideoStage"),
            episode.get("displayName"),
            title,
        ):
            number = extract_episode_number(str(value or ""))
            if number is not None:
                return number
        return None

    def _is_non_main_episode_candidate(self, episode: dict, title: str) -> bool:
        video_type = str(episode.get("videoType") or "").strip()
        if video_type and video_type != "正片":
            return True
        marker_text = " ".join(
            (
                title,
                str(((episode.get("iconCorner") or {}).get("tagText") or "")),
            )
        )
        return any(marker in marker_text for marker in self._NON_MAIN_EPISODE_MARKERS)

    def _episode_title_with_number(self, title: str, episode_number: int) -> str:
        value = str(title or "").strip()
        if extract_episode_number(value) == episode_number:
            return value
        return f"第{episode_number}集 {value}".strip()
```

将 `_component_episode_items()` 的单集名称构造改为：

```python
            raw_title = str(episode.get("title") or "").strip()
            episode_number = self._component_episode_number(episode, raw_title)
            url = self._component_episode_url(episode)
            if (
                episode_number is None
                or not url
                or self._is_non_main_episode_candidate(episode, raw_title)
            ):
                continue
            episode_title = self._episode_title_with_number(raw_title, episode_number)
```

其余 `DanmakuSearchItem` 构造继续使用 `_episode_candidate_title(parent_title, episode_title)`。

- [ ] **Step 4: 运行新增测试和现有优酷搜索测试并确认 GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py -k "search" -v
```

Expected: PASS；无 warning 或 error。

- [ ] **Step 5: 提交 Task 1**

```bash
git add src/atv_player/danmaku/providers/youku.py tests/test_danmaku_youku_provider.py
git commit -m "fix(danmaku): parse youku episode stages"
```

### Task 2: 使用结构化详情选集并收紧旧 HTML 回退

**Files:**
- Modify: `src/atv_player/danmaku/providers/youku.py:1-15, 245-470`
- Test: `tests/test_danmaku_youku_provider.py:145-363`

- [ ] **Step 1: 写入结构化选集和噪声过滤的失败测试**

先在测试模块增加可复用的详情页 HTML：

```python
def _suspense_initial_data_html() -> str:
    payload = {
        "moduleList": [
            {
                "components": [
                    {
                        "type": 10013,
                        "title": "选集",
                        "itemList": [
                            {
                                "action_value": "XNjUxODE2NjYyNA==",
                                "title": "第1集 矢量",
                                "stage": 1,
                                "videoType": "正片",
                            },
                            {
                                "action_value": "XNjUxODE2NjYyOA==",
                                "title": "第4集 专线",
                                "stage": 4,
                                "videoType": "正片",
                            },
                            {
                                "action_value": "preview04",
                                "title": "第4集 专线（预告）",
                                "stage": 4,
                                "videoType": "预告片",
                            },
                            {
                                "action_value": "highlight04",
                                "title": "第4集 看点",
                                "stage": 4,
                                "videoType": "剧集看点",
                            },
                        ],
                    },
                    {
                        "type": 10322,
                        "title": "精彩推荐",
                        "itemList": [
                            {
                                "action_value": "recommended",
                                "title": "悬案凶手",
                                "stage": 4,
                                "videoType": "正片",
                            }
                        ],
                    },
                ]
            }
        ]
    }
    return f"<script>window.__INITIAL_DATA__ ={json.dumps(payload, ensure_ascii=False)};</script>"
```

再增加测试：

```python
def test_youku_search_uses_structured_main_episode_list() -> None:
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
                                "videoLink": "https://v.youku.com/v_show/id_XNjUxODE2NjYyNA==.html",
                            },
                            "componentMap": {
                                "1035": {
                                    "data": [
                                        {
                                            "videoId": "XNjUxODE2NjYyNA==",
                                            "title": "矢量",
                                            "displayName": "1",
                                            "showVideoStage": "1",
                                        },
                                        {
                                            "videoId": "preview04",
                                            "title": "专线（预告）",
                                            "displayName": "4",
                                            "iconCorner": {"tagText": "预告"},
                                        },
                                    ]
                                }
                            },
                        }
                    ]
                },
            )
        if url == "https://v.youku.com/v_show/id_XNjUxODE2NjYyNA==.html":
            return httpx.Response(200, text=_suspense_initial_data_html())
        raise AssertionError(url)

    items = YoukuDanmakuProvider(get=fake_get).search("悬案")

    assert [(item.name, item.url) for item in items] == [
        ("悬案 第1集 矢量", "https://v.youku.com/v_show/id_XNjUxODE2NjYyNA==.html"),
        ("悬案 第4集 专线", "https://v.youku.com/v_show/id_XNjUxODE2NjYyOA==.html"),
    ]
```

把 `test_youku_search_prefixes_parent_title_for_bare_episode_titles` 中两个合法选集 `<a>` 增加 `class="box-anthology-item"`，并增加一个不带该 class 的普通推荐链接；断言仍然只有两集。

- [ ] **Step 2: 运行结构化与旧回退测试并确认 RED**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py::test_youku_search_uses_structured_main_episode_list tests/test_danmaku_youku_provider.py::test_youku_search_prefixes_parent_title_for_bare_episode_titles -v
```

Expected: FAIL；现有代码不解析 `window.__INITIAL_DATA__`，并会把普通推荐链接加入结果。

- [ ] **Step 3: 用标准 HTML 解析器限制旧版选集链接**

增加导入和模块内解析器：

```python
from html.parser import HTMLParser


class _YoukuAnthologyLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        values = {key.casefold(): str(value or "") for key, value in attrs}
        if "box-anthology-item" not in values.get("class", "").split():
            return
        href = values.get("href", "").strip()
        label = values.get("aria-label", "").strip()
        if href and label:
            self.links.append((href, label))
```

将旧 `_extract_detail_episode_items()` 改名为 `_extract_legacy_detail_episode_items()`，用解析器的 `links` 构造候选；要求 `extract_episode_number(episode_title)` 不为空，且标题不含 `_NON_MAIN_EPISODE_MARKERS`。

- [ ] **Step 4: 解析 `window.__INITIAL_DATA__` 的 JSON**

在 provider 中增加：

```python
    def _extract_initial_data(self, html_text: str) -> dict:
        marker = re.search(r"window\.__INITIAL_DATA__\s*=\s*", html_text)
        if marker is None:
            return {}
        try:
            payload, _ = json.JSONDecoder().raw_decode(html_text[marker.end() :])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _extract_initial_data_episode_items(
        self,
        html_text: str,
        parent_title: str = "",
    ) -> list[DanmakuSearchItem]:
        payload = self._extract_initial_data(html_text)
        output: list[DanmakuSearchItem] = []
        for module in payload.get("moduleList") or []:
            if not isinstance(module, dict):
                continue
            for component in module.get("components") or []:
                if not isinstance(component, dict) or int(component.get("type") or 0) != 10013:
                    continue
                for episode in component.get("itemList") or []:
                    if not isinstance(episode, dict) or str(episode.get("videoType") or "").strip() != "正片":
                        continue
                    episode_number = extract_episode_number(str(episode.get("stage") or ""))
                    raw_title = str(episode.get("title") or "").strip()
                    url = self._component_episode_url(episode)
                    if episode_number is None or not raw_title or not url:
                        continue
                    episode_title = self._episode_title_with_number(raw_title, episode_number)
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

扩展 `_component_episode_url()`：先尝试规范化 `action_value` / `action.value`，否则把合法的裸 `videoId` 或裸 `action_value` 组装为标准优酷 URL。裸 ID 只接受 `re.fullmatch(r"[A-Za-z0-9_=+-]+", value)`。

- [ ] **Step 5: 让结构化选集按剧集权威替换搜索摘要**

给 `_expand_items_from_candidate_pages()` 增加 `authoritative_groups: set[str]`。每个组的详情请求完成后：

```python
            structured = self._extract_initial_data_episode_items(
                response.text,
                parent_title=parent_title,
            )
            if structured:
                authoritative_groups.add(group_key)
                expanded.extend(self._merge_detail_metadata(structured, items))
                continue
            expanded.extend(
                self._extract_legacy_detail_episode_items(
                    response.text,
                    parent_title=parent_title,
                )
            )
```

其中 `_merge_detail_metadata()` 按 URL 从搜索摘要补充更大的 `duration_seconds`，但保留结构化候选名称。最终只把不属于 `authoritative_groups` 的搜索候选传给 `_merge_search_items()`：

```python
        fallback_items = [
            item for item in items if self._search_item_group_key(item) not in authoritative_groups
        ]
        if not expanded:
            return fallback_items
        return self._merge_search_items(expanded, fallback_items)
```

`_search_item_group_key()` 必须复用现有规则：优先 `resolve_context["parent_title"]`，否则 `strip_episode_suffix(item.name)`，最后回退 `item.url`。

- [ ] **Step 6: 运行优酷 provider 全部测试并确认 GREEN**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py -v
```

Expected: 全部 PASS；结构化详情只返回第 1、4 集正片，旧版普通推荐链接不进入结果。

- [ ] **Step 7: 提交 Task 2**

```bash
git add src/atv_player/danmaku/providers/youku.py tests/test_danmaku_youku_provider.py
git commit -m "fix(danmaku): parse structured youku episode lists"
```

### Task 3: 锁定 `DanmakuService` 的第 4 集精确结果

**Files:**
- Modify: `tests/test_danmaku_service.py:1-15, 110-135`

- [ ] **Step 1: 写入服务层回归测试**

在 `tests/test_danmaku_service.py` 导入 `json`、`httpx` 和 `YoukuDanmakuProvider`，增加：

```python
def test_search_danmu_finds_youku_suspense_episode_four() -> None:
    detail_payload = {
        "moduleList": [
            {
                "components": [
                    {
                        "type": 10013,
                        "itemList": [
                            {
                                "action_value": "XNjUxODE2NjYyNA==",
                                "title": "第1集 矢量",
                                "stage": 1,
                                "videoType": "正片",
                            },
                            {
                                "action_value": "XNjUxODE2NjYyOA==",
                                "title": "第4集 专线",
                                "stage": 4,
                                "videoType": "正片",
                            },
                            {
                                "action_value": "preview04",
                                "title": "第4集 专线（预告）",
                                "stage": 4,
                                "videoType": "预告片",
                            },
                        ],
                    }
                ]
            }
        ]
    }

    def fake_get(url: str, **kwargs):
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
                                "videoLink": "https://v.youku.com/v_show/id_XNjUxODE2NjYyNA==.html",
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            text=f"<script>window.__INITIAL_DATA__ ={json.dumps(detail_payload, ensure_ascii=False)};</script>",
        )

    provider = YoukuDanmakuProvider(get=fake_get)
    service = DanmakuService({"youku": provider}, provider_order=["youku"])

    results = service.search_danmu("悬案 4集", provider_filter="youku")

    assert [(item.name, item.url) for item in results] == [
        ("悬案 第4集 专线", "https://v.youku.com/v_show/id_XNjUxODE2NjYyOA==.html"),
    ]
```

- [ ] **Step 2: 运行测试并确认它验证了完整调用链**

Run:

```bash
uv run pytest tests/test_danmaku_service.py::test_search_danmu_finds_youku_suspense_episode_four -v
```

Expected: PASS；该测试使用 Task 2 已实现的真实 provider，并证明服务层把查询拆成 `悬案`、保留原始 `悬案 4集`，最终只留下第 4 集正片。

- [ ] **Step 3: 运行 provider 与 service 相关测试**

Run:

```bash
uv run pytest tests/test_danmaku_youku_provider.py tests/test_danmaku_service.py -q
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交 Task 3**

```bash
git add tests/test_danmaku_service.py
git commit -m "test(danmaku): cover youku episode filtering"
```

### Task 4: 完整验证与线上只读验收

**Files:**
- Verify only: `src/atv_player/danmaku/providers/youku.py`
- Verify only: `tests/test_danmaku_youku_provider.py`
- Verify only: `tests/test_danmaku_service.py`

- [ ] **Step 1: 运行所有弹幕测试**

Run:

```bash
uv run pytest tests/test_danmaku_*.py tests/test_generic_danmaku_controller.py -q
```

Expected: 全部 PASS。

- [ ] **Step 2: 检查格式和工作区差异**

Run:

```bash
uv run ruff check src/atv_player/danmaku/providers/youku.py tests/test_danmaku_youku_provider.py tests/test_danmaku_service.py
git diff --check
git status --short
```

Expected: Ruff 与 `git diff --check` 均无输出；状态中只保留用户原有改动或本计划明确产生的提交。

- [ ] **Step 3: 对线上优酷响应做只读验收**

Run:

```bash
PYTHONPATH=src .venv/bin/python -c 'from atv_player.danmaku.providers.youku import YoukuDanmakuProvider; items=YoukuDanmakuProvider().search("悬案", original_name="悬案 4集"); print([(item.name, item.url) for item in items if "第4集" in item.name])'
```

Expected:

```text
[("悬案 第4集 专线", "https://v.youku.com/v_show/id_XNjUxODE2NjYyOA==.html")]
```

- [ ] **Step 4: 记录验证证据**

最终交付中报告 provider/service 测试数量、弹幕测试结果、Ruff 结果和线上第 4 集 URL；若线上请求因网络环境失败，明确说明自动化回归已通过但线上验收未执行。
