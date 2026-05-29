# AI Enrichment Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared OpenAI-compatible AI enrichment layer and connect it as best-effort assistance for metadata scraping, danmaku search, episode title rewriting, and following detail summaries.

**Architecture:** Add typed AI enrichment models plus `AIEnrichmentService` under `src/atv_player/ai/`, then inject one optional service from `AppCoordinator` into existing orchestration boundaries. AI outputs are hints only: provider search, danmaku filtering, episode title source priority, and following progress math remain deterministic and continue to work when AI is disabled or fails.

**Tech Stack:** Python dataclasses, existing `OpenAICompatibleClient.chat_completion(...)`, pytest, ruff, pyright.

---

## File Structure

- Create `src/atv_player/ai/enrichment.py`: AI enrichment input/output dataclasses, JSON helpers, prompt construction, and `AIEnrichmentService`.
- Modify `src/atv_player/ai/__init__.py`: export enrichment models and service.
- Modify `src/atv_player/app.py`: construct a shared AI enrichment service when config is complete, inject it into metadata scrape, danmaku, and following controller paths.
- Modify `src/atv_player/metadata/scrape.py`: accept optional AI enrichment service, refine metadata search queries, and apply low-priority AI episode title rewrites.
- Modify `src/atv_player/danmaku/service.py`: accept optional AI enrichment service and try refined query variants before falling back to original search.
- Modify `src/atv_player/following_models.py`: add display-only `FollowingAISummary`.
- Modify `src/atv_player/controllers/following_controller.py`: ask AI for a privacy-safe following summary after deterministic detail loading.
- Modify `src/atv_player/ui/following_detail_page.py`: render a compact optional AI summary panel and hide it when empty.
- Add `tests/test_ai_enrichment.py`: unit coverage for parsing, fallback, and privacy.
- Modify `tests/test_metadata_scrape_service.py`: refined metadata query and AI episode-title rewrite coverage.
- Modify `tests/test_danmaku_service.py`: refined query fallback coverage.
- Modify `tests/test_episode_titles.py`: AI source priority coverage.
- Modify `tests/test_following_controller.py`: following AI summary display-only coverage.
- Modify `tests/test_following_detail_page_ui.py`: optional AI summary panel rendering.
- Modify `tests/test_app.py`: app wiring coverage.

---

### Task 1: Add AI enrichment dataclasses and parser service

**Files:**
- Create: `src/atv_player/ai/enrichment.py`
- Modify: `src/atv_player/ai/__init__.py`
- Test: `tests/test_ai_enrichment.py`

- [ ] **Step 1: Write failing parser and fallback tests**

Add `tests/test_ai_enrichment.py`:

```python
from __future__ import annotations

import json

from atv_player.ai.enrichment import (
    AIEnrichmentService,
    DanmakuQueryRefinementInput,
    EpisodeTitleRewriteInput,
    EpisodeTitleRewriteItem,
    FollowingDetailSummaryInput,
    MetadataQueryRefinementInput,
)
from atv_player.ai.models import AICompletionResult


class RecordingClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[dict[str, str]] = []

    def chat_completion(self, *, messages, temperature=0.0, response_format=None):
        self.messages = list(messages)
        self.temperature = temperature
        self.response_format = response_format
        return AICompletionResult(content=self.content)


class FailingClient:
    def chat_completion(self, **kwargs):
        raise RuntimeError("network down")


def test_refine_metadata_query_parses_json_response() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "title": "黑镜",
                "year": "2011",
                "season_number": 3,
                "media_kind": "live_action",
                "alternative_titles": ["Black Mirror"],
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.refine_metadata_query(
        MetadataQueryRefinementInput(
            title="Black.Mirror.S03.2011",
            year="",
            category_name="英剧",
            season_number=0,
            source_name="browse",
        )
    )

    assert result.title == "黑镜"
    assert result.year == "2011"
    assert result.season_number == 3
    assert result.media_kind == "live_action"
    assert result.alternative_titles == ["Black Mirror"]
    assert client.response_format == {"type": "json_object"}


def test_refine_danmaku_query_parses_ordered_queries() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "queries": ["黑镜 第3集", "Black Mirror S01E03"],
                "episode_number": 3,
                "reason": "clean episode marker",
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.refine_danmaku_query(
        DanmakuQueryRefinementInput(
            title="Black.Mirror.S01E03",
            media_title="黑镜",
            episode_title="",
            episode_number=0,
            year="2011",
        )
    )

    assert result.queries == ["黑镜 第3集", "Black Mirror S01E03"]
    assert result.episode_number == 3
    assert result.reason == "clean episode marker"


def test_rewrite_episode_titles_parses_index_map() -> None:
    client = RecordingClient(
        json.dumps({"titles_by_index": {"0": "第一集 国歌", "1": "第二集 一千五百万点"}})
    )
    service = AIEnrichmentService(client)

    result = service.rewrite_episode_titles(
        EpisodeTitleRewriteInput(
            media_title="黑镜",
            items=[
                EpisodeTitleRewriteItem(index=0, original_title="S01E01.mkv", display_title=""),
                EpisodeTitleRewriteItem(index=1, original_title="S01E02.mkv", display_title=""),
            ],
            metadata_titles={},
        )
    )

    assert result.titles_by_index == {0: "第一集 国歌", 1: "第二集 一千五百万点"}


def test_summarize_following_detail_parses_compact_summary() -> None:
    client = RecordingClient(
        json.dumps(
            {
                "summary": "本季进入主线冲突，适合继续追。",
                "highlights": ["节奏更快", "悬疑线明显", "下集将更新"],
                "next_hint": "下一集明晚更新",
            }
        )
    )
    service = AIEnrichmentService(client)

    result = service.summarize_following_detail(
        FollowingDetailSummaryInput(
            title="黑镜",
            media_kind="英剧",
            current_episode=2,
            latest_episode=3,
            total_episodes=6,
            overview="科技寓言单元剧",
            next_episode_title="",
            next_episode_air_date="2026-05-30",
            metadata_fields=[{"label": "年份", "value": "2011"}],
        )
    )

    assert result.summary == "本季进入主线冲突，适合继续追。"
    assert result.highlights == ["节奏更快", "悬疑线明显", "下集将更新"]
    assert result.next_hint == "下一集明晚更新"


def test_enrichment_returns_empty_outputs_when_client_fails() -> None:
    service = AIEnrichmentService(FailingClient())

    assert service.refine_metadata_query(MetadataQueryRefinementInput(title="x")).title == ""
    assert service.refine_danmaku_query(DanmakuQueryRefinementInput(title="x")).queries == []
    assert service.rewrite_episode_titles(EpisodeTitleRewriteInput(media_title="x")).titles_by_index == {}
    assert service.summarize_following_detail(FollowingDetailSummaryInput(title="x")).summary == ""


def test_prompts_do_not_include_local_paths_or_api_keys() -> None:
    client = RecordingClient(json.dumps({"title": "黑镜"}))
    service = AIEnrichmentService(client)

    service.refine_metadata_query(
        MetadataQueryRefinementInput(
            title="/home/user/Videos/Black.Mirror.S01E01.mkv",
            year="2011",
            category_name="剧集",
            source_name="secret-api-key",
        )
    )

    prompt_text = "\n".join(message["content"] for message in client.messages)
    assert "/home/user" not in prompt_text
    assert "secret-api-key" not in prompt_text
    assert "Black.Mirror.S01E01.mkv" in prompt_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_ai_enrichment.py -q
```

