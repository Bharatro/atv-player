# Danmaku Provider Expansion and Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five native danmaku providers and an explainable matching pipeline that uses title identity, aliases, year, season, episode, media kind, duration, source URL, and validated history.

**Architecture:** Keep providers responsible for native search/detail/comment parsing and move cross-provider filtering and ranking into atv_player.danmaku.matching. Build a structured context once per playback item, carry candidate metadata through service/cache/UI, and allow only high-confidence candidates to become automatic defaults. Existing providers remain compatible through signature capability detection and legacy metadata fallbacks.

**Tech Stack:** Python 3.12, dataclasses, httpx, BeautifulSoup/lxml, PyCryptodome, OpenCC Python reimplementation, PySide6, pytest/pytest-qt, uv, Ruff, Pyright.

---

## File map

New focused modules:

- src/atv_player/danmaku/matching.py: normalization, hard conflicts, scoring, confidence, and explanations.
- src/atv_player/danmaku/context.py: build DanmakuMatchContext from PlayItem and compute cache fingerprints.
- src/atv_player/danmaku/providers/_segments.py: bounded segment collection shared by LeTV and Xigua.
- src/atv_player/danmaku/providers/dandanplay.py: DandanPlay adapter.
- src/atv_player/danmaku/providers/animeko.py: Bangumi/Animeko search, node health, and comments.
- src/atv_player/danmaku/providers/leshi.py: LeTV HTML and segmented comments.
- src/atv_player/danmaku/providers/xigua.py: Xigua mobile HTML and segmented comments.
- src/atv_player/danmaku/providers/_hanjutv_crypto.py: HanjuTV signing and response decoding.
- src/atv_player/danmaku/providers/hanjutv.py: HanjuTV dual-route adapter.

Existing modules retain narrow roles:

- src/atv_player/danmaku/models.py: immutable context, metadata, result, and source-option fields.
- src/atv_player/danmaku/service.py: provider orchestration and source grouping/default selection.
- src/atv_player/danmaku/cache.py: context-aware search/XML cache serialization.
- src/atv_player/danmaku/preferences.py: stable-series history.
- src/atv_player/danmaku/generic.py and src/atv_player/plugins/controller.py: build/pass context.
- src/atv_player/models.py: optional PlayItem matching hints.
- src/atv_player/source_preferences.py and src/atv_player/ui/player_window.py: provider settings and confidence labels.

## Task 1: Preserve and commit the current danmaku regression baseline

**Files:**
- Modify: src/atv_player/danmaku/providers/tencent.py
- Modify: src/atv_player/danmaku/service.py
- Modify: src/atv_player/danmaku/subtitle.py
- Modify: src/atv_player/danmaku/utils.py
- Test: tests/test_danmaku_service.py
- Test: tests/test_danmaku_subtitle.py
- Test: tests/test_danmaku_tencent_provider.py
- Test: tests/test_danmaku_utils.py

- [ ] **Step 1: Inspect the existing user-owned diff before staging**

Run:

~~~bash
git diff -- src/atv_player/danmaku/providers/tencent.py src/atv_player/danmaku/service.py src/atv_player/danmaku/subtitle.py src/atv_player/danmaku/utils.py tests/test_danmaku_service.py tests/test_danmaku_subtitle.py tests/test_danmaku_tencent_provider.py tests/test_danmaku_utils.py
~~~

Expected: only the reviewed same-name Tencent expansion, marker-led episode matching, and illegal XML control-character fixes. Stop for user review if unrelated changes appear.

- [ ] **Step 2: Verify the baseline tests**

Run:

~~~bash
uv run pytest tests/test_danmaku_service.py tests/test_danmaku_subtitle.py tests/test_danmaku_tencent_provider.py tests/test_danmaku_utils.py -q
~~~

Expected: PASS.

- [ ] **Step 3: Stage exactly the eight baseline files**

Run:

~~~bash
git add src/atv_player/danmaku/providers/tencent.py src/atv_player/danmaku/service.py src/atv_player/danmaku/subtitle.py src/atv_player/danmaku/utils.py tests/test_danmaku_service.py tests/test_danmaku_subtitle.py tests/test_danmaku_tencent_provider.py tests/test_danmaku_utils.py
git diff --cached --check
git diff --cached --name-only
~~~

Expected: exactly those eight paths.

- [ ] **Step 4: Commit the verified baseline**

Run:

~~~bash
git commit -m "fix: harden danmaku episode matching and xml parsing"
~~~

Expected: one focused commit. If already committed when execution begins, verify the tests and skip the duplicate commit.

## Task 2: Add structured models and deterministic title normalization

**Files:**
- Modify: pyproject.toml
- Modify: uv.lock
- Modify: src/atv_player/danmaku/models.py
- Create: src/atv_player/danmaku/matching.py
- Create: tests/test_danmaku_matching.py

- [ ] **Step 1: Write failing model and normalization tests**

Create tests/test_danmaku_matching.py:

~~~python
from atv_player.danmaku.matching import compact_title, title_variants
from atv_player.danmaku.models import (
    DanmakuCandidateMetadata,
    DanmakuMatchContext,
    DanmakuSearchItem,
)


def test_title_variants_unifies_nfkc_noise_and_simplified_traditional() -> None:
    variants = title_variants("《進擊的巨人》 第２季 1080P")
    assert "進擊的巨人第2季" in variants
    assert "进击的巨人第2季" in variants
    assert all("1080p" not in value for value in variants)


def test_compact_title_preserves_identity_numbers() -> None:
    assert compact_title("某剧 (2024) S02 Part 2") == "某剧2024s02part2"


