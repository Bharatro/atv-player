# AI Call Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log every OpenAI-compatible AI HTTP call through the existing application logging system without recording prompts, responses, API keys, or local paths.

**Architecture:** Add logging at `OpenAICompatibleClient`, the shared HTTP boundary for AI chat completions, model listing, and connectivity checks. Use standard Python logging with `log_category="ai"` and `log_source="app"` so existing `StructuredJsonlHandler` persists the records.

**Tech Stack:** Python 3, `httpx`, standard `logging`, `pytest` `caplog`, existing `AIProviderConfig` and `OpenAICompatibleClient`.

---

## File Structure

- Modify `src/atv_player/ai/openai_compatible.py`: add module logger, sanitized endpoint summaries, elapsed-time logging, and structured log extras for chat completion and model list calls.
- Modify `tests/test_ai_openai_compatible.py`: add focused logging tests using `caplog`; do not write JSONL files because `StructuredJsonlHandler` persistence is already tested in `tests/test_log_store.py`.

### Task 1: Chat Completion Success Logs

**Files:**
- Modify: `tests/test_ai_openai_compatible.py`
- Modify: `src/atv_player/ai/openai_compatible.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_chat_completion_logs_success_without_prompt_or_api_key(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "secret-response"}}]})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://user:pass@api.example.com/v1?token=secret-query",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("INFO", logger="atv_player.ai.openai_compatible"):
        client.chat_completion(messages=[{"role": "user", "content": "secret prompt"}])

    messages = [record.getMessage() for record in caplog.records]
    joined = "\n".join(messages)
    assert "AI chat_completion request started" in joined
    assert "AI chat_completion request succeeded" in joined
    assert "model-a" in joined
    assert "api.example.com/v1" in joined
    assert "status=200" in joined
    assert "elapsed_ms=" in joined
    assert "secret prompt" not in joined
    assert "secret-response" not in joined
    assert "sk-test" not in joined
    assert "user:pass" not in joined
    assert "secret-query" not in joined
    for record in caplog.records:
        assert getattr(record, "log_category", "") == "ai"
        assert getattr(record, "log_source", "") == "app"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_success_without_prompt_or_api_key -v`

Expected: FAIL because no AI logging is emitted yet.

- [ ] **Step 3: Implement minimal success logging**

In `src/atv_player/ai/openai_compatible.py`, add imports and helpers near the top:

```python
import logging
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
_LOG_EXTRA = {"log_category": "ai", "log_source": "app"}
```

Add helper functions after `_sanitize_message`:

```python
def _endpoint_summary(url: str) -> str:
    parsed = urlsplit(str(url or ""))
    if not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    return f"{parsed.hostname or parsed.netloc}{path}"


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))
```

Update `chat_completion()` so it logs before and after the POST:

```python
        completion_url = _completion_url(self._config.base_url)
        endpoint = _endpoint_summary(completion_url)
        logger.info(
            "AI chat_completion request started model=%s endpoint=%s",
            payload["model"],
            endpoint,
            extra=_LOG_EXTRA,
        )
        started_at = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    completion_url,
                    headers={"Authorization": f"Bearer {self._config.api_key.strip()}"},
                    json=payload,
                )
                response.raise_for_status()
            logger.info(
                "AI chat_completion request succeeded model=%s endpoint=%s status=%s elapsed_ms=%s",
                payload["model"],
                endpoint,
                response.status_code,
                _elapsed_ms(started_at),
                extra=_LOG_EXTRA,
            )
```

Keep the existing `except` blocks unchanged for now; failure logging is added in Task 2.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_success_without_prompt_or_api_key -v`

Expected: PASS.

- [ ] **Step 5: Run existing OpenAI-compatible tests**

Run: `uv run pytest tests/test_ai_openai_compatible.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_ai_openai_compatible.py src/atv_player/ai/openai_compatible.py
git commit -m "feat: log successful ai chat completions"
```

### Task 2: Chat Completion Failure Logs

**Files:**
- Modify: `tests/test_ai_openai_compatible.py`
- Modify: `src/atv_player/ai/openai_compatible.py`

- [ ] **Step 1: Write the failing HTTP status test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_chat_completion_logs_http_failure_without_api_key(caplog) -> None:
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

    with caplog.at_level("WARNING", logger="atv_player.ai.openai_compatible"):
        with pytest.raises(OpenAICompatibleError):
            client.chat_completion(messages=[{"role": "user", "content": "secret prompt"}])

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI chat_completion request failed" in joined
    assert "status=401" in joined
    assert "elapsed_ms=" in joined
    assert "[redacted]" in joined
    assert "sk-test" not in joined
    assert "secret prompt" not in joined
    for record in caplog.records:
        assert getattr(record, "log_category", "") == "ai"
        assert getattr(record, "log_source", "") == "app"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_http_failure_without_api_key -v`