Expected: FAIL with `ModuleNotFoundError` or import errors for `atv_player.ai.enrichment`.

- [ ] **Step 3: Implement enrichment models and service**

Create `src/atv_player/ai/enrichment.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_VALID_MEDIA_KINDS = {"anime", "movie", "live_action", ""}


@dataclass(slots=True)
class MetadataQueryRefinementInput:
    title: str
    year: str = ""
    category_name: str = ""
    season_number: int = 0
    source_name: str = ""


@dataclass(slots=True)
class MetadataQueryRefinement:
    title: str = ""
    year: str = ""
    season_number: int = 0
    media_kind: str = ""
    alternative_titles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DanmakuQueryRefinementInput:
    title: str
    media_title: str = ""
    episode_title: str = ""
    episode_number: int = 0
    year: str = ""


@dataclass(slots=True)
class DanmakuQueryRefinement:
    queries: list[str] = field(default_factory=list)
    episode_number: int = 0
    reason: str = ""


@dataclass(slots=True)
class EpisodeTitleRewriteItem:
    index: int
    original_title: str
    display_title: str = ""


@dataclass(slots=True)
class EpisodeTitleRewriteInput:
    media_title: str
    items: list[EpisodeTitleRewriteItem] = field(default_factory=list)
    metadata_titles: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class EpisodeTitleRewrite:
    titles_by_index: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class FollowingDetailSummaryInput:
    title: str
    media_kind: str = ""
    current_episode: int = 0
    latest_episode: int = 0
    total_episodes: int = 0
    overview: str = ""
    next_episode_title: str = ""
    next_episode_air_date: str = ""
    metadata_fields: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class FollowingDetailSummary:
    summary: str = ""
    highlights: list[str] = field(default_factory=list)
    next_hint: str = ""


def _json_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {}


def _string(value: object, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _safe_title(value: object) -> str:
    text = _string(value, limit=180)
    return re.split(r"[\\/]", text)[-1]


def _string_list(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item, limit=80)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, int | float | str):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class AIEnrichmentService:
    def __init__(self, client) -> None:
        self._client = client

    def _complete(self, system: str, payload: dict[str, object]) -> dict[str, Any]:
        result = self._client.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return _json_payload(result.content)

    def refine_metadata_query(self, data: MetadataQueryRefinementInput) -> MetadataQueryRefinement:
        try:
            payload = self._complete(
                "你是影视元数据搜索 query 清洗器。只输出 JSON，不要解释。",
                {
                    "title": _safe_title(data.title),
                    "year": _string(data.year, limit=16),
                    "category_name": _string(data.category_name, limit=40),
                    "season_number": _int_value(data.season_number),
                },
            )
        except Exception:
            logger.debug("AI metadata query refinement failed", exc_info=True)
            return MetadataQueryRefinement()
        media_kind = _string(payload.get("media_kind"), limit=24)
        return MetadataQueryRefinement(
            title=_string(payload.get("title"), limit=120),
            year=_string(payload.get("year"), limit=16),
            season_number=_int_value(payload.get("season_number")),
            media_kind=media_kind if media_kind in _VALID_MEDIA_KINDS else "",
            alternative_titles=_string_list(payload.get("alternative_titles"), limit=4),
        )

    def refine_danmaku_query(self, data: DanmakuQueryRefinementInput) -> DanmakuQueryRefinement:
        try:
            payload = self._complete(
                "你是弹幕搜索 query 清洗器。只输出 JSON，不要解释。",
                {
                    "title": _safe_title(data.title),
                    "media_title": _string(data.media_title, limit=120),
                    "episode_title": _string(data.episode_title, limit=120),
                    "episode_number": _int_value(data.episode_number),
                    "year": _string(data.year, limit=16),
                },
            )
        except Exception:
            logger.debug("AI danmaku query refinement failed", exc_info=True)
            return DanmakuQueryRefinement()
        return DanmakuQueryRefinement(
            queries=_string_list(payload.get("queries"), limit=4),
            episode_number=_int_value(payload.get("episode_number")),
            reason=_string(payload.get("reason"), limit=120),
        )

    def rewrite_episode_titles(self, data: EpisodeTitleRewriteInput) -> EpisodeTitleRewrite:
        items = [
            {
                "index": item.index,
                "original_title": _safe_title(item.original_title),
                "display_title": _string(item.display_title, limit=120),
            }
            for item in data.items[:80]
        ]
        try:
            payload = self._complete(
                "你是影视分集标题改写器。只输出 JSON，不要解释。",
                {
                    "media_title": _string(data.media_title, limit=120),
                    "items": items,
                    "metadata_titles": {
                        str(index): _string(title, limit=120)
                        for index, title in data.metadata_titles.items()
                    },
                },
            )
        except Exception:
            logger.debug("AI episode title rewrite failed", exc_info=True)
            return EpisodeTitleRewrite()
        raw_map = payload.get("titles_by_index")
        titles: dict[int, str] = {}
        if isinstance(raw_map, dict):
            for key, value in raw_map.items():
                index = _int_value(key)
                title = _string(value, limit=120)
                if title:
                    titles[index] = title
        return EpisodeTitleRewrite(titles_by_index=titles)

    def summarize_following_detail(self, data: FollowingDetailSummaryInput) -> FollowingDetailSummary:
        try:
            payload = self._complete(
                "你是追更详情摘要助手。只输出 JSON，不要解释。",
                {
                    "title": _string(data.title, limit=120),
                    "media_kind": _string(data.media_kind, limit=40),
                    "current_episode": _int_value(data.current_episode),
                    "latest_episode": _int_value(data.latest_episode),
                    "total_episodes": _int_value(data.total_episodes),
                    "overview": _string(data.overview, limit=600),
                    "next_episode_title": _string(data.next_episode_title, limit=120),
                    "next_episode_air_date": _string(data.next_episode_air_date, limit=32),
                    "metadata_fields": [
                        {
                            "label": _string(field.get("label"), limit=40),
                            "value": _string(field.get("value"), limit=160),
                        }
                        for field in data.metadata_fields[:12]
                    ],
                },
            )
        except Exception:
            logger.debug("AI following detail summary failed", exc_info=True)
            return FollowingDetailSummary()
        return FollowingDetailSummary(
            summary=_string(payload.get("summary"), limit=280),
            highlights=_string_list(payload.get("highlights"), limit=3),
            next_hint=_string(payload.get("next_hint"), limit=120),
        )
```