def test_search_item_carries_stable_candidate_metadata() -> None:
    metadata = DanmakuCandidateMetadata(
        series_id="series-1",
        episode_id="episode-13",
        series_title="百花杀",
        aliases=("Kill All Flowers",),
        year=2026,
        season_number=1,
        episode_number=13,
        media_kind="tv",
    )
    item = DanmakuSearchItem(
        provider="tencent",
        name="第十三集 剧情副标题",
        url="https://v.qq.com/episode-13",
        candidate_metadata=metadata,
    )
    context = DanmakuMatchContext(title="百花杀", episode_number=13)
    assert item.candidate_metadata.episode_id == "episode-13"
    assert context.aliases == ()
~~~

- [ ] **Step 2: Run the test and verify the new API is absent**

Run: uv run pytest tests/test_danmaku_matching.py -q

Expected: FAIL on missing module/dataclasses.

- [ ] **Step 3: Add OpenCC and lock it**

Add this dependency to pyproject.toml:

~~~toml
"opencc-python-reimplemented>=0.1.7",
~~~

Run: uv sync

Expected: uv.lock changes and sync succeeds.

- [ ] **Step 4: Add immutable matching dataclasses**

Add before DanmakuSearchItem in models.py:

~~~python
@dataclass(frozen=True, slots=True)
class DanmakuMatchContext:
    title: str
    aliases: tuple[str, ...] = ()
    year: int = 0
    season_number: int = 0
    episode_number: int = 0
    media_kind: str = ""
    duration_seconds: int = 0
    reg_src: str = ""
    manual_query: bool = False


@dataclass(frozen=True, slots=True)
class DanmakuCandidateMetadata:
    series_id: str = ""
    episode_id: str = ""
    series_title: str = ""
    aliases: tuple[str, ...] = ()
    year: int = 0
    season_number: int = 0
    episode_number: int = 0
    media_kind: str = ""


@dataclass(frozen=True, slots=True)
class DanmakuMatchResult:
    score: int
    confidence: str
    reasons: tuple[str, ...] = ()
    rejection_reason: str = ""
~~~

Extend DanmakuSearchItem and DanmakuSourceOption with:

~~~python
candidate_metadata: DanmakuCandidateMetadata = field(default_factory=DanmakuCandidateMetadata)
match_score: int = 0
match_confidence: str = ""
match_reasons: tuple[str, ...] = ()
~~~

- [ ] **Step 5: Implement normalization**

Create matching.py:

~~~python
from __future__ import annotations

import re
import unicodedata

from opencc import OpenCC

