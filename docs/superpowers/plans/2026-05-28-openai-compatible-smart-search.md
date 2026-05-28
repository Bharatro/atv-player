# OpenAI-Compatible Smart Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenAI-compatible cloud AI settings and a natural-language `智能匹配` global-search tab that parses user intent with Chat Completions and ranks existing local results.

**Architecture:** Keep AI behind a small `atv_player.ai` module and keep smart search behind a `atv_player.search` module. The first UI integration is a global-search-only tab, so existing global search sources still run unchanged and AI failures are isolated to the smart tab. The LLM receives only the user's query and a JSON schema; local behavior data stays local and is used only by deterministic ranking.

**Tech Stack:** Python 3.12, PySide6, httpx, SQLite, pytest, pytest-qt, existing `MainWindow` global search flow.

---

## File Map

- `src/atv_player/models.py`
  Add AI config fields to `AppConfig`.
- `src/atv_player/storage.py`
  Add SQLite columns, load/save support, and normalization helpers for AI config.
- `src/atv_player/ai/__init__.py`
  Export the AI client and search intent parser.
- `src/atv_player/ai/models.py`
  Define provider config, request/result records, and typed AI errors.
- `src/atv_player/ai/openai_compatible.py`
  Implement a minimal Chat Completions-compatible HTTP client with `httpx`.
- `src/atv_player/ai/search_intent.py`
  Implement prompt construction, JSON extraction, and `SmartSearchIntent` normalization.
- `src/atv_player/search/__init__.py`
  Export smart search models and controller.
- `src/atv_player/search/models.py`
  Define `SmartSearchCandidate`, `SmartSearchResult`, and source labels.
- `src/atv_player/search/ranking.py`
  Score local candidates against structured intent.
- `src/atv_player/search/controller.py`
  Provide `search_items(keyword, page)` for the `智能匹配` global-search tab.
- `src/atv_player/ui/advanced_settings_dialog.py`
  Add the AI settings tab and connection test button.
- `src/atv_player/ui/main_window.py`
  Register a global-search-only smart tab when the controller is available.
- `src/atv_player/app.py`
  Build and inject the smart search controller from saved config and existing controllers.
- `tests/test_storage.py`
  Cover AI config defaults, persistence, migration, and normalization.
- `tests/test_ai_openai_compatible.py`
  Cover request URL, headers, payload, compatible response parsing, and sanitized errors.
- `tests/test_ai_search_intent.py`
  Cover intent parsing, invalid JSON fallback, and field normalization.
- `tests/test_smart_search_ranking.py`
  Cover deterministic scoring and explanation strings.
- `tests/test_smart_search_controller.py`
  Cover disabled AI fallback, parser failure, pagination, and local candidate ranking.
- `tests/test_app.py`
  Cover settings UI persistence and app-level controller injection.
- `tests/test_main_window_ui.py`
  Cover the `智能匹配` global-search-only tab integration.

---

### Task 1: Persist AI Provider Settings

**Files:**
- Modify: `src/atv_player/models.py`
- Modify: `src/atv_player/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Append these tests to `tests/test_storage.py`:

```python
def test_app_config_defaults_ai_settings_disabled() -> None:
    config = AppConfig()

    assert config.ai_enabled is False
    assert config.ai_base_url == ""
    assert config.ai_api_key == ""
    assert config.ai_chat_model == ""
    assert config.ai_request_timeout_seconds == 30