Update `src/atv_player/ai/__init__.py` to export the new types:

```python
from atv_player.ai.enrichment import (
    AIEnrichmentService,
    DanmakuQueryRefinement,
    DanmakuQueryRefinementInput,
    EpisodeTitleRewrite,
    EpisodeTitleRewriteInput,
    EpisodeTitleRewriteItem,
    FollowingDetailSummary,
    FollowingDetailSummaryInput,
    MetadataQueryRefinement,
    MetadataQueryRefinementInput,
)
```

Add these names to `__all__`.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_ai_enrichment.py -q
```

Expected: PASS.

- [ ] **Step 5: Lint and type-check the new module**

Run:

```bash
uv run ruff check src/atv_player/ai/enrichment.py tests/test_ai_enrichment.py
npx --yes pyright src/atv_player/ai
```

Expected: both commands pass.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ai/enrichment.py src/atv_player/ai/__init__.py tests/test_ai_enrichment.py
git commit -m "feat: add ai enrichment service"
```

---

### Task 2: Wire metadata query refinement

**Files:**
- Modify: `src/atv_player/metadata/scrape.py`
- Test: `tests/test_metadata_scrape_service.py`

- [ ] **Step 1: Write failing metadata refinement tests**

Append to `tests/test_metadata_scrape_service.py`:

```python
from dataclasses import dataclass

from atv_player.ai.enrichment import MetadataQueryRefinement


class AIRefinesMetadataQuery:
    def __init__(self) -> None:
        self.inputs = []

    def refine_metadata_query(self, data):
        self.inputs.append(data)
        return MetadataQueryRefinement(title="黑镜", year="2011")


class SearchRecordingProvider:
    name = "tmdb"

    def __init__(self) -> None:
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        if query.title == "黑镜":
            return [MetadataMatch(provider="tmdb", provider_id="tv:1", title="黑镜", year="2011")]
        return []
```

Add the test:

```python
def test_metadata_scrape_service_uses_ai_refined_query_before_original(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = SearchRecordingProvider()
    ai = AIRefinesMetadataQuery()
    service = MetadataScrapeService(cache=cache, providers=[provider], ai_enrichment_service=ai)

    groups = service.search(MetadataQuery(title="Black.Mirror.S01E01", year=""))

    assert ai.inputs[0].title == "Black.Mirror.S01E01"
    assert provider.queries[0].title == "黑镜"
    assert groups[0].items[0].title == "黑镜"
```

Add fallback test:

```python
class AIEmptyMetadataQuery:
    def refine_metadata_query(self, data):
        return MetadataQueryRefinement()


def test_metadata_scrape_service_falls_back_when_ai_refinement_empty(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    provider = SearchRecordingProvider()
    service = MetadataScrapeService(cache=cache, providers=[provider], ai_enrichment_service=AIEmptyMetadataQuery())

    service.search(MetadataQuery(title="Black.Mirror.S01E01", year=""))

    assert provider.queries[0].title == "Black.Mirror.S01E01"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_metadata_scrape_service.py -k "ai_refined_query or ai_refinement_empty" -q
```

Expected: FAIL because `MetadataScrapeService.__init__` does not accept `ai_enrichment_service`.

- [ ] **Step 3: Implement optional query refinement**

In `src/atv_player/metadata/scrape.py`:

1. Import:

```python
from atv_player.ai.enrichment import MetadataQueryRefinementInput
```

2. Change constructor:

```python
class MetadataScrapeService:
    def __init__(
        self,
        cache: MetadataCache,
        providers: list[object],
        ai_enrichment_service=None,
    ) -> None:
        self._cache = cache
        self._providers = list(providers)
        self._providers_by_name = {provider.name: provider for provider in self._providers}
        self._ai_enrichment_service = ai_enrichment_service
```

3. Add helper:

```python
    def _refine_query_with_ai(self, query: MetadataQuery) -> MetadataQuery:
        if self._ai_enrichment_service is None:
            return query
        refine = getattr(self._ai_enrichment_service, "refine_metadata_query", None)
        if not callable(refine):
            return query
        try:
            result = refine(
                MetadataQueryRefinementInput(
                    title=query.title,
                    year=query.year,
                    category_name=query.category_name,
                    season_number=extract_season_number(query.title) or 0,
                    source_name=query.type_name,
                )
            )
        except Exception:
            logger.debug("AI metadata query refinement failed in scrape service", exc_info=True)
            return query
        refined_title = str(getattr(result, "title", "") or "").strip()
        if not refined_title:
            return query
        refined_year = str(getattr(result, "year", "") or "").strip() or query.year
        return replace(query, title=refined_title, year=refined_year)
```

4. In `search(...)`, after normalization:

```python
        query = replace(query, title=normalized_title, year=normalized_year)
        query = self._refine_query_with_ai(query)
```

Do not alter `search_following(...)` in this task.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_metadata_scrape_service.py -k "ai_refined_query or ai_refinement_empty" -q
```

Expected: PASS.

- [ ] **Step 5: Run focused metadata scrape regressions**

Run:

```bash
uv run pytest tests/test_metadata_scrape_service.py -k "groups_parallel_results or cache_only_reuses_cached_results or filters_explicit_category_mismatches or ai_refined_query or ai_refinement_empty" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/metadata/scrape.py tests/test_metadata_scrape_service.py
git commit -m "feat: refine metadata scrape queries with ai"
```

---

### Task 3: Wire danmaku query refinement

**Files:**
- Modify: `src/atv_player/danmaku/service.py`
- Test: `tests/test_danmaku_service.py`

- [ ] **Step 1: Write failing danmaku tests**

Append to `tests/test_danmaku_service.py`:

```python
from atv_player.ai.enrichment import DanmakuQueryRefinement


class AIRefinesDanmakuQuery:
    def __init__(self) -> None:
        self.inputs = []

    def refine_danmaku_query(self, data):
        self.inputs.append(data)
        return DanmakuQueryRefinement(queries=["黑镜 第3集"])


class RecordingDanmakuProvider:
    def __init__(self) -> None:
        self.queries = []

    def search(self, name: str, *, original_name: str | None = None):
        self.queries.append((name, original_name))
        if name == "黑镜 第3集":
            return [
                DanmakuSearchItem(
                    provider="tencent",
                    name="黑镜 第3集",
                    url="https://v.qq.com/x/3",
                    ratio=1.0,
                    simi=1.0,
                    duration_seconds=3600,
                )
            ]
        return []

    def supports(self, page_url: str) -> bool:
        return False
```

Add tests:

```python
def test_danmaku_service_uses_ai_refined_query_before_original() -> None:
    provider = RecordingDanmakuProvider()
    ai = AIRefinesDanmakuQuery()
    service = DanmakuService(
        {"tencent": provider},
        provider_order=["tencent"],
        ai_enrichment_service=ai,
    )

    results = service.search_danmu("Black.Mirror.S01E03")

    assert ai.inputs[0].title == "Black.Mirror.S01E03"
    assert provider.queries[0][0] == "黑镜 第3集"
    assert results[0].name == "黑镜 第3集"


class AIEmptyDanmakuQuery:
    def refine_danmaku_query(self, data):
        return DanmakuQueryRefinement()


def test_danmaku_service_falls_back_when_ai_query_empty() -> None:
    provider = RecordingDanmakuProvider()
    service = DanmakuService(
        {"tencent": provider},
        provider_order=["tencent"],
        ai_enrichment_service=AIEmptyDanmakuQuery(),
    )

    service.search_danmu("Black.Mirror.S01E03")

    assert provider.queries[0][0] == "black.mirror.s01e03"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_danmaku_service.py -k "ai_refined_query or ai_query_empty" -q
```

Expected: FAIL because `DanmakuService.__init__` does not accept `ai_enrichment_service`.

- [ ] **Step 3: Implement optional danmaku refinement**

In `src/atv_player/danmaku/service.py`:

1. Import:

```python
from atv_player.ai.enrichment import DanmakuQueryRefinementInput
```

2. Add constructor parameter:

```python
    def __init__(
        self,
        providers: dict[str, DanmakuProvider],
        provider_order: list[str],
        disabled_provider_ids_loader: Callable[[], list[str]] | None = None,
        ai_enrichment_service=None,
    ) -> None:
        ...
        self._ai_enrichment_service = ai_enrichment_service
```

3. Add helper:

```python
    def _ai_danmaku_queries(self, normalized: str, requested_episode: int | None) -> list[str]:
        if self._ai_enrichment_service is None:
            return []
        refine = getattr(self._ai_enrichment_service, "refine_danmaku_query", None)
        if not callable(refine):
            return []
        try:
            result = refine(
                DanmakuQueryRefinementInput(
                    title=normalized,
                    episode_number=requested_episode or 0,
                )
            )
        except Exception:
            logger.debug("AI danmaku query refinement failed in service", exc_info=True)
            return []
        queries: list[str] = []
        for query in getattr(result, "queries", []) or []:
            text = normalize_name(query)
            if text and text not in queries:
                queries.append(text)
        return queries[:3]