_S2T = OpenCC("s2t")
_T2S = OpenCC("t2s")
_NOISE_RE = re.compile(
    r"(?:2160p|1080p|720p|4k|uhd|hdr|蓝光|超清|高清|国语版|粤语版|普通话版)",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^0-9a-zA-Z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+")


def compact_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return _PUNCT_RE.sub("", _NOISE_RE.sub("", normalized))


def title_variants(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    output: list[str] = []
    for variant in (normalized, _T2S.convert(normalized), _S2T.convert(normalized)):
        compact = compact_title(variant)
        if compact and compact not in output:
            output.append(compact)
    return tuple(output)
~~~

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_matching.py -q
uv run ruff check src/atv_player/danmaku/models.py src/atv_player/danmaku/matching.py tests/test_danmaku_matching.py
git add pyproject.toml uv.lock src/atv_player/danmaku/models.py src/atv_player/danmaku/matching.py tests/test_danmaku_matching.py
git commit -m "feat: add structured danmaku matching models"
~~~

Expected: tests/lint PASS and one focused commit.

## Task 3: Implement hard conflicts, scoring, and confidence

**Files:**
- Modify: src/atv_player/danmaku/matching.py
- Modify: src/atv_player/danmaku/utils.py
- Modify: tests/test_danmaku_matching.py
- Modify: tests/test_danmaku_utils.py

- [ ] **Step 1: Write a failing confidence table**

Append a candidate helper and parameterized cases for:

~~~python
@pytest.mark.parametrize(
    ("context", "item", "confidence", "reason"),
    [
        (
            DanmakuMatchContext(title="百花杀", season_number=1, episode_number=13, duration_seconds=2700),
            candidate("百花杀", season=1, episode=13, media_kind="tv", duration=2680),
            "high",
            "标题完全一致",
        ),
        (
            DanmakuMatchContext(title="倚天屠龙记", year=2019, episode_number=1),
            candidate("倚天屠龙记", year=2003, episode=1),
            "rejected",
            "年份冲突",
        ),
        (
            DanmakuMatchContext(title="间谍过家家", season_number=2, episode_number=3),
            candidate("间谍过家家", season=1, episode=3),
            "rejected",
            "季号冲突",
        ),
        (
            DanmakuMatchContext(title="八千里路云和月", episode_number=16),
            candidate("隆行天下之重走八千里路云和月", episode=16),
            "manual",
            "标题相似",
        ),
        (
            DanmakuMatchContext(title="剑来", episode_number=13),
            DanmakuSearchItem(provider="test", name="第十三集 剧情", url="test://13"),
            "manual",
            "父作品未知",
        ),
        (
            DanmakuMatchContext(title="沙丘", media_kind="movie", duration_seconds=9300),
            candidate("沙丘 预告片", media_kind="movie", duration=120),
            "rejected",
            "时长冲突",
        ),
    ],
)
def test_match_candidate_confidence_table(context, item, confidence, reason) -> None:
    result = match_candidate(context, item)
    assert result.confidence == confidence
    assert reason in (*result.reasons, result.rejection_reason)
~~~

Add a separate test proving “第十三集 剧情” becomes high only when candidate metadata has series_title="百花杀" and episode_number=13.

Add table rows for exact simplified/traditional aliases, `Part 2` conflict, four-character short-title containment, movie-versus-trailer duration, variety issue/date mismatch, unknown duration, and the 10%/20% duration score boundaries. Add a test that search-query generation returns at most three unique values in this order: cleaned main title, first reliable alias, season-stripped fallback.

- [ ] **Step 2: Verify scoring is absent**

Run: uv run pytest tests/test_danmaku_matching.py -q

Expected: FAIL on missing match_candidate.

- [ ] **Step 3: Expose the episode-marker helper**

Rename _starts_with_episode_marker to starts_with_episode_marker in utils.py, update internal calls, and keep:

~~~python
_starts_with_episode_marker = starts_with_episode_marker
~~~

Add assertions that marker-led text returns true and a show-prefixed title returns false.

- [ ] **Step 4: Implement scoring in this order**

In matching.py:

~~~python
DANMAKU_MATCH_RULE_VERSION = "v1"
~~~

1. Extract candidate episode from metadata, then candidate name.
2. Extract season and Part from structured fields, then explicit text markers.
3. Reject explicit episode, season, year, Part, or normalized media-kind conflicts.
4. Reject long targets when candidate is below 55% duration or gap exceeds max(900 seconds, 50%).
5. Score title exact=50, alias exact=48, strong bounded similarity=30.
6. Score episode=20, season=12, year=10, kind=8, close duration=8/4, source URL=5; cap at 100.
7. High requires score >=65, valid title identity, no hard conflict, and known duration inside the 20% near range.
8. Manual requires score >=35 without conflict. A marker-led episode with correct number but no parent identity returns exactly 35/manual.
9. Reject everything else with a stable Chinese reason.

Use SequenceMatcher only after NFKC/OpenCC variants; require at least four normalized characters for containment. Use match_provider(context.reg_src) for source evidence.

Implement `build_search_queries(context)` in matching.py. It returns no more than three deduplicated strings and, when `manual_query` is true, returns only the user's title plus its season-stripped fallback; stale aliases are excluded.

- [ ] **Step 5: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_matching.py tests/test_danmaku_utils.py -q
git add src/atv_player/danmaku/matching.py src/atv_player/danmaku/utils.py tests/test_danmaku_matching.py tests/test_danmaku_utils.py
git commit -m "feat: score danmaku candidates with hard conflicts"
~~~

## Task 4: Integrate matching into service orchestration

**Files:**
- Modify: src/atv_player/danmaku/providers/base.py
- Modify: src/atv_player/danmaku/service.py
- Modify: tests/test_danmaku_service.py

- [ ] **Step 1: Add failing service tests**

Add a ContextProvider fake whose search signature includes context=None and records received contexts. Test:

- a structured exact title/episode candidate is high and default;
- marker-only legacy candidate remains manual and visible;
- manual-only results leave default_option_url and default_provider empty;
- explicit year/season conflict is absent from groups;
- an old FakeProvider without context still works.

- [ ] **Step 2: Run the new cases**

Run: uv run pytest tests/test_danmaku_service.py -k "confidence or match_context or manual" -q

Expected: FAIL because service does not accept match_context.

- [ ] **Step 3: Add optional context capability**

Keep DanmakuProvider unchanged and add ContextAwareDanmakuProvider:

~~~python
class ContextAwareDanmakuProvider(Protocol):
    key: str

    def search(
        self,
        name: str,
        original_name: str | None = None,
        context: DanmakuMatchContext | None = None,
    ) -> list[DanmakuSearchItem]:
        raise NotImplementedError
~~~

- [ ] **Step 4: Thread context through service**

Add match_context=None to search_danmu, search_danmu_sources, rerank_danmaku_source_search_result, and _collect_search_results. Add:

~~~python
def _provider_search(self, key, query_name, original_name, match_context):
    search = self._providers[key].search
    if "context" in inspect.signature(search).parameters:
        return search(query_name, original_name=original_name, context=match_context)
    return search(query_name, original_name=original_name)
~~~

When context is absent, create a minimal one from query, extracted episode, duration, and reg_src.

- [ ] **Step 5: Evaluate and persist decisions**

Inside each provider worker, try `build_search_queries(match_context)` in order and stop trying further variants as soon as that provider produces a high-confidence candidate. This preserves cross-provider concurrency while limiting each provider to three searches. Deduplicate candidates by provider stable series/episode IDs, falling back to URL.

After provider expansion, call match_candidate once. Drop rejected rows and use dataclasses.replace to persist score/confidence/reasons. Copy metadata and matching fields to DanmakuSourceOption. Sort confidence high before manual, then score descending, then existing deterministic tie breakers.

Update _pick_default_source_option so only a currently re-evaluated high option can be default. Preferred page/provider/history can win only among high rows.

Retain existing explicit-episode, movie, variety, and provider fallback logic until each removed filter has an equivalent passing matcher regression.

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_service.py tests/test_danmaku_provider_concurrency.py -q
git add src/atv_player/danmaku/providers/base.py src/atv_player/danmaku/service.py tests/test_danmaku_service.py
git commit -m "feat: apply confidence matching to danmaku search"
~~~

Expected: PASS, including maximum provider-search concurrency of four.

## Task 5: Build playback context and context-aware caches

**Files:**
- Modify: src/atv_player/models.py
- Create: src/atv_player/danmaku/context.py
- Modify: src/atv_player/danmaku/cache.py
- Modify: src/atv_player/danmaku/generic.py
- Modify: src/atv_player/plugins/controller.py
- Create: tests/test_danmaku_context.py
- Modify: tests/test_danmaku_cache.py
- Modify: tests/test_generic_danmaku_controller.py
- Modify: tests/test_spider_plugin_controller.py

- [ ] **Step 1: Write failing context tests**

Test explicit PlayItem hints, original-title aliases, playlist episode inference, manual-query flag, duration override, and fingerprints changing with season, enabled providers, or rule version.

Required PlayItem hints:

~~~python
danmaku_aliases: list[str] = field(default_factory=list)
danmaku_year: int = 0
danmaku_season_number: int = 0
danmaku_episode_number: int = 0
danmaku_media_kind: str = ""
~~~

- [ ] **Step 2: Implement context.py**

Create the module with these complete public functions and the required imports (`json`, `re`, `sha256`, the context model, `infer_playlist_episode_number`, and `PlayItem`):

~~~python
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def build_match_context(
    item: PlayItem,
    playlist: list[PlayItem] | None = None,
    media_duration_seconds: int = 0,
) -> DanmakuMatchContext:
    title = (item.danmaku_search_title or item.media_title or item.title).strip()
    aliases: list[str] = []
    for value in (*item.danmaku_aliases, item.original_title):
        normalized = str(value or "").strip()
        if normalized and normalized != title and normalized not in aliases:
            aliases.append(normalized)
    year_match = _YEAR_RE.search(" ".join((item.media_title, item.original_title)))
    episode = item.danmaku_episode_number or infer_playlist_episode_number(item, playlist) or 0
    return DanmakuMatchContext(
        title=title,
        aliases=tuple(aliases),
        year=item.danmaku_year or (int(year_match.group(1)) if year_match else 0),
        season_number=max(0, int(item.danmaku_season_number or 0)),
        episode_number=max(0, int(episode)),
        media_kind=(item.danmaku_media_kind or item.type_name or item.category_name).strip(),
        duration_seconds=max(0, int(media_duration_seconds or item.duration_seconds or 0)),
        reg_src=str(item.vod_id or item.url or "").strip(),
        manual_query=bool(item.danmaku_search_query_overridden),
    )


def match_context_fingerprint(
    context: DanmakuMatchContext,
    provider_ids: list[str],
    rule_version: str,
) -> str:
    payload = {
        "rule": rule_version,
        "title": context.title,
        "aliases": context.aliases,
        "year": context.year,
        "season": context.season_number,
        "episode": context.episode_number,
        "kind": context.media_kind,
        "providers": sorted(set(provider_ids)),
        "reg_src": context.reg_src,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()
~~~

Title priority is manual danmaku_search_title, media_title, then item title. Deduplicate danmaku_aliases plus original_title. Explicit hints beat regex/playlist inference. Fingerprint canonical JSON containing rule, title, aliases, year, season, episode, kind, sorted providers, and reg_src, then SHA-256.

- [ ] **Step 3: Write failing cache tests**

Extend the source-option round trip with candidate metadata and match fields. Assert two different context fingerprints create different search-cache paths and stable provider episode IDs create different XML paths.

- [ ] **Step 4: Version and serialize caches**

In cache.py:

- source-search version v4 -> v5;
- XML version v1 -> v2;
- optional context_fingerprint parameter on source-search key/path/load/save;
- optional provider_episode_key on XML key/path/load/save;
- use dataclasses.asdict for candidate metadata;
- restore aliases/reasons as tuples;
- store score/confidence/reasons;
- read the old XML key only as migration fallback and rewrite successful fallback content under v2.

- [ ] **Step 5: Pass context through both controllers**

Build context only after final search title/episode selection. Use inspect.signature to pass match_context only when supported. Compute fingerprint with service.provider_order and DANMAKU_MATCH_RULE_VERSION="v1". Pass it to every source-cache variant. After every cache load, rerank with current context; never trust serialized defaults directly.

Add tests that a cached season-1 result does not become default in season 2 and manual-only cache restores candidates without selecting a URL.

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_context.py tests/test_danmaku_cache.py tests/test_generic_danmaku_controller.py tests/test_spider_plugin_controller.py -q
git add src/atv_player/models.py src/atv_player/danmaku/context.py src/atv_player/danmaku/cache.py src/atv_player/danmaku/generic.py src/atv_player/plugins/controller.py tests/test_danmaku_context.py tests/test_danmaku_cache.py tests/test_generic_danmaku_controller.py tests/test_spider_plugin_controller.py
git commit -m "feat: carry danmaku match context through caches"
~~~

## Task 6: Make series preferences stable and backward compatible

**Files:**
- Modify: src/atv_player/danmaku/models.py
- Modify: src/atv_player/danmaku/preferences.py
- Modify: src/atv_player/danmaku/service.py
- Modify: src/atv_player/plugins/controller.py
- Modify: tests/test_danmaku_preferences.py
- Modify: tests/test_danmaku_service.py
- Modify: tests/test_spider_plugin_controller.py

- [ ] **Step 1: Write failing key/migration tests**

Assert same title with year 2003 versus 2019 differs; season 1 versus 2 differs; a legacy JSON row lacking new fields loads; a new row round-trips stable series_id/year/season.

- [ ] **Step 2: Extend preferences**

Add defaults to DanmakuSeriesPreference:

~~~python
series_id: str = ""
year: int = 0
season_number: int = 0
~~~

Persist known fields explicitly; do not pass arbitrary JSON keys through **raw.

Change the key helper to:

~~~python
def build_danmaku_series_key(name: str, *, year: int = 0, season_number: int = 0) -> str:
    normalized = _compact_title(strip_episode_suffix(normalize_name(name)))
    return ":".join((normalized, str(max(0, year)), str(max(0, season_number))))
~~~

Load the old title-only key as migration fallback only; save new-format keys.

- [ ] **Step 3: Save stable selected identity**

In plugin controller, find the selected option and persist candidate_metadata.series_id plus current context year/season. Preference adds ranking evidence but never bypasses hard conflicts.

- [ ] **Step 4: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_preferences.py tests/test_danmaku_service.py tests/test_spider_plugin_controller.py -q
git add src/atv_player/danmaku/models.py src/atv_player/danmaku/preferences.py src/atv_player/danmaku/service.py src/atv_player/plugins/controller.py tests/test_danmaku_preferences.py tests/test_danmaku_service.py tests/test_spider_plugin_controller.py
git commit -m "feat: validate stable danmaku series preferences"
~~~


## Task 7: Add a shared bounded segment collector

**Files:**
- Create: src/atv_player/danmaku/providers/_segments.py
- Create: tests/test_danmaku_segment_collector.py

- [ ] **Step 1: Write failing bounded concurrency and partial-failure tests**

Create a worker that tracks active calls under a lock, sleeps briefly, returns one string, and raises for row 7. Assert output preserves successful input order and maximum active workers is eight:

~~~python
results = collect_segment_records(range(20), worker, max_workers=8)
assert state["max_active"] == 8
assert results == [str(index) for index in range(20) if index != 7]
~~~

- [ ] **Step 2: Run and verify the module is absent**

Run: uv run pytest tests/test_danmaku_segment_collector.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement settled collection**

Create _segments.py:

~~~python
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from atv_player.danmaku.providers._concurrency import iter_bounded_settled

T = TypeVar("T")
R = TypeVar("R")


def collect_segment_records(
    segments: Iterable[T],
    loader: Callable[[T], list[R]],
    *,
    max_workers: int = 8,
) -> list[R]:
    output: list[R] = []
    for batch in iter_bounded_settled(segments, loader, max_workers=max_workers):
        for settled in batch:
            if settled.error is None and settled.value:
                output.extend(settled.value)
    return output
~~~

- [ ] **Step 4: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_segment_collector.py tests/test_danmaku_provider_concurrency.py -q
git add src/atv_player/danmaku/providers/_segments.py tests/test_danmaku_segment_collector.py
git commit -m "feat: add bounded danmaku segment collection"
~~~

## Task 8: Implement native DandanPlay

**Files:**
- Create: src/atv_player/danmaku/providers/dandanplay.py
- Create: tests/test_danmaku_dandanplay_provider.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/sources/dandan.js

- [ ] **Step 1: Write fixed-response tests first**

Fake these direct official requests:

~~~text
GET https://api.dandanplay.net/api/v2/search/anime?keyword=进击的巨人
GET https://api.dandanplay.net/api/v2/bangumi/123
GET https://api.dandanplay.net/api/v2/comment/1230003?from=0&withRelated=true&chConvert=0
~~~

Search fixture: anime ID 123, title 进击的巨人, aliases 進擊的巨人 and Attack on Titan, year 2022. Detail fixture: season 4 episodes 1230001 and 1230003. Assert episode 3 returns dandan://episode/123/1230003 with complete metadata.

Also test: p="1.25,1,16711680,0" converts correctly; malformed comments are skipped; invalid custom URL raises DanmakuResolveError; network failure becomes “弹弹Play弹幕获取失败”.

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_dandanplay_provider.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement the provider**

Create DandanPlayDanmakuProvider with key="dandan" and injected `get`. Implement concrete methods `supports`, context-aware `search`, `resolve`, `_search_anime`, `_bangumi`, `_episode_id`, and `_comment_record`; the tests in Step 1 define every accepted input and output shape.

Use urlencode, timeout=10.0, follow_redirects=True, and User-Agent atv-player/dandan. Inspect at most eight anime rows. Parent title filtering happens via structured metadata and the central matcher. If context has an episode, return that episode; otherwise return the normalized episode list. Read aliases from bangumi.titles and only follow related seasons matching explicit context season.

Never call the danmu_api project or `api.danmaku.weeblify.app`; native mode uses only the official DandanPlay host. Treat a non-2xx or structurally invalid official response as an isolated provider search/resolve error.

For comments, accept only a list under comments. Parse p as time,mode,color,...; mode 4 -> bottom, 5 -> top, else scrolling. Use m as text, skip malformed/empty rows, sort by time/content.

- [ ] **Step 4: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_dandanplay_provider.py -q
uv run ruff check src/atv_player/danmaku/providers/dandanplay.py tests/test_danmaku_dandanplay_provider.py
git add src/atv_player/danmaku/providers/dandanplay.py tests/test_danmaku_dandanplay_provider.py
git commit -m "feat: add native DandanPlay danmaku provider"
~~~

## Task 9: Implement native Animeko with node health

**Files:**
- Create: src/atv_player/danmaku/providers/animeko.py
- Create: tests/test_danmaku_animeko_provider.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/sources/animeko.js

- [ ] **Step 1: Write search/fallback/comment fixtures**

Simulate:

- POST api.bangumi.lol/v0/search/subjects?limit=20&offset=0 with id, name, name_cn, date, platform, aliases;
- GET api.animeko.org/v2/subjects/{id} with MAIN and SP episodes;
- first danmaku node timeout and second node returning danmakuList;
- location NORMAL -> 1, TOP -> 5, BOTTOM -> 4, color -1 -> white.

Assert SP is excluded and the last successful danmaku node is tried first on the next resolve.

Also assert malformed search/subject/comment payloads return no candidates or records without leaking raw payloads.

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_animeko_provider.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement queues and health**

Create AnimekoDanmakuProvider with injected get/post:

~~~python
SEARCH_NODES = ("https://api.bangumi.lol", "https://api.bgm.tv")
SUBJECT_NODES = (
    "https://api.animeko.org",
    "https://danmaku-global.myani.org",
    "https://danmaku-cn.myani.org",
    "https://s1.animeko.openani.org",
)
~~~

POST {"keyword": keyword, "filter": {"type": [2]}}. Stop after 60 search rows. Use five-second search/detail and three-second comments timeouts. Keep independent subject/comment healthy-node indices; update only after structurally valid data.

Return animeko://episode/{subject_id}/{episode_id}. Metadata includes parent names/aliases, year from date, explicit season, MAIN episode sort, and media_kind tv. Resolve /v1/danmaku/{episode_id}; accept rows with danmakuInfo.text and numeric playTime.

- [ ] **Step 4: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_animeko_provider.py -q
uv run ruff check src/atv_player/danmaku/providers/animeko.py tests/test_danmaku_animeko_provider.py
git add src/atv_player/danmaku/providers/animeko.py tests/test_danmaku_animeko_provider.py
git commit -m "feat: add native Animeko danmaku provider"
~~~

## Task 10: Implement native LeTV

**Files:**
- Create: src/atv_player/danmaku/providers/leshi.py
- Create: tests/test_danmaku_leshi_provider.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/sources/leshi.js

- [ ] **Step 1: Write HTML and segment fixtures**

Use minimal HTML:

~~~html
<div class="So-detail" data-info="{pid:'10026580',type:'tv',year:'2026'}">
  <h1><a title="剑来"></a></h1>
</div>
<a href="https://www.le.com/ptv/vplay/77917395.html" title="第1集"></a>
<a href="https://www.le.com/ptv/vplay/77917396.html" title="第2集"></a>
<script>var video = {duration:'00:42:00'};</script>
~~~

Return JSONP containing one list row with id/start/position/color/txt. Assert episode 2 becomes leshi://episode/10026580/77917396; 2,520 seconds yields nine segments; active segment calls never exceed eight; one failed segment does not discard other records.

Add cases for missing `data-info`, invalid restricted-object syntax, invalid JSONP, and an unsupported custom URL.

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_leshi_provider.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement safe HTML parsing**

Create LeshiDanmakuProvider with injected get. Search so.le.com/s using urlencode. Parse each So-detail block. Convert restricted data-info by quoting bare ASCII keys and replacing single-quoted scalar values; never use eval. Try tv, comic, playlet, movie details and extract unique /ptv/vplay/{video_id}.html in document order.

- [ ] **Step 4: Implement segment resolution**

Resolve leshi://episode/{media_id}/{video_id}. Parse duration as HH:MM:SS, MM:SS, or seconds; default 2,400. Build five-minute hd-my.le.com/danmu/list requests, parse only the JSON object inside the exact JSONP callback, and call collect_segment_records(max_workers=8).

Map positions {1:1, 2:5, 3:4}, parse hex colors, skip empty txt, and sort records.

- [ ] **Step 5: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_leshi_provider.py tests/test_danmaku_segment_collector.py -q
uv run ruff check src/atv_player/danmaku/providers/leshi.py tests/test_danmaku_leshi_provider.py
git add src/atv_player/danmaku/providers/leshi.py tests/test_danmaku_leshi_provider.py
git commit -m "feat: add native LeTV danmaku provider"
~~~

## Task 11: Implement native Xigua

**Files:**
- Create: src/atv_player/danmaku/providers/xigua.py
- Create: tests/test_danmaku_xigua_provider.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/sources/xigua.js

- [ ] **Step 1: Write mobile HTML and comment fixtures**

Search HTML contains a 相关视频 section with two s-long-video cards plus unrelated cards outside it. Detail HTML contains valid episodes_list JSON and "duration":2520. Assert only scoped cards survive, seq_num supplies episode, and a 120-second clip cannot auto-match a 2,520-second context.

Comment JSON:

~~~json
{"data":[{"danmaku_id":"1","offset_time":1500,"text":"西瓜弹幕"}]}
~~~

Assert record (1.5, 1, "16777215", "西瓜弹幕") and nine millisecond-range ib.snssdk.com URLs.

Add cases for missing related-video section, malformed `episodes_list`, nonnumeric duration, malformed comment JSON, and invalid custom URL.

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_xigua_provider.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement scoped search and robust JSON extraction**

Create XiguaDanmakuProvider with injected get, mobile Safari headers, and xigua://episode/{album_id}/{item_id}. Parse only the related-video section, normalize protocol-relative images, and extract type/year. Use json.JSONDecoder().raw_decode beginning after episodes_list rather than a non-greedy nested-JSON regex.

- [ ] **Step 4: Implement segment comments**

Read numeric duration, build five-minute millisecond segments, request ib.snssdk.com/vapp/danmaku/list/v1 with item_id/start_time/end_time/format=json, and use max eight workers. Skip missing text/non-numeric offsets and sort.

- [ ] **Step 5: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_xigua_provider.py tests/test_danmaku_matching.py -q
uv run ruff check src/atv_player/danmaku/providers/xigua.py tests/test_danmaku_xigua_provider.py
git add src/atv_player/danmaku/providers/xigua.py tests/test_danmaku_xigua_provider.py
git commit -m "feat: add native Xigua danmaku provider"
~~~


## Task 12: Port and verify HanjuTV crypto

**Files:**
- Create: src/atv_player/danmaku/providers/_hanjutv_crypto.py
- Create: tests/test_danmaku_hanjutv_crypto.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/utils/hanjutv-util.js

- [ ] **Step 1: Record deterministic vectors in failing tests**

Freeze UID, install timestamp, request timestamp, OA, and encrypted response input. Use the JavaScript reference once to record literal expected base64 values for uk/mobile sign/TV di/TV rp and one encrypted payload. CI tests must not invoke Node or the network.

Required behavioral assertions:

~~~python
headers = build_mobile_headers(uid="A" * 20, session_ts=1_700_000_000_000, request_ts=1_700_000_001_000)
assert headers["uid"] == "A" * 20
assert decrypt_hanjutv_payload(encrypted_fixture, uid="A" * 20) == {
    "seriesList": [{"sid": "1", "name": "测试"}]
}
encoded = encode_merged_episode_id("pid-1", "eid-1")
assert parse_episode_ref(encoded) == (("hxq", "pid-1"), ("tv", "eid-1"))
~~~

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_hanjutv_crypto.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement with PyCryptodome**

Create concrete functions `build_mobile_headers`, `build_tv_headers`, `decrypt_hanjutv_payload`, `encode_merged_episode_id`, and `parse_episode_ref` with the exact arguments and return values exercised by Step 1's deterministic vectors.

Use Crypto.Cipher.AES.MODE_CBC, PKCS#7 for encryption, control-character stripping after decryption, urlsafe base64 without padding for merged IDs, and constants from the reference. Do not port the JavaScript pure-AES implementation. Validate key/IV length and raise DanmakuResolveError for malformed encrypted payloads.

- [ ] **Step 4: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_hanjutv_crypto.py -q
uv run ruff check src/atv_player/danmaku/providers/_hanjutv_crypto.py tests/test_danmaku_hanjutv_crypto.py
git add src/atv_player/danmaku/providers/_hanjutv_crypto.py tests/test_danmaku_hanjutv_crypto.py
git commit -m "feat: add HanjuTV request signing and decoding"
~~~

## Task 13: Implement native HanjuTV

**Files:**
- Create: src/atv_player/danmaku/providers/hanjutv.py
- Create: tests/test_danmaku_hanjutv_provider.py
- Reference: /home/harold/workspace/danmu_api/danmu_api/sources/hanjutv.js

- [ ] **Step 1: Write dual-route and fallback fixtures**

Cover:

- S5 row sid=hxq-1, name=来自星星的你, year=2013;
- TV row with same exact title and compatible year/category under sid=tv-1;
- same-title conflicting-year rows that must not pair;
- HXQ detail/episodes with pid and TV detail/episodes with eid;
- primary comment host failure followed by fallback-host success;
- TV bulletchat fallback only when both HXQ hosts yield nothing.

Assert compatible exact-title rows become one merged candidate; ambiguous/conflicting pairs stay separate. Merged resolve prefers HXQ and uses TV strictly as fallback, never duplicate-merging both.

- [ ] **Step 2: Run and verify import failure**

Run: uv run pytest tests/test_danmaku_hanjutv_provider.py -q

Expected: FAIL on import.

- [ ] **Step 3: Implement identity-safe dual search**

Create HanjuTVDanmakuProvider with key="hanjutv", injected get:

~~~python
APP_HOST = "https://hxqapi.hiyun.tv"
TV_HOST = "https://api.xiawen.tv"
DANMAKU_HOSTS = (APP_HOST, "https://hxqapi.zmdcq.com")
~~~

Search S5 and TV through iter_bounded_settled. Decode when payload.data is encrypted text. Normalize IDs/title/year/category/episode count/route. Pair only exact NFKC titles whose known year/category/play mode do not conflict and whose mutual best match is unique.

- [ ] **Step 4: Expand episodes into stable URLs**

Load HXQ and TV detail/episodes; normalize positive serial numbers and pair only equal serials. Use:

~~~text
hanjutv://episode/hxq/{pid}
hanjutv://episode/tv/{eid}
hanjutv://episode/merged/{url-safe-payload}
~~~

Metadata carries stable series identity, parent title, year, episode number, and media-kind mapping: 电影 -> movie, 综艺 -> variety, drama categories -> tv.

- [ ] **Step 5: Implement fallback comment pagination**

For HXQ refs, page /api/danmu/playItem/list in 60-second axes, at most 240 pages. Stop for non-increasing nextAxis, empty final page, or maximum axis. Try primary then fallback host and stop on first nonempty host. Use encrypted TV bulletchat only when HXQ produced none.

Map milliseconds t, tp (2 -> 5, 4 -> 4, otherwise 1), sc color, con text. Skip malformed rows and sort.

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_hanjutv_crypto.py tests/test_danmaku_hanjutv_provider.py -q
uv run ruff check src/atv_player/danmaku/providers/hanjutv.py tests/test_danmaku_hanjutv_provider.py
git add src/atv_player/danmaku/providers/hanjutv.py tests/test_danmaku_hanjutv_provider.py
git commit -m "feat: add native HanjuTV danmaku provider"
~~~

## Task 14: Register providers, expose confidence, and update help

**Files:**
- Modify: src/atv_player/danmaku/providers/__init__.py
- Modify: src/atv_player/danmaku/service.py
- Modify: src/atv_player/source_preferences.py
- Modify: src/atv_player/ui/player_window.py
- Modify: docs/help.md
- Modify: tests/test_danmaku_service.py
- Modify: tests/test_main_window_ui.py
- Modify: tests/test_player_window_ui.py

- [ ] **Step 1: Write failing registry/settings tests**

Expected default base order:

~~~python
[
    "tencent", "youku", "bilibili", "iqiyi", "mgtv", "sohu", "migu", "renren",
    "dandan", "animeko", "leshi", "xigua", "hanjutv",
]
~~~

Assert five labels appear in advanced settings/player filter; disabling each removes it; injected get/post reach every constructor.

- [ ] **Step 2: Write failing confidence-label tests**

Build high/manual source options and assert labels contain:

~~~text
高｜标题完全一致、集号一致、时长接近 · 百花杀 第13集 · 45:00
手选｜标题相似 · 候选标题
~~~

Assert manual-only results do not preselect or auto-download a URL.

- [ ] **Step 3: Register classes and labels**

Export all five provider classes. Instantiate them in create_default_danmaku_service with injected transports. Add labels:

~~~python
"dandan": "弹弹Play",
"animeko": "Animeko",
"leshi": "乐视",
"xigua": "西瓜",
"hanjutv": "韩小圈",
~~~

Append matching entries to DANMAKU_SOURCE_PREFERENCES and _DANMAKU_SEARCH_PROVIDER_OPTIONS.

- [ ] **Step 4: Add media-kind tie orders**

Add:

~~~python
_ANIME_TIE_ORDER = ("bilibili", "dandan", "animeko", "tencent", "youku", "iqiyi")
_LIVE_ACTION_TIE_ORDER = (
    "tencent", "youku", "iqiyi", "mgtv", "sohu", "leshi", "xigua", "migu", "hanjutv", "renren"
)
~~~

Apply only after confidence/score. Unknown kind/provider falls back to base order. Test equal-score anime chooses DandanPlay before Tencent and live action chooses Tencent before HanjuTV.

- [ ] **Step 5: Render confidence and full diagnostic tooltip**

Format:

~~~python
confidence = {"high": "高", "manual": "手选"}.get(option.match_confidence, "")
evidence = "、".join(option.match_reasons[:3])
prefix = f"{confidence}｜{evidence}" if confidence and evidence else confidence
label = f"{prefix} · {option.name}" if prefix else option.name
~~~

Append duration after candidate name. Tooltip contains all reasons. Existing empty-confidence options keep their old display.

- [ ] **Step 6: Update help**

List five new native sources in docs/help.md. Explain high/manual labels, high-only auto-loading, provider filters, and that provider failures are isolated.

- [ ] **Step 7: Verify and commit**

Run:

~~~bash
uv run pytest tests/test_danmaku_service.py tests/test_main_window_ui.py -k "danmaku_source or provider_order or default_service" -q
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_player_window_ui.py -k "danmaku_source" -q
git add src/atv_player/danmaku/providers/__init__.py src/atv_player/danmaku/service.py src/atv_player/source_preferences.py src/atv_player/ui/player_window.py docs/help.md tests/test_danmaku_service.py tests/test_main_window_ui.py tests/test_player_window_ui.py
git commit -m "feat: expose expanded native danmaku providers"
~~~

## Task 15: Full regression, static checks, and live smoke tests

**Files:**
- Modify only if verification finds a defect in a file already owned by this plan.

- [ ] **Step 1: Run all focused tests**

Run:

~~~bash
uv run pytest tests/test_danmaku_*.py tests/test_generic_danmaku_controller.py tests/test_direct_parse_danmaku.py tests/test_spider_plugin_controller.py -q
~~~

Expected: PASS.

- [ ] **Step 2: Run formatting, lint, and type checks**

Run:

~~~bash
uv run ruff format --check src tests
uv run ruff check src tests
npx --yes pyright
~~~

Expected: PASS. If unrelated pre-existing failures exist, rerun on all changed files and record unrelated failures verbatim.

- [ ] **Step 3: Run the complete suite**

Run:

~~~bash
QT_QPA_PLATFORM=offscreen uv run pytest -q
~~~

Expected: PASS.

- [ ] **Step 4: Smoke-test native endpoints with network approval**

Provider-filtered searches:

~~~text
dandan: 进击的巨人 1集
animeko: 进击的巨人 1集
leshi: 剑来 1集
xigua: 西游记 1集
hanjutv: 来自星星的你 1集
~~~

Print only provider, count, first candidate name, stable ID, confidence, reasons, and at most the first high candidate's comment count. Never print response bodies, signatures, tokens, or headers.

Expected: each reachable provider returns a structurally valid result, or a provider-specific timeout/region/interface error. Network failure does not invalidate fixture tests; malformed live data requires a redacted fixture and parser regression before completion.

- [ ] **Step 5: Verify scope and commit any test-driven smoke fix**

Run:

~~~bash
git status --short
git diff --check
git log --oneline -15
~~~

Expected: no plan-owned uncommitted changes and one focused commit per task. If smoke verification required a code change, first add its fixture regression and then commit only that fix:

~~~bash
git commit -m "fix: handle verified danmaku provider response"
~~~

## Plan self-review record

- Spec coverage: matching architecture, all five native providers, conservative default selection, playback context, cache versioning, stable history, UI evidence, bounded concurrency, current regression baseline, and live smoke checks have explicit tasks.
- Placeholder scan: the plan contains no deferred implementation markers; every code-changing task names exact paths, behaviors, commands, and expected results.
- Type consistency: later tasks consistently use DanmakuMatchContext, DanmakuCandidateMetadata, DanmakuMatchResult, candidate_metadata, match_score, match_confidence, match_reasons, and match_context.
- Scope: all tasks belong to one danmaku search/resolve subsystem. Cross-provider merging and the three deferred providers remain excluded.
- Worktree safety: Task 1 reviews and isolates the current user-owned dirty baseline before later commits touch overlapping files.