Expected: FAIL because the HTTP failure path does not emit warning logs yet.

- [ ] **Step 3: Implement HTTP failure logging**

Update the `httpx.HTTPStatusError` block in `chat_completion()`:

```python
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, self._config.api_key)
            logger.warning(
                "AI chat_completion request failed model=%s endpoint=%s status=%s elapsed_ms=%s error=%s",
                payload["model"],
                endpoint,
                exc.response.status_code,
                _elapsed_ms(started_at),
                body,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(
                f"AI API 请求失败: HTTP {exc.response.status_code} {body}"
            ) from exc
```

- [ ] **Step 4: Run HTTP status test**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_http_failure_without_api_key -v`

Expected: PASS.

- [ ] **Step 5: Write the failing transport error test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_chat_completion_logs_transport_failure_without_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot connect with sk-test")

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("WARNING", logger="atv_player.ai.openai_compatible"):
        with pytest.raises(OpenAICompatibleError):
            client.chat_completion(messages=[{"role": "user", "content": "secret prompt"}])

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI chat_completion request failed" in joined
    assert "status=" in joined
    assert "elapsed_ms=" in joined
    assert "[redacted]" in joined
    assert "sk-test" not in joined
    assert "secret prompt" not in joined
```

- [ ] **Step 6: Run transport test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_transport_failure_without_api_key -v`

Expected: FAIL because the transport error path does not emit warning logs yet.

- [ ] **Step 7: Implement transport failure logging**

Update the `httpx.HTTPError` block in `chat_completion()`:

```python
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), self._config.api_key)
            logger.warning(
                "AI chat_completion request failed model=%s endpoint=%s status= elapsed_ms=%s error=%s",
                payload["model"],
                endpoint,
                _elapsed_ms(started_at),
                message,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(f"AI API 请求失败: {message}") from exc
```

- [ ] **Step 8: Run focused failure tests**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_chat_completion_logs_http_failure_without_api_key tests/test_ai_openai_compatible.py::test_chat_completion_logs_transport_failure_without_api_key -v`

Expected: both tests PASS.

- [ ] **Step 9: Run existing OpenAI-compatible tests**

Run: `uv run pytest tests/test_ai_openai_compatible.py -q`

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add tests/test_ai_openai_compatible.py src/atv_player/ai/openai_compatible.py
git commit -m "feat: log failed ai chat completions"
```

### Task 3: Model List Logs

**Files:**
- Modify: `tests/test_ai_openai_compatible.py`
- Modify: `src/atv_player/ai/openai_compatible.py`

- [ ] **Step 1: Write the failing list models success test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_list_models_logs_success_without_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("INFO", logger="atv_player.ai.openai_compatible"):
        assert client.list_models() == ["model-a"]

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI list_models request started" in joined
    assert "AI list_models request succeeded" in joined
    assert "api.example.com/v1/models" in joined
    assert "status=200" in joined
    assert "elapsed_ms=" in joined
    assert "sk-test" not in joined
    for record in caplog.records:
        assert getattr(record, "log_category", "") == "ai"
        assert getattr(record, "log_source", "") == "app"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_success_without_api_key -v`

Expected: FAIL because `list_models()` does not emit AI logs yet.

- [ ] **Step 3: Implement list model success logging**

Update `list_models()` in `src/atv_player/ai/openai_compatible.py`:

```python
        models_url = _models_url(base_url)
        endpoint = _endpoint_summary(models_url)
        logger.info(
            "AI list_models request started endpoint=%s",
            endpoint,
            extra=_LOG_EXTRA,
        )
        started_at = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            logger.info(
                "AI list_models request succeeded endpoint=%s status=%s elapsed_ms=%s",
                endpoint,
                response.status_code,
                _elapsed_ms(started_at),
                extra=_LOG_EXTRA,
            )
```

Keep the existing `except` blocks unchanged for this step, but make sure the request uses `models_url` instead of repeating `_models_url(base_url)`:

```python
                response = client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
```

- [ ] **Step 4: Run list models success test**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_success_without_api_key -v`

Expected: PASS.

- [ ] **Step 5: Write the failing list models HTTP failure test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_list_models_logs_failure_without_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "forbidden sk-test"}})

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("WARNING", logger="atv_player.ai.openai_compatible"):
        with pytest.raises(OpenAICompatibleError):
            client.list_models()

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI list_models request failed" in joined
    assert "status=403" in joined
    assert "elapsed_ms=" in joined
    assert "[redacted]" in joined
    assert "sk-test" not in joined
```

- [ ] **Step 6: Run list models failure test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_failure_without_api_key -v`

Expected: FAIL because the `list_models()` HTTP failure path does not emit warning logs yet.

- [ ] **Step 7: Implement list models HTTP status failure logging**

Update the `httpx.HTTPStatusError` block in `list_models()`:

```python
        except httpx.HTTPStatusError as exc:
            body = _sanitize_message(exc.response.text, api_key)
            logger.warning(
                "AI list_models request failed endpoint=%s status=%s elapsed_ms=%s error=%s",
                endpoint,
                exc.response.status_code,
                _elapsed_ms(started_at),
                body,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(
                f"AI 模型列表请求失败: HTTP {exc.response.status_code} {body}"
            ) from exc
```

Keep the existing `httpx.HTTPError` block unchanged in this step.

- [ ] **Step 8: Run list models HTTP failure test**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_failure_without_api_key -v`

Expected: PASS.

- [ ] **Step 9: Write the failing list models transport failure test**

Add this test to `tests/test_ai_openai_compatible.py`:

```python
def test_list_models_logs_transport_failure_without_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot list models with sk-test")

    client = OpenAICompatibleClient(
        AIProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            chat_model="model-a",
        ),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("WARNING", logger="atv_player.ai.openai_compatible"):
        with pytest.raises(OpenAICompatibleError):
            client.list_models()

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI list_models request failed" in joined
    assert "status=" in joined
    assert "elapsed_ms=" in joined
    assert "[redacted]" in joined
    assert "sk-test" not in joined
```

- [ ] **Step 10: Run list models transport failure test to verify it fails**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_transport_failure_without_api_key -v`

Expected: FAIL because the `list_models()` transport failure path does not emit warning logs yet.

- [ ] **Step 11: Implement list models transport failure logging**

Update the `httpx.HTTPError` block in `list_models()`:

```python
        except httpx.HTTPError as exc:
            message = _sanitize_message(str(exc), api_key)
            logger.warning(
                "AI list_models request failed endpoint=%s status= elapsed_ms=%s error=%s",
                endpoint,
                _elapsed_ms(started_at),
                message,
                extra=_LOG_EXTRA,
            )
            raise OpenAICompatibleError(f"AI 模型列表请求失败: {message}") from exc
```

- [ ] **Step 12: Run list models transport failure test**

Run: `uv run pytest tests/test_ai_openai_compatible.py::test_list_models_logs_transport_failure_without_api_key -v`

Expected: PASS.

- [ ] **Step 13: Run OpenAI-compatible test file**

Run: `uv run pytest tests/test_ai_openai_compatible.py -q`

Expected: all tests pass.

- [ ] **Step 14: Commit**

```bash
git add tests/test_ai_openai_compatible.py src/atv_player/ai/openai_compatible.py
git commit -m "feat: log ai model list requests"
```

### Task 4: Final Verification

**Files:**
- No new code files unless verification exposes a defect.

- [ ] **Step 1: Run AI-focused test suite**

Run: `uv run pytest tests/test_ai_openai_compatible.py tests/test_ai_enrichment.py tests/test_ai_search_intent.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run logging tests**

Run: `uv run pytest tests/test_logging_utils.py tests/test_log_store.py -q`

Expected: all tests pass.

- [ ] **Step 3: Check worktree**

Run: `git status --short`

Expected: no uncommitted changes except files intentionally left by the user.

- [ ] **Step 4: Commit any verification fixes**

If Step 1 or Step 2 required code fixes, commit them:

```bash
git add tests/test_ai_openai_compatible.py src/atv_player/ai/openai_compatible.py
git commit -m "fix: stabilize ai call logging"
```

If no fixes were required, do not create an empty commit.