def test_settings_repository_saves_ai_provider_config(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.ai_enabled = True
    config.ai_base_url = "https://api.example.com/v1"
    config.ai_api_key = "sk-test"
    config.ai_chat_model = "gpt-4o-mini"
    config.ai_request_timeout_seconds = 45

    repo.save_config(config)
    saved = SettingsRepository(tmp_path / "app.db").load_config()

    assert saved.ai_enabled is True
    assert saved.ai_base_url == "https://api.example.com/v1"
    assert saved.ai_api_key == "sk-test"
    assert saved.ai_chat_model == "gpt-4o-mini"
    assert saved.ai_request_timeout_seconds == 45


def test_settings_repository_normalizes_ai_values(tmp_path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    repo.save_config(
        AppConfig(
            ai_enabled=True,
            ai_base_url=" https://api.example.com/v1/ ",
            ai_api_key=" sk-test ",
            ai_chat_model=" gpt-4o-mini ",
            ai_request_timeout_seconds=999,
        )
    )

    saved = repo.load_config()

    assert saved.ai_base_url == "https://api.example.com/v1"
    assert saved.ai_api_key == "sk-test"
    assert saved.ai_chat_model == "gpt-4o-mini"
    assert saved.ai_request_timeout_seconds == 120
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_storage.py -k "ai_provider_config or ai_settings" -q
```

Expected: FAIL with `AttributeError` for missing `AppConfig.ai_enabled`.

- [ ] **Step 3: Add AppConfig fields**

In `src/atv_player/models.py`, add these fields after `global_search_hot_source`:

```python
    ai_enabled: bool = False
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_chat_model: str = ""
    ai_request_timeout_seconds: int = 30
```

- [ ] **Step 4: Add storage normalization helpers**

In `src/atv_player/storage.py`, add helpers near the other `_normalize_*` functions:

```python
def _normalize_ai_base_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def _normalize_ai_secret(value: object) -> str:
    return str(value or "").strip()


def _normalize_ai_model(value: object) -> str:
    return str(value or "").strip()


def _normalize_ai_timeout(value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return 30
    return max(5, min(timeout, 120))
```

- [ ] **Step 5: Add SQLite columns and INSERT defaults**

In `SettingsRepository._init_db()`, add columns to `CREATE TABLE app_config` after `global_search_hot_source`:

```sql
                    ai_enabled INTEGER NOT NULL DEFAULT 0,
                    ai_base_url TEXT NOT NULL DEFAULT '',
                    ai_api_key TEXT NOT NULL DEFAULT '',
                    ai_chat_model TEXT NOT NULL DEFAULT '',
                    ai_request_timeout_seconds INTEGER NOT NULL DEFAULT 30,
```

Add migration checks after the `global_search_hot_source` migration block:

```python
            if "ai_enabled" not in columns:
                conn.execute("ALTER TABLE app_config ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 0")
            if "ai_base_url" not in columns:
                conn.execute("ALTER TABLE app_config ADD COLUMN ai_base_url TEXT NOT NULL DEFAULT ''")
            if "ai_api_key" not in columns:
                conn.execute("ALTER TABLE app_config ADD COLUMN ai_api_key TEXT NOT NULL DEFAULT ''")
            if "ai_chat_model" not in columns:
                conn.execute("ALTER TABLE app_config ADD COLUMN ai_chat_model TEXT NOT NULL DEFAULT ''")
            if "ai_request_timeout_seconds" not in columns:
                conn.execute("ALTER TABLE app_config ADD COLUMN ai_request_timeout_seconds INTEGER NOT NULL DEFAULT 30")
```

Update the initial `INSERT INTO app_config` column list and values so the five AI values appear after `global_search_hot_source`:

```sql
                    global_search_hot_source,
                    ai_enabled,
                    ai_base_url,
                    ai_api_key,
                    ai_chat_model,
                    ai_request_timeout_seconds,
                    following_episode_display_mode,
```

```sql
                    NULL, NULL, NULL, NULL, 'douban', '', '', '[]', '360',
                    0, '', '', '', 30,
                    'poster', 1
```

- [ ] **Step 6: Load and save AI fields**

In `load_config()`, add the fields to the `SELECT`, tuple unpacking, and `AppConfig(...)` construction:

```python
                    global_search_hot_source,
                    ai_enabled,
                    ai_base_url,
                    ai_api_key,
                    ai_chat_model,
                    ai_request_timeout_seconds,
                    following_episode_display_mode,
```

```python
            global_search_hot_source,
            ai_enabled,
            ai_base_url,
            ai_api_key,
            ai_chat_model,
            ai_request_timeout_seconds,
            following_episode_display_mode,
```

```python
            global_search_hot_source=str(global_search_hot_source or "360").strip() or "360",
            ai_enabled=bool(ai_enabled),
            ai_base_url=_normalize_ai_base_url(ai_base_url),
            ai_api_key=_normalize_ai_secret(ai_api_key),
            ai_chat_model=_normalize_ai_model(ai_chat_model),
            ai_request_timeout_seconds=_normalize_ai_timeout(ai_request_timeout_seconds),
            following_episode_display_mode=_normalize_following_episode_display_mode(
```

In `save_config()`, add the same fields to the `UPDATE` statement and value tuple:

```python
                    global_search_hot_source = ?,
                    ai_enabled = ?,
                    ai_base_url = ?,
                    ai_api_key = ?,
                    ai_chat_model = ?,
                    ai_request_timeout_seconds = ?,
                    following_episode_display_mode = ?,
```

```python
                    str(config.global_search_hot_source or "360").strip() or "360",
                    int(config.ai_enabled),
                    _normalize_ai_base_url(config.ai_base_url),
                    _normalize_ai_secret(config.ai_api_key),
                    _normalize_ai_model(config.ai_chat_model),
                    _normalize_ai_timeout(config.ai_request_timeout_seconds),
                    _normalize_following_episode_display_mode(config.following_episode_display_mode),
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/test_storage.py -k "ai_provider_config or ai_settings" -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/atv_player/models.py src/atv_player/storage.py tests/test_storage.py
git commit -m "feat: persist ai provider settings"
```

---

### Task 2: Add OpenAI-Compatible Chat Client

**Files:**
- Create: `src/atv_player/ai/__init__.py`
- Create: `src/atv_player/ai/models.py`
- Create: `src/atv_player/ai/openai_compatible.py`
- Test: `tests/test_ai_openai_compatible.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_ai_openai_compatible.py`:

```python
from __future__ import annotations

import json

import httpx
import pytest

from atv_player.ai.models import AIProviderConfig
from atv_player.ai.openai_compatible import OpenAICompatibleClient, OpenAICompatibleError


def test_chat_completion_posts_to_normalized_v1_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"mode\":\"smart_discovery\"}"}}]},
        )

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com",
            api_key="sk-test",
            chat_model="model-a",
            timeout_seconds=12,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = client.chat_completion(
        messages=[{"role": "user", "content": "类似黑镜"}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test"
    assert captured["json"]["model"] == "model-a"
    assert result.content == "{\"mode\":\"smart_discovery\"}"


def test_chat_completion_preserves_existing_v1_base_url() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1/",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    client.chat_completion(messages=[{"role": "user", "content": "x"}])

    assert urls == ["https://api.example.com/v1/chat/completions"]


def test_chat_completion_raises_sanitized_error_without_api_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key sk-test"}})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        client.chat_completion(messages=[{"role": "user", "content": "x"}])

    assert "401" in str(exc_info.value)
    assert "sk-test" not in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_ai_openai_compatible.py -q
```

Expected: FAIL because `atv_player.ai` does not exist.

- [ ] **Step 3: Implement AI models**

Create `src/atv_player/ai/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AIProviderConfig:
    base_url: str
    api_key: str
    chat_model: str
    timeout_seconds: int = 30

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.chat_model.strip())


@dataclass(slots=True)
class AICompletionResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)


class AIError(RuntimeError):
    pass