```

4. In `search_danmu(...)`, after `provider_keys` are computed and before collecting results:

```python
        query_variants = [
            query
            for query in self._ai_danmaku_queries(normalized, requested_episode)
            if query != primary_query
        ]
        query_variants.append(primary_query)
        results: list[DanmakuSearchItem] = []
        for query_variant in query_variants:
            results = self._collect_search_results(provider_keys, query_variant, normalized)
            results = _filter_too_short_duration_candidates(results)
            if results:
                primary_query = query_variant
                break
```

Remove or replace the existing single call:

```python
        results = self._collect_search_results(provider_keys, primary_query, normalized)
        results = _filter_too_short_duration_candidates(results)
```

5. Update `create_default_danmaku_service(...)` signature and return:

```python
def create_default_danmaku_service(..., ai_enrichment_service=None) -> DanmakuService:
    ...
    return DanmakuService(..., ai_enrichment_service=ai_enrichment_service)
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_danmaku_service.py -k "ai_refined_query or ai_query_empty" -q
```

Expected: PASS.

- [ ] **Step 5: Run focused danmaku regressions**

Run:

```bash
uv run pytest tests/test_danmaku_service.py -k "search_danmu or danmaku_source or create_default_danmaku_service or ai_refined_query or ai_query_empty" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/danmaku/service.py tests/test_danmaku_service.py
git commit -m "feat: refine danmaku search queries with ai"
```

---

### Task 4: Add AI episode title rewriting as a low-priority source

**Files:**
- Modify: `src/atv_player/metadata/scrape.py`
- Test: `tests/test_metadata_scrape_service.py`
- Test: `tests/test_episode_titles.py`

- [ ] **Step 1: Write failing episode-title rewrite tests**

Append to `tests/test_episode_titles.py`:

```python
def test_ai_episode_title_source_has_lower_priority_than_tmdb() -> None:
    playlist = [
        PlayItem(title="S01E01", original_title="S01E01"),
    ]
    apply_episode_title_map(
        playlist,
        {1: "官方标题"},
        source="tmdb",
        source_priority=["tmdb", "ai"],
    )
    apply_episode_title_map(
        playlist,
        {1: "AI 标题"},
        source="ai",
        source_priority=["tmdb", "ai"],
    )

    assert playlist[0].episode_display_title == "官方标题"
    assert playlist[0].episode_title_source == "tmdb"
```

Append to `tests/test_metadata_scrape_service.py`:

```python
class AIEpisodeTitleRewrite:
    def __init__(self) -> None:
        self.inputs = []

    def rewrite_episode_titles(self, data):
        self.inputs.append(data)
        from atv_player.ai.enrichment import EpisodeTitleRewrite

        return EpisodeTitleRewrite(titles_by_index={0: "AI 第一集", 1: "AI 第二集"})


def test_metadata_scrape_service_applies_ai_episode_titles_when_provider_titles_missing(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    service = MetadataScrapeService(
        cache=cache,
        providers=[],
        ai_enrichment_service=AIEpisodeTitleRewrite(),
    )
    playlist = [
        PlayItem(title="S01E01.mkv", original_title=""),
        PlayItem(title="S01E02.mkv", original_title=""),
    ]

    updated = service.build_episode_title_playlist(
        VodItem(vod_id="1", vod_name="黑镜"),
        playlist,
    )

    assert updated is playlist
    assert playlist[0].original_title == "S01E01.mkv"
    assert playlist[0].episode_display_title == "AI 第一集"
    assert playlist[0].episode_title_source == "ai"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_episode_titles.py::test_ai_episode_title_source_has_lower_priority_than_tmdb tests/test_metadata_scrape_service.py::test_metadata_scrape_service_applies_ai_episode_titles_when_provider_titles_missing -q
```

Expected: first test may pass if helper already supports priority; second test FAILS because AI titles are not applied.

- [ ] **Step 3: Implement AI title rewrite fallback**

In `src/atv_player/metadata/scrape.py`:

1. Extend import:

```python
from atv_player.ai.enrichment import (
    EpisodeTitleRewriteInput,
    EpisodeTitleRewriteItem,
    MetadataQueryRefinementInput,
)
```

2. Import title helper:

```python
from atv_player.episode_titles import apply_episode_title_index_map, extract_season_number, seed_original_titles
```

3. Add helper to `MetadataScrapeService`:

```python
    def _apply_ai_episode_titles(self, vod: VodItem, playlist: list[PlayItem]) -> list[PlayItem] | None:
        if self._ai_enrichment_service is None or not playlist:
            return None
        rewrite = getattr(self._ai_enrichment_service, "rewrite_episode_titles", None)
        if not callable(rewrite):
            return None
        seed_original_titles(playlist)
        try:
            result = rewrite(
                EpisodeTitleRewriteInput(
                    media_title=str(vod.vod_name or "").strip(),
                    items=[
                        EpisodeTitleRewriteItem(
                            index=index,
                            original_title=item.original_title or item.title,
                            display_title=item.episode_display_title,
                        )
                        for index, item in enumerate(playlist)
                    ],
                    metadata_titles={
                        index: item.episode_display_title
                        for index, item in enumerate(playlist)
                        if item.episode_display_title
                    },
                )
            )
        except Exception:
            logger.debug("AI episode title rewrite failed in scrape service", exc_info=True)
            return None
        titles_by_index = dict(getattr(result, "titles_by_index", {}) or {})
        if not titles_by_index:
            return None
        return apply_episode_title_index_map(
            playlist,
            titles_by_index,
            source="ai",
            source_priority=[*METADATA_EPISODE_TITLE_SOURCE_PRIORITY, "ai"],
        )
```

4. Import `METADATA_EPISODE_TITLE_SOURCE_PRIORITY` from `atv_player.metadata.episode_title_resolver`.

5. In `build_episode_title_playlist(...)`, before `return None`, add:

```python
        return self._apply_ai_episode_titles(vod, playlist)
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_episode_titles.py::test_ai_episode_title_source_has_lower_priority_than_tmdb tests/test_metadata_scrape_service.py::test_metadata_scrape_service_applies_ai_episode_titles_when_provider_titles_missing -q
```

Expected: PASS.

- [ ] **Step 5: Run focused episode title regressions**

Run:

```bash
uv run pytest tests/test_episode_titles.py tests/test_metadata_scrape_service.py -k "episode_title or ai_episode" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/metadata/scrape.py tests/test_metadata_scrape_service.py tests/test_episode_titles.py
git commit -m "feat: rewrite episode display titles with ai"
```

---

### Task 5: Add display-only following AI summary

**Files:**
- Modify: `src/atv_player/following_models.py`
- Modify: `src/atv_player/controllers/following_controller.py`
- Modify: `src/atv_player/ui/following_detail_page.py`
- Test: `tests/test_following_controller.py`
- Test: `tests/test_following_detail_page_ui.py`

- [ ] **Step 1: Write failing following controller test**

Append to `tests/test_following_controller.py`:

```python
from atv_player.ai.enrichment import FollowingDetailSummary


class AISummarizesFollowingDetail:
    def __init__(self) -> None:
        self.inputs = []

    def summarize_following_detail(self, data):
        self.inputs.append(data)
        return FollowingDetailSummary(
            summary="AI 摘要",
            highlights=["看点一", "看点二"],
            next_hint="明晚更新",
        )


def test_following_controller_adds_display_only_ai_summary(tmp_path: Path) -> None:
    repo = FollowingRepository(tmp_path / "following.db")
    record_id = repo.upsert(
        FollowingRecord(
            id=0,
            title="黑镜",
            current_episode=1,
            latest_episode=2,
            total_episodes=6,
        )
    )
    repo.save_detail_snapshot(
        record_id,
        FollowingDetailSnapshot(
            following_id=record_id,
            overview="科技寓言",
            next_episode=FollowingEpisode(episode_number=3, title="第三集", air_date="2026-05-30"),
        ),
    )
    ai = AISummarizesFollowingDetail()
    controller = FollowingController(
        repo,
        metadata_search_service=FakeSearchService(),
        ai_enrichment_service=ai,
        now=lambda: 100,
    )

    view = controller.load_detail(record_id, refresh_if_empty=False)

    assert ai.inputs[0].title == "黑镜"
    assert view.snapshot.ai_summary is not None
    assert view.snapshot.ai_summary.summary == "AI 摘要"
    assert view.record.latest_episode == 2
```

- [ ] **Step 2: Write failing following UI test**

Append to `tests/test_following_detail_page_ui.py`:

```python
def test_following_detail_page_renders_ai_summary_panel(qtbot) -> None:
    view = FollowingDetailView(
        record=FollowingRecord(id=1, title="黑镜", latest_episode=2, total_episodes=6),
        snapshot=FollowingDetailSnapshot(
            following_id=1,
            ai_summary=FollowingAISummary(
                summary="AI 摘要",
                highlights=["看点一", "看点二"],
                next_hint="明晚更新",
            ),
        ),
    )
    page = FollowingDetailPage(lambda following_id: view)
    qtbot.addWidget(page)

    page.load_record(1)

    assert page.ai_summary_panel.isVisible()
    assert "AI 摘要" in page.ai_summary_label.text()
    assert "看点一" in page.ai_summary_label.text()
    assert "明晚更新" in page.ai_summary_label.text()
```

Update imports in the test file as needed:

```python
from atv_player.following_models import FollowingAISummary
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_following_controller.py::test_following_controller_adds_display_only_ai_summary tests/test_following_detail_page_ui.py::test_following_detail_page_renders_ai_summary_panel -q
```

Expected: FAIL because `FollowingAISummary`, `ai_summary`, and page widgets do not exist.

- [ ] **Step 4: Add following summary model**

In `src/atv_player/following_models.py`, before `FollowingDetailSnapshot`:

```python
@dataclass(slots=True)
class FollowingAISummary:
    summary: str = ""
    highlights: list[str] = field(default_factory=list)
    next_hint: str = ""
```

Add to `FollowingDetailSnapshot`:

```python
    ai_summary: FollowingAISummary | None = None
```

- [ ] **Step 5: Wire controller summary generation**

In `src/atv_player/controllers/following_controller.py`:

1. Import:

```python
from dataclasses import replace
from atv_player.ai.enrichment import FollowingDetailSummaryInput
from atv_player.following_models import FollowingAISummary
```

2. Add constructor parameter:

```python
        ai_enrichment_service=None,
```

and store:

```python
        self._ai_enrichment_service = ai_enrichment_service
```

3. Add helper:

```python
    def _with_ai_summary(
        self,
        record: FollowingRecord,
        snapshot: FollowingDetailSnapshot,
    ) -> FollowingDetailSnapshot:
        if self._ai_enrichment_service is None:
            return snapshot
        summarize = getattr(self._ai_enrichment_service, "summarize_following_detail", None)
        if not callable(summarize):
            return snapshot
        next_episode = snapshot.next_episode
        try:
            result = summarize(
                FollowingDetailSummaryInput(
                    title=record.title,
                    media_kind=record.media_kind,
                    current_episode=record.current_episode,
                    latest_episode=record.latest_episode,
                    total_episodes=record.total_episodes,
                    overview=snapshot.overview,
                    next_episode_title="" if next_episode is None else next_episode.title,
                    next_episode_air_date="" if next_episode is None else next_episode.air_date,
                    metadata_fields=[
                        {"label": str(item.get("label", "")), "value": str(item.get("value", ""))}
                        for item in snapshot.metadata_fields[:12]
                    ],
                )
            )
        except Exception:
            return snapshot
        summary = str(getattr(result, "summary", "") or "").strip()
        highlights = [
            str(item or "").strip()
            for item in getattr(result, "highlights", []) or []
            if str(item or "").strip()
        ][:3]
        next_hint = str(getattr(result, "next_hint", "") or "").strip()
        if not summary and not highlights and not next_hint:
            return snapshot
        return replace(
            snapshot,
            ai_summary=FollowingAISummary(
                summary=summary,
                highlights=highlights,
                next_hint=next_hint,
            ),
        )
```

4. In `load_detail(...)`, before returning:

```python
        snapshot = self._with_ai_summary(record, snapshot)
        return FollowingDetailView(record=record, snapshot=snapshot)
```

- [ ] **Step 6: Render compact AI panel**

In `src/atv_player/ui/following_detail_page.py`:

1. Add widgets in `__init__` near existing labels:

```python
        self.ai_summary_panel = QFrame(self)
        self.ai_summary_panel.setObjectName("followingDetailAISummaryPanel")
        self.ai_summary_label = QLabel("", self.ai_summary_panel)
        self.ai_summary_label.setWordWrap(True)
        self.ai_summary_label.setTextInteractionFlags(selectable_flags)
```

If `selectable_flags` is local to `_build_layout`, create the label in `__init__` without flags and set flags in `_build_layout`.

2. In `_build_layout(...)`, after `metadata_layout.addWidget(self.overview_label)`:

```python
        ai_summary_layout = QVBoxLayout(self.ai_summary_panel)
        ai_summary_layout.setContentsMargins(12, 12, 12, 12)
        ai_summary_layout.setSpacing(6)
        ai_summary_layout.addWidget(self.ai_summary_label)
        metadata_layout.addWidget(self.ai_summary_panel)
```

3. Add helper:

```python
    def _render_ai_summary(self, snapshot: FollowingDetailSnapshot) -> None:
        summary = getattr(snapshot, "ai_summary", None)
        if summary is None:
            self.ai_summary_label.setText("")
            self.ai_summary_panel.setVisible(False)
            return
        lines = []
        if summary.summary:
            lines.append(summary.summary)
        lines.extend(f"• {item}" for item in summary.highlights if item)
        if summary.next_hint:
            lines.append(summary.next_hint)
        text = "\n".join(lines).strip()
        self.ai_summary_label.setText(text)
        self.ai_summary_panel.setVisible(bool(text))
```

4. Call it from `_render(...)` after `_render_metadata_bundle(snapshot)`:

```python
        self._render_ai_summary(snapshot)
```

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/test_following_controller.py::test_following_controller_adds_display_only_ai_summary tests/test_following_detail_page_ui.py::test_following_detail_page_renders_ai_summary_panel -q
```

Expected: PASS.

- [ ] **Step 8: Run focused following regressions**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_following_controller.py tests/test_following_detail_page_ui.py -k "ai_summary or load_detail or renders" -q
```

Expected: PASS or only known unrelated pre-existing failures. Investigate any failure touching changed behavior.

- [ ] **Step 9: Commit**

```bash
git add src/atv_player/following_models.py src/atv_player/controllers/following_controller.py src/atv_player/ui/following_detail_page.py tests/test_following_controller.py tests/test_following_detail_page_ui.py
git commit -m "feat: show ai summaries in following detail"
```

---

### Task 6: Wire shared AI enrichment service in AppCoordinator

**Files:**
- Modify: `src/atv_player/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing app wiring tests**

Append to `tests/test_app.py` near existing AI smart search tests:

```python
def test_app_coordinator_builds_ai_enrichment_service_when_configured(tmp_path, monkeypatch) -> None:
    repo = SettingsRepository(tmp_path / "settings.db")
    config = repo.load_config()
    config.ai_enabled = True
    config.ai_base_url = "https://api.example.com"
    config.ai_api_key = "key"
    config.ai_chat_model = "model"
    repo.save_config(config)
    coordinator = AppCoordinator(repo)

    service = coordinator._build_ai_enrichment_service(config)

    assert service is not None


def test_app_coordinator_skips_ai_enrichment_service_when_incomplete(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "settings.db")
    config = repo.load_config()
    config.ai_enabled = True
    config.ai_base_url = ""
    config.ai_api_key = "key"
    config.ai_chat_model = "model"
    repo.save_config(config)
    coordinator = AppCoordinator(repo)

    assert coordinator._build_ai_enrichment_service(config) is None
```

Add a factory injection test:

```python
def test_app_coordinator_injects_ai_enrichment_into_metadata_scrape_factory(monkeypatch, tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "settings.db")
    config = repo.load_config()
    config.metadata_enhancement_enabled = True
    config.ai_enabled = True
    config.ai_base_url = "https://api.example.com"
    config.ai_api_key = "key"
    config.ai_chat_model = "model"
    repo.save_config(config)
    coordinator = AppCoordinator(repo)
    ai_service = object()
    monkeypatch.setattr(coordinator, "_build_ai_enrichment_service", lambda config: ai_service)
    monkeypatch.setattr(coordinator, "_build_metadata_providers", lambda **kwargs: [])

    factory = coordinator._build_metadata_scrape_service_factory(object())
    service = factory(source_kind="browse", vod=VodItem(vod_id="1", vod_name="x"))

    assert service._ai_enrichment_service is ai_service
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_app.py -k "ai_enrichment_service" -q
```

Expected: FAIL because `_build_ai_enrichment_service` does not exist.

- [ ] **Step 3: Implement app construction and injection**

In `src/atv_player/app.py`:

1. Update import:

```python
from atv_player.ai import (
    AIEnrichmentService,
    AIProviderConfig,
    OpenAICompatibleClient,
    SmartSearchIntentParser,
)
```

2. Add method near `_build_smart_search_controller(...)`:

```python
    def _build_ai_enrichment_service(self, config: AppConfig):
        if not config.ai_enabled:
            return None
        provider_config = AIProviderConfig(
            base_url=config.ai_base_url,
            api_key=config.ai_api_key,
            chat_model=config.ai_chat_model,
            timeout_seconds=config.ai_request_timeout_seconds,
        )
        if not provider_config.is_complete:
            return None
        return AIEnrichmentService(OpenAICompatibleClient(provider_config))
```

3. In `__init__`, create danmaku service without AI as today. Add method:

```python
    def _refresh_danmaku_ai_enrichment(self, config: AppConfig) -> object | None:
        ai_enrichment_service = self._build_ai_enrichment_service(config)
        if self._danmaku_service is not None:
            setattr(self._danmaku_service, "_ai_enrichment_service", ai_enrichment_service)
        return ai_enrichment_service
```

4. In `_show_main(...)`, after `config = self.repo.load_config()`:

```python
        ai_enrichment_service = self._refresh_danmaku_ai_enrichment(config)
```

5. Change `_build_metadata_scrape_service_factory(...)` to build and pass service:

```python
            ai_enrichment_service = self._build_ai_enrichment_service(config)
            return MetadataScrapeService(
                cache=cache,
                providers=providers,
                ai_enrichment_service=ai_enrichment_service,
            )
```

6. Change `_build_following_metadata_search_service(...)` to pass service:

```python
        ai_enrichment_service = self._build_ai_enrichment_service(config)
        return MetadataScrapeService(..., ai_enrichment_service=ai_enrichment_service)
```

7. When constructing `FollowingController`, pass the shared service from `_show_main(...)`:

```python
                ai_enrichment_service=ai_enrichment_service,
```

8. Update `create_default_danmaku_service(...)` call in `__init__` only if the constructor now accepts it and tests require it. Otherwise rely on `_refresh_danmaku_ai_enrichment(...)`.

- [ ] **Step 4: Run app tests**

Run:

```bash
uv run pytest tests/test_app.py -k "ai_enrichment_service or smart_search_controller_when_ai_enabled" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/app.py tests/test_app.py
git commit -m "feat: wire ai enrichment service"
```

---

### Task 7: Focused integration verification and lint

**Files:**
- No source changes expected unless verification finds a defect.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest \
  tests/test_ai_enrichment.py \
  tests/test_metadata_scrape_service.py \
  tests/test_danmaku_service.py \
  tests/test_episode_titles.py \
  tests/test_following_controller.py \
  tests/test_following_detail_page_ui.py \
  tests/test_app.py \
  -k "ai_enrichment or ai_refined_query or ai_refinement_empty or ai_query_empty or ai_episode or ai_summary or smart_search_controller_when_ai_enabled" \
  -q
```

Expected: PASS. If unrelated pre-existing failures appear, rerun the exact failing tests on `master` to confirm baseline before changing source.

- [ ] **Step 2: Run ruff for touched files**

Run:

```bash
uv run ruff check \
  src/atv_player/ai \
  src/atv_player/metadata/scrape.py \
  src/atv_player/danmaku/service.py \
  src/atv_player/following_models.py \
  src/atv_player/controllers/following_controller.py \
  src/atv_player/ui/following_detail_page.py \
  tests/test_ai_enrichment.py \
  tests/test_metadata_scrape_service.py \
  tests/test_danmaku_service.py \
  tests/test_episode_titles.py \
  tests/test_following_controller.py \
  tests/test_following_detail_page_ui.py \
  tests/test_app.py
```

Expected: PASS or only legacy violations outside touched lines. Fix touched-line violations.

- [ ] **Step 3: Run pyright for new AI/search-adjacent modules**

Run:

```bash
npx --yes pyright src/atv_player/ai src/atv_player/search
```

Expected: PASS.

- [ ] **Step 4: Commit verification fixes if needed**

If Step 1-3 required fixes:

```bash
git add \
  src/atv_player/ai \
  src/atv_player/metadata/scrape.py \
  src/atv_player/danmaku/service.py \
  src/atv_player/following_models.py \
  src/atv_player/controllers/following_controller.py \
  src/atv_player/ui/following_detail_page.py \
  tests/test_ai_enrichment.py \
  tests/test_metadata_scrape_service.py \
  tests/test_danmaku_service.py \
  tests/test_episode_titles.py \
  tests/test_following_controller.py \
  tests/test_following_detail_page_ui.py \
  tests/test_app.py
git commit -m "fix: stabilize ai enrichment integration"
```

If no fixes were needed, do not create an empty commit.

---

### Task 8: Final review before branch completion

**Files:**
- No source changes expected unless review finds a defect.

- [ ] **Step 1: Review branch diff**

Run:

```bash
git diff --stat master...HEAD
git diff -- src/atv_player/ai/enrichment.py src/atv_player/metadata/scrape.py src/atv_player/danmaku/service.py src/atv_player/controllers/following_controller.py src/atv_player/ui/following_detail_page.py
```

Expected: changes match the spec: optional AI hints only, no persistent writes of AI output except display-only snapshot field in memory.

- [ ] **Step 2: Verify no sensitive prompt fields**

Run:

```bash
rg -n "api_key|local|history|database_path|original_path|/home|C:\\\\|watch" src/atv_player/ai src/atv_player/metadata/scrape.py src/atv_player/danmaku/service.py src/atv_player/controllers/following_controller.py
```

Expected: no prompt payload sends API keys, local paths, full history, or database paths. Mentions in config construction outside prompt payloads are acceptable.

- [ ] **Step 3: Check final worktree status**

Run:

```bash
git status --short
```

Expected: clean worktree.

- [ ] **Step 4: Use finishing workflow**

Invoke `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Present the standard four options for merge/PR/keep/discard.