```

- [ ] **Step 4: Implement compatible client**

Create `src/atv_player/ai/openai_compatible.py`:

```python
from __future__ import annotations

from typing import Any

import httpx

from atv_player.ai.models import AICompletionResult, AIError, AIProviderConfig


class OpenAICompatibleError(AIError):
    pass


def _completion_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise OpenAICompatibleError("AI API 地址不能为空")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _sanitize_message(message: str, api_key: str) -> str:
    sanitized = str(message or "")
    if api_key:
        sanitized = sanitized.replace(api_key, "[redacted]")
    return sanitized


class OpenAICompatibleClient:
    def __init__(
        self,
        config: AIProviderConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        response_format: dict[str, object] | None = None,
    ) -> AICompletionResult:
        if not self._config.is_complete:
            raise OpenAICompatibleError("AI API 配置不完整")
        payload: dict[str, Any] = {
            "model": self._config.chat_model.strip(),
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = dict(response_format)
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    _completion_url(self._config.base_url),
                    headers={"Authorization": f"Bearer {self._config.api_key.strip()}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, self._config.api_key)
            raise OpenAICompatibleError(f"AI API 请求失败: HTTP {exc.response.status_code} {body}") from exc
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), self._config.api_key)
            raise OpenAICompatibleError(f"AI API 请求失败: {message}") from exc
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise OpenAICompatibleError("AI API 响应缺少 choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else ""
        return AICompletionResult(content=str(content or ""), raw=data)
```

- [ ] **Step 5: Export module**

Create `src/atv_player/ai/__init__.py`:

```python
from atv_player.ai.models import AICompletionResult, AIError, AIProviderConfig
from atv_player.ai.openai_compatible import OpenAICompatibleClient, OpenAICompatibleError

__all__ = [
    "AICompletionResult",
    "AIError",
    "AIProviderConfig",
    "OpenAICompatibleClient",
    "OpenAICompatibleError",
]
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/test_ai_openai_compatible.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/ai tests/test_ai_openai_compatible.py
git commit -m "feat: add openai compatible client"
```

---

### Task 3: Parse Natural-Language Search Intent

**Files:**
- Create: `src/atv_player/ai/search_intent.py`
- Modify: `src/atv_player/ai/__init__.py`
- Test: `tests/test_ai_search_intent.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_ai_search_intent.py`:

```python
from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntentParser


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []

    def chat_completion(self, *, messages, temperature=0.0, response_format=None):
        self.messages = messages
        return type("Result", (), {"content": self.content})()


def test_intent_parser_normalizes_black_mirror_query() -> None:
    client = FakeClient(
        """
        {
          "mode": "smart_discovery",
          "media_types": ["tv"],
          "genres": ["科幻", "悬疑"],
          "rating_min": 8.0,
          "keywords": ["高分", "科幻"],
          "reference_titles": ["黑镜"],
          "sort_preference": "rating"
        }
        """
    )
    parser = SmartSearchIntentParser(client)

    intent = parser.parse("类似黑镜的高分科幻")

    assert intent.query_text == "类似黑镜的高分科幻"
    assert intent.mode == "smart_discovery"
    assert intent.media_types == ["tv"]
    assert intent.genres == ["科幻", "悬疑"]
    assert intent.rating_min == 8.0
    assert intent.keywords == ["高分", "科幻"]
    assert intent.reference_titles == ["黑镜"]
    assert intent.sort_preference == "rating"
    assert "只输出 JSON" in client.messages[0]["content"]


def test_intent_parser_falls_back_to_title_search_on_invalid_json() -> None:
    parser = SmartSearchIntentParser(FakeClient("not-json"))

    intent = parser.parse("流浪地球")

    assert intent.mode == "title_search"
    assert intent.query_text == "流浪地球"
    assert intent.keywords == ["流浪地球"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_ai_search_intent.py -q
```

Expected: FAIL because `atv_player.ai.search_intent` does not exist.

- [ ] **Step 3: Implement intent parser**

Create `src/atv_player/ai/search_intent.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


_VALID_MODES = {"title_search", "smart_discovery"}
_VALID_SORTS = {"rating", "popularity", "recent", "relevance"}


@dataclass(slots=True)
class SmartSearchIntent:
    query_text: str
    mode: str = "title_search"
    media_types: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    mood: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    year_min: int = 0
    year_max: int = 0
    rating_min: float = 0.0
    max_runtime_minutes: int = 0
    keywords: list[str] = field(default_factory=list)
    reference_titles: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    sort_preference: str = "relevance"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fallback_intent(query_text: str) -> SmartSearchIntent:
    normalized = str(query_text or "").strip()
    return SmartSearchIntent(query_text=normalized, keywords=[normalized] if normalized else [])


def _json_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {}


class SmartSearchIntentParser:
    def __init__(self, client) -> None:
        self._client = client

    def parse(self, query_text: str) -> SmartSearchIntent:
        normalized_query = str(query_text or "").strip()
        try:
            result = self._client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是影视搜索意图解析器。只输出 JSON，不要输出解释。"
                            "字段包含 mode, media_types, genres, mood, countries, languages, "
                            "year_min, year_max, rating_min, max_runtime_minutes, keywords, "
                            "reference_titles, negative_keywords, sort_preference。"
                        ),
                    },
                    {"role": "user", "content": normalized_query},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            payload = _json_payload(result.content)
        except Exception:
            return _fallback_intent(normalized_query)
        mode = str(payload.get("mode") or "title_search").strip()
        sort_preference = str(payload.get("sort_preference") or "relevance").strip()
        intent = SmartSearchIntent(
            query_text=normalized_query,
            mode=mode if mode in _VALID_MODES else "title_search",
            media_types=_string_list(payload.get("media_types")),
            genres=_string_list(payload.get("genres")),
            mood=_string_list(payload.get("mood")),
            countries=_string_list(payload.get("countries")),
            languages=_string_list(payload.get("languages")),
            year_min=_int_value(payload.get("year_min")),
            year_max=_int_value(payload.get("year_max")),
            rating_min=max(0.0, min(_float_value(payload.get("rating_min")), 10.0)),
            max_runtime_minutes=max(0, _int_value(payload.get("max_runtime_minutes"))),
            keywords=_string_list(payload.get("keywords")),
            reference_titles=_string_list(payload.get("reference_titles")),
            negative_keywords=_string_list(payload.get("negative_keywords")),
            sort_preference=sort_preference if sort_preference in _VALID_SORTS else "relevance",
        )
        if not intent.keywords:
            intent.keywords = [normalized_query] if normalized_query else []
        return intent
```

- [ ] **Step 4: Export parser**

Update `src/atv_player/ai/__init__.py`:

```python
from atv_player.ai.models import AICompletionResult, AIError, AIProviderConfig
from atv_player.ai.openai_compatible import OpenAICompatibleClient, OpenAICompatibleError
from atv_player.ai.search_intent import SmartSearchIntent, SmartSearchIntentParser

__all__ = [
    "AICompletionResult",
    "AIError",
    "AIProviderConfig",
    "OpenAICompatibleClient",
    "OpenAICompatibleError",
    "SmartSearchIntent",
    "SmartSearchIntentParser",
]
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_ai_search_intent.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ai tests/test_ai_search_intent.py
git commit -m "feat: parse smart search intent"
```

---

### Task 4: Rank Local Smart Search Candidates

**Files:**
- Create: `src/atv_player/search/__init__.py`
- Create: `src/atv_player/search/models.py`
- Create: `src/atv_player/search/ranking.py`
- Test: `tests/test_smart_search_ranking.py`

- [ ] **Step 1: Write failing ranking tests**

Create `tests/test_smart_search_ranking.py`:

```python
from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.search.models import SmartSearchCandidate
from atv_player.search.ranking import rank_candidates


def test_rank_candidates_rewards_keywords_rating_and_source() -> None:
    intent = SmartSearchIntent(
        query_text="类似黑镜的高分科幻",
        mode="smart_discovery",
        genres=["科幻"],
        keywords=["科幻"],
        rating_min=8.0,
        reference_titles=["黑镜"],
        sort_preference="rating",
    )
    candidates = [
        SmartSearchCandidate(
            source_kind="history",
            source_label="播放记录",
            vod_id="1",
            title="普通喜剧",
            overview="轻松喜剧",
            rating=6.5,
        ),
        SmartSearchCandidate(
            source_kind="following",
            source_label="我的追更",
            vod_id="2",
            title="黑镜",
            overview="近未来科幻寓言",
            genres=["科幻", "悬疑"],
            rating=8.8,
        ),
    ]

    ranked = rank_candidates(candidates, intent)

    assert ranked[0].candidate.vod_id == "2"
    assert ranked[0].score > ranked[1].score
    assert "科幻匹配" in ranked[0].reasons
    assert "评分 8.8" in ranked[0].reasons
    assert "来自我的追更" in ranked[0].reasons


def test_rank_candidates_filters_negative_keywords() -> None:
    intent = SmartSearchIntent(
        query_text="轻松电影不要恐怖",
        keywords=["轻松"],
        negative_keywords=["恐怖"],
    )
    candidates = [
        SmartSearchCandidate(source_kind="favorite", source_label="我的收藏", vod_id="1", title="轻松恐怖片"),
        SmartSearchCandidate(source_kind="favorite", source_label="我的收藏", vod_id="2", title="轻松喜剧"),
    ]

    ranked = rank_candidates(candidates, intent)

    assert [item.candidate.vod_id for item in ranked] == ["2"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_smart_search_ranking.py -q
```

Expected: FAIL because `atv_player.search` does not exist.

- [ ] **Step 3: Implement smart search models**

Create `src/atv_player/search/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from atv_player.models import VodItem


@dataclass(slots=True)
class SmartSearchCandidate:
    source_kind: str
    source_label: str
    vod_id: str
    title: str
    subtitle: str = ""
    poster: str = ""
    remarks: str = ""
    overview: str = ""
    year: str = ""
    area: str = ""
    language: str = ""
    actors: str = ""
    genres: list[str] = field(default_factory=list)
    rating: float = 0.0
    vod_item: VodItem | None = None


@dataclass(slots=True)
class RankedSmartSearchCandidate:
    candidate: SmartSearchCandidate
    score: float
    reasons: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Implement ranking**

Create `src/atv_player/search/ranking.py`:

```python
from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.search.models import RankedSmartSearchCandidate, SmartSearchCandidate


def _haystack(candidate: SmartSearchCandidate) -> str:
    return " ".join(
        [
            candidate.title,
            candidate.subtitle,
            candidate.remarks,
            candidate.overview,
            candidate.year,
            candidate.area,
            candidate.language,
            candidate.actors,
            " ".join(candidate.genres),
        ]
    ).lower()


def _contains_any(text: str, values: list[str]) -> bool:
    return any(str(value or "").strip().lower() in text for value in values if str(value or "").strip())


def rank_candidates(
    candidates: list[SmartSearchCandidate],
    intent: SmartSearchIntent,
) -> list[RankedSmartSearchCandidate]:
    ranked: list[RankedSmartSearchCandidate] = []
    for candidate in candidates:
        text = _haystack(candidate)
        if _contains_any(text, intent.negative_keywords):
            continue
        score = 0.0
        reasons: list[str] = []
        for keyword in intent.keywords:
            normalized = str(keyword or "").strip()
            if normalized and normalized.lower() in text:
                score += 3.0
                reasons.append(f"{normalized}匹配")
        for genre in intent.genres:
            normalized = str(genre or "").strip()
            if normalized and normalized.lower() in text:
                score += 4.0
                reasons.append(f"{normalized}匹配")
        if _contains_any(text, intent.reference_titles):
            score += 5.0
            reasons.append("与参考作品相关")
        if intent.rating_min and candidate.rating >= intent.rating_min:
            score += candidate.rating
            reasons.append(f"评分 {candidate.rating:.1f}")
        elif candidate.rating:
            score += candidate.rating / 3.0
        if candidate.source_label:
            score += 1.0
            reasons.append(f"来自{candidate.source_label}")
        if intent.sort_preference == "rating" and candidate.rating:
            score += candidate.rating / 2.0
        ranked.append(RankedSmartSearchCandidate(candidate=candidate, score=score, reasons=reasons))
    ranked.sort(key=lambda item: (item.score, item.candidate.rating, item.candidate.title), reverse=True)
    return ranked
```

- [ ] **Step 5: Export search module**

Create `src/atv_player/search/__init__.py`:

```python
from atv_player.search.models import RankedSmartSearchCandidate, SmartSearchCandidate
from atv_player.search.ranking import rank_candidates

__all__ = ["RankedSmartSearchCandidate", "SmartSearchCandidate", "rank_candidates"]
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/test_smart_search_ranking.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/search tests/test_smart_search_ranking.py
git commit -m "feat: rank smart search candidates"
```

---

### Task 5: Add Smart Search Controller

**Files:**
- Create: `src/atv_player/search/controller.py`
- Modify: `src/atv_player/search/__init__.py`
- Test: `tests/test_smart_search_controller.py`

- [ ] **Step 1: Write failing controller tests**

Create `tests/test_smart_search_controller.py`:

```python
from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.models import FavoriteCardItem, FavoriteRecord, HistoryRecord, VodItem
from atv_player.search.controller import SmartSearchController


class Parser:
    def __init__(self, intent: SmartSearchIntent | Exception) -> None:
        self.intent = intent

    def parse(self, keyword: str) -> SmartSearchIntent:
        if isinstance(self.intent, Exception):
            raise self.intent
        return self.intent


class Favorites:
    def search_items(self, keyword: str, page: int):
        record = FavoriteRecord(
            source_kind="telegram",
            source_key="",
            source_name="电报影视",
            vod_id="fav-1",
            vod_name_snapshot="黑镜",
            latest_vod_name="黑镜",
            vod_pic="",
            vod_remarks="8.8 科幻",
            title_changed=False,
            created_at=1,
            updated_at=2,
        )
        return [FavoriteCardItem(record=record, display_title="黑镜", source_label="我的收藏")], 1


class EmptyFollowing:
    def search_items(self, keyword: str, page: int):
        return [], 0


class EmptyHistory:
    def load_page(self, page: int, size: int, keyword: str):
        return [], 0


def test_smart_search_controller_returns_ranked_vod_items() -> None:
    controller = SmartSearchController(
        intent_parser=Parser(
            SmartSearchIntent(
                query_text="类似黑镜的高分科幻",
                keywords=["科幻"],
                genres=["科幻"],
                rating_min=8.0,
                sort_preference="rating",
            )
        ),
        favorites_controller=Favorites(),
        following_controller=EmptyFollowing(),
        history_controller=EmptyHistory(),
    )

    items, total = controller.search_items("类似黑镜的高分科幻", 1)

    assert total == 1
    assert items[0].vod_name == "黑镜"
    assert items[0].type_name == "智能匹配"
    assert "来自我的收藏" in items[0].vod_remarks


def test_smart_search_controller_returns_empty_when_parser_fails() -> None:
    controller = SmartSearchController(
        intent_parser=Parser(RuntimeError("boom")),
        favorites_controller=Favorites(),
        following_controller=EmptyFollowing(),
        history_controller=EmptyHistory(),
    )

    items, total = controller.search_items("类似黑镜", 1)

    assert items == []
    assert total == 0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_smart_search_controller.py -q
```

Expected: FAIL because `SmartSearchController` does not exist.

- [ ] **Step 3: Implement controller**

Create `src/atv_player/search/controller.py`:

```python
from __future__ import annotations

import re

from atv_player.models import FavoriteCardItem, HistoryRecord, VodItem
from atv_player.search.models import SmartSearchCandidate
from atv_player.search.ranking import rank_candidates


_RATING_RE = re.compile(r"(?<!\d)([0-9](?:\.[0-9])?|10(?:\.0)?)(?!\d)")


def _rating_from_text(text: str) -> float:
    matches = [float(match.group(1)) for match in _RATING_RE.finditer(str(text or ""))]
    return max(matches) if matches else 0.0


def _vod_from_ranked(candidate: SmartSearchCandidate, reasons: list[str]) -> VodItem:
    if candidate.vod_item is not None:
        item = candidate.vod_item
    else:
        item = VodItem(
            vod_id=candidate.vod_id,
            vod_name=candidate.title,
            vod_pic=candidate.poster,
            vod_remarks=candidate.remarks,
        )
    item.type_name = "智能匹配"
    reason_text = " / ".join(reasons[:3])
    if reason_text:
        item.vod_remarks = reason_text
    return item


class SmartSearchController:
    def __init__(
        self,
        *,
        intent_parser,
        favorites_controller=None,
        following_controller=None,
        history_controller=None,
        page_size: int = 20,
    ) -> None:
        self._intent_parser = intent_parser
        self._favorites_controller = favorites_controller
        self._following_controller = following_controller
        self._history_controller = history_controller
        self._page_size = page_size

    def search_items(self, keyword: str, page: int) -> tuple[list[VodItem], int]:
        try:
            intent = self._intent_parser.parse(keyword)
        except Exception:
            return [], 0
        candidates = self._load_candidates(intent.keywords or [keyword])
        ranked = rank_candidates(candidates, intent)
        start = max(page - 1, 0) * self._page_size
        end = start + self._page_size
        items = [_vod_from_ranked(item.candidate, item.reasons) for item in ranked[start:end]]
        return items, len(ranked)

    def _load_candidates(self, keywords: list[str]) -> list[SmartSearchCandidate]:
        candidates: list[SmartSearchCandidate] = []
        seen: set[tuple[str, str]] = set()
        for keyword in [item for item in keywords if str(item or "").strip()]:
            candidates.extend(self._favorite_candidates(keyword, seen))
            candidates.extend(self._following_candidates(keyword, seen))
            candidates.extend(self._history_candidates(keyword, seen))
        return candidates

    def _favorite_candidates(self, keyword: str, seen: set[tuple[str, str]]) -> list[SmartSearchCandidate]:
        if self._favorites_controller is None or not hasattr(self._favorites_controller, "search_items"):
            return []
        cards, _total = self._favorites_controller.search_items(keyword, 1)
        candidates = []
        for card in cards:
            record = getattr(card, "record", None)
            if record is None:
                continue
            key = ("favorite", record.vod_id)
            if key in seen:
                continue
            seen.add(key)
            remarks = str(record.vod_remarks or "")
            candidates.append(
                SmartSearchCandidate(
                    source_kind="favorite",
                    source_label="我的收藏",
                    vod_id=str(record.vod_id),
                    title=str(card.display_title or record.latest_vod_name or record.vod_name_snapshot),
                    poster=str(record.vod_pic or ""),
                    remarks=remarks,
                    rating=_rating_from_text(remarks),
                )
            )
        return candidates

    def _following_candidates(self, keyword: str, seen: set[tuple[str, str]]) -> list[SmartSearchCandidate]:
        if self._following_controller is None or not hasattr(self._following_controller, "search_items"):
            return []
        cards, _total = self._following_controller.search_items(keyword, 1)
        candidates = []
        for card in cards:
            record = getattr(card, "record", None)
            if record is None:
                continue
            key = ("following", str(record.id))
            if key in seen:
                continue
            seen.add(key)
            text = " ".join([str(getattr(card, "subtitle", "") or ""), str(getattr(card, "update_text", "") or "")])
            candidates.append(
                SmartSearchCandidate(
                    source_kind="following",
                    source_label="我的追更",
                    vod_id=str(record.id),
                    title=str(record.title),
                    poster=str(record.poster or ""),
                    remarks=text,
                    overview=str(record.overview or ""),
                    rating=_rating_from_text(text),
                )
            )
        return candidates

    def _history_candidates(self, keyword: str, seen: set[tuple[str, str]]) -> list[SmartSearchCandidate]:
        if self._history_controller is None or not hasattr(self._history_controller, "load_page"):
            return []
        records, _total = self._history_controller.load_page(page=1, size=self._page_size, keyword=keyword)
        candidates = []
        for record in records:
            if not isinstance(record, HistoryRecord):
                continue
            key = ("history", record.key)
            if key in seen:
                continue
            seen.add(key)
            remarks = str(record.vod_remarks or "")
            candidates.append(
                SmartSearchCandidate(
                    source_kind="history",
                    source_label="播放记录",
                    vod_id=str(record.key),
                    title=str(record.vod_name),
                    poster=str(record.vod_pic or ""),
                    remarks=remarks,
                    rating=_rating_from_text(remarks),
                )
            )
        return candidates
```

- [ ] **Step 4: Export controller**

Update `src/atv_player/search/__init__.py`:

```python
from atv_player.search.controller import SmartSearchController
from atv_player.search.models import RankedSmartSearchCandidate, SmartSearchCandidate
from atv_player.search.ranking import rank_candidates

__all__ = [
    "RankedSmartSearchCandidate",
    "SmartSearchCandidate",
    "SmartSearchController",
    "rank_candidates",
]
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_smart_search_controller.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/search tests/test_smart_search_controller.py
git commit -m "feat: add smart search controller"
```

---

### Task 6: Add AI Settings UI

**Files:**
- Modify: `src/atv_player/ui/advanced_settings_dialog.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing settings UI tests**

Append these tests near the existing `AdvancedSettingsDialog` tests in `tests/test_app.py`:

```python
def test_advanced_settings_dialog_saves_ai_provider_settings(qtbot) -> None:
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    config = AppConfig()
    saved: list[tuple[bool, str, str, str, int]] = []
    dialog = AdvancedSettingsDialog(
        config,
        save_config=lambda: saved.append(
            (
                config.ai_enabled,
                config.ai_base_url,
                config.ai_api_key,
                config.ai_chat_model,
                config.ai_request_timeout_seconds,
            )
        ),
    )
    qtbot.addWidget(dialog)

    dialog.ai_enabled_checkbox.setChecked(True)
    dialog.ai_base_url_edit.setText(" https://api.example.com/v1/ ")
    dialog.ai_api_key_edit.setText(" sk-test ")
    dialog.ai_chat_model_edit.setText(" gpt-4o-mini ")
    dialog.ai_timeout_edit.setText("45")
    dialog._save()

    assert saved == [(True, "https://api.example.com/v1", "sk-test", "gpt-4o-mini", 45)]


def test_advanced_settings_dialog_masks_ai_api_key(qtbot) -> None:
    from PySide6.QtWidgets import QLineEdit
    from atv_player.ui.advanced_settings_dialog import AdvancedSettingsDialog

    dialog = AdvancedSettingsDialog(AppConfig(ai_api_key="sk-test"), save_config=lambda: None)
    qtbot.addWidget(dialog)

    assert dialog.ai_api_key_edit.text() == "sk-test"
    assert dialog.ai_api_key_edit.echoMode() == QLineEdit.EchoMode.Password
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_app.py -k "advanced_settings_dialog_saves_ai_provider_settings or advanced_settings_dialog_masks_ai_api_key" -q
```

Expected: FAIL because the dialog has no AI widgets.

- [ ] **Step 3: Add AI widgets**

In `AdvancedSettingsDialog.__init__`, create widgets after the metadata tab fields:

```python
        self.ai_tab = QWidget()
        self.ai_group = QGroupBox("AI 智能功能")
        self.ai_enabled_checkbox = QCheckBox("启用智能搜索")
        self.ai_base_url_edit = QLineEdit()
        self.ai_base_url_edit.setPlaceholderText("例如 https://api.openai.com/v1")
        self.ai_api_key_edit = QLineEdit()
        self.ai_api_key_edit.setPlaceholderText("填写 API Key")
        self.ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_chat_model_edit = QLineEdit()
        self.ai_chat_model_edit.setPlaceholderText("例如 gpt-4o-mini")
        self.ai_timeout_edit = QLineEdit()
        self.ai_timeout_edit.setPlaceholderText("5 - 120")
        self.ai_privacy_label = QLabel("启用后，搜索文本会发送到你配置的 AI 服务商；媒体库、播放历史、收藏列表和 API Key 不会随搜索请求发送。")
        self.ai_privacy_label.setWordWrap(True)
```

Set initial values:

```python
        self.ai_enabled_checkbox.setChecked(config.ai_enabled)
        self.ai_base_url_edit.setText(config.ai_base_url)
        self.ai_api_key_edit.setText(config.ai_api_key)
        self.ai_chat_model_edit.setText(config.ai_chat_model)
        self.ai_timeout_edit.setText(str(config.ai_request_timeout_seconds))
```

Add layout before the network proxy tab layout:

```python
        ai_layout = QFormLayout()
        ai_layout.addRow(self.ai_enabled_checkbox)
        ai_layout.addRow("API 地址", self.ai_base_url_edit)
        ai_layout.addRow("API Key", self.ai_api_key_edit)
        ai_layout.addRow("Chat 模型", self.ai_chat_model_edit)
        ai_layout.addRow("请求超时", self.ai_timeout_edit)
        ai_layout.addRow("隐私", self.ai_privacy_label)
        self.ai_group.setLayout(ai_layout)
        ai_tab_layout = QVBoxLayout(self.ai_tab)
        ai_tab_layout.addWidget(self.ai_group)
        ai_tab_layout.addStretch(1)
```

Register the tab after `"元数据"`:

```python
        self.settings_tabs.addTab(self.ai_tab, "AI")
```

- [ ] **Step 4: Theme and validation**

In `_apply_theme()`, add the AI edits to the styled line edits tuple:

```python
            self.ai_base_url_edit,
            self.ai_api_key_edit,
            self.ai_chat_model_edit,
            self.ai_timeout_edit,
```

Add validation helper:

```python
    def _validated_ai_values(self) -> tuple[bool, str, str, str, int] | None:
        enabled = self.ai_enabled_checkbox.isChecked()
        base_url = self.ai_base_url_edit.text().strip().rstrip("/")
        api_key = self.ai_api_key_edit.text().strip()
        model = self.ai_chat_model_edit.text().strip()
        try:
            timeout = int(self.ai_timeout_edit.text().strip() or "30")
        except ValueError:
            QMessageBox.warning(self, "AI 请求超时无效", "AI 请求超时必须是整数")
            return None
        if timeout < 5 or timeout > 120:
            QMessageBox.warning(self, "AI 请求超时无效", "AI 请求超时必须在 5 到 120 秒之间")
            return None
        if enabled and not base_url:
            QMessageBox.warning(self, "AI API 地址无效", "启用智能搜索需要填写 API 地址")
            return None
        if enabled and not api_key:
            QMessageBox.warning(self, "AI API Key 无效", "启用智能搜索需要填写 API Key")
            return None
        if enabled and not model:
            QMessageBox.warning(self, "AI Chat 模型无效", "启用智能搜索需要填写 Chat 模型")
            return None
        return enabled, base_url, api_key, model, timeout
```

In `_save()`, validate and persist before `self._save_config()`:

```python
        ai_values = self._validated_ai_values()
        if ai_values is None:
            return
```

```python
        (
            self._config.ai_enabled,
            self._config.ai_base_url,
            self._config.ai_api_key,
            self._config.ai_chat_model,
            self._config.ai_request_timeout_seconds,
        ) = ai_values
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_app.py -k "advanced_settings_dialog_saves_ai_provider_settings or advanced_settings_dialog_masks_ai_api_key" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/ui/advanced_settings_dialog.py tests/test_app.py
git commit -m "feat: add ai provider settings ui"
```

---

### Task 7: Wire Smart Search Into App and Global Search

**Files:**
- Modify: `src/atv_player/app.py`
- Modify: `src/atv_player/ui/main_window.py`
- Test: `tests/test_main_window_ui.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing MainWindow smart tab test**

Append to `tests/test_main_window_ui.py` near global search tests:

```python
class SmartSearchGlobalController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search_items(self, keyword: str, page: int):
        self.calls.append((keyword, page))
        return [VodItem(vod_id="smart-1", vod_name="黑镜", vod_remarks="科幻匹配")], 1


def test_global_search_includes_smart_match_tab_when_controller_present(qtbot) -> None:
    smart_controller = SmartSearchGlobalController()
    window = MainWindow(
        browse_controller=FakeStaticController(),
        history_controller=DummyHistoryController(),
        player_controller=FakePlayerController(),
        telegram_controller=SearchableController(),
        smart_search_controller=smart_controller,
        config=AppConfig(),
        save_config=lambda: None,
    )
    qtbot.addWidget(window)
    window.show()

    window.global_search_edit.setText("类似黑镜的高分科幻")
    window._start_global_search()

    qtbot.waitUntil(lambda: smart_controller.calls == [("类似黑镜的高分科幻", 1)], timeout=1000)
    qtbot.waitUntil(lambda: any(window.nav_tabs.tabText(i) == "智能匹配(1)" for i in range(window.nav_tabs.count())), timeout=1000)
```

- [ ] **Step 2: Run MainWindow test to verify failure**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_includes_smart_match_tab_when_controller_present" -q
```

Expected: FAIL because `MainWindow.__init__` has no `smart_search_controller` argument.

- [ ] **Step 3: Add MainWindow wiring**

In `MainWindow.__init__`, add argument before `metadata_hydrator_factory`:

```python
            smart_search_controller=None,
```

Store it:

```python
        self._smart_search_controller = smart_search_controller
```

After the `pansou` global-search-only tab registration and before history global-search registration, add:

```python
        if self._smart_search_controller is not None:
            self._static_tab_definitions.append(
                _TabDefinition(
                    "smart:search",
                    "智能匹配",
                    PosterGridPage(
                        self._smart_search_controller,
                        click_action="open",
                        search_enabled=False,
                    ),
                    self._smart_search_controller,
                    global_search_only=True,
                )
            )
```

Do not connect item open for this first tab. Smart results are discovery results; users can right-click or copy title through existing result context only after a later task adds deep source routing.

- [ ] **Step 4: Write failing AppCoordinator injection test**

Append to `tests/test_app.py`:

```python
def test_app_coordinator_injects_smart_search_controller_when_ai_enabled(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class CapturingMainWindow:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

        def show(self) -> None:
            pass

    monkeypatch.setattr(app_module, "MainWindow", CapturingMainWindow)
    repo = app_module.SettingsRepository(tmp_path / "app.db")
    repo.save_config(
        AppConfig(
            token="token",
            ai_enabled=True,
            ai_base_url="https://api.example.com/v1",
            ai_api_key="sk-test",
            ai_chat_model="model-a",
        )
    )
    coordinator = app_module.AppCoordinator(repo)

    coordinator._show_main()

    assert captured["smart_search_controller"] is not None
```

- [ ] **Step 5: Implement AppCoordinator builder**

In `src/atv_player/app.py`, import AI/search classes:

```python
from atv_player.ai import AIProviderConfig, OpenAICompatibleClient, SmartSearchIntentParser
from atv_player.search import SmartSearchController
```

Add a method to `AppCoordinator`:

```python
    def _build_smart_search_controller(
        self,
        config: AppConfig,
        *,
        favorites_controller=None,
        following_controller=None,
        history_controller=None,
    ):
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
        client = OpenAICompatibleClient(provider_config)
        parser = SmartSearchIntentParser(client)
        return SmartSearchController(
            intent_parser=parser,
            favorites_controller=favorites_controller,
            following_controller=following_controller,
            history_controller=history_controller,
        )
```

In `_show_main()`, after the existing controllers are created and before `MainWindow(...)`, assign:

```python
        smart_search_controller = self._build_smart_search_controller(
            config,
            favorites_controller=favorites_controller,
            following_controller=following_controller,
            history_controller=history_controller,
        )
```

Pass it into `MainWindow(...)`:

```python
            smart_search_controller=smart_search_controller,
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/test_main_window_ui.py -k "global_search_includes_smart_match_tab_when_controller_present" tests/test_app.py -k "app_coordinator_injects_smart_search_controller_when_ai_enabled" -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atv_player/app.py src/atv_player/ui/main_window.py tests/test_app.py tests/test_main_window_ui.py
git commit -m "feat: wire smart search into global search"
```

---

### Task 8: Final Verification

**Files:**
- Test: all files touched in this plan

- [ ] **Step 1: Run focused unit and UI tests**

Run:

```bash
uv run pytest \
  tests/test_ai_openai_compatible.py \
  tests/test_ai_search_intent.py \
  tests/test_smart_search_ranking.py \
  tests/test_smart_search_controller.py \
  tests/test_storage.py -k "ai_provider_config or ai_settings" \
  tests/test_app.py -k "advanced_settings_dialog_saves_ai_provider_settings or advanced_settings_dialog_masks_ai_api_key or app_coordinator_injects_smart_search_controller_when_ai_enabled" \
  tests/test_main_window_ui.py -k "global_search_includes_smart_match_tab_when_controller_present" \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run static checks**

Run:

```bash
uv run ruff check src/atv_player/ai src/atv_player/search src/atv_player/models.py src/atv_player/storage.py src/atv_player/app.py src/atv_player/ui/advanced_settings_dialog.py src/atv_player/ui/main_window.py tests/test_ai_openai_compatible.py tests/test_ai_search_intent.py tests/test_smart_search_ranking.py tests/test_smart_search_controller.py
```

Expected: PASS.

Run:

```bash
npx --yes pyright src/atv_player/ai src/atv_player/search
```

Expected: PASS.

- [ ] **Step 3: Run broader regression around touched surfaces**

Run:

```bash
uv run pytest tests/test_storage.py tests/test_app.py tests/test_main_window_ui.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit any verification fixes**

If verification required fixes, commit only those touched files:

```bash
git add src/atv_player tests
git commit -m "fix: stabilize smart search integration"
```
