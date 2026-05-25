# Douban Official Rate Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip official Douban scraping immediately when another official Douban request was allowed less than 10 seconds ago.

**Architecture:** Add a process-wide nonblocking limiter inside `LocalDoubanClient` so every official Douban search/detail HTTP request goes through the same gate. Represent skipped attempts with `DoubanRateLimitedError`, a subclass of `DoubanBlockedError`, preserving existing provider fallback behavior.

**Tech Stack:** Python, httpx, pytest, existing metadata provider architecture.

---

## File Structure

- Modify `src/atv_player/metadata/providers/local_douban_client.py`: define `DoubanRateLimitedError`, add a small process-wide limiter, inject a monotonic clock for deterministic tests, and call the limiter before HTTP.
- Modify `tests/test_local_douban_client.py`: add tests for nonblocking skip behavior and no real waiting.

### Task 1: Add Tests For Nonblocking Official Douban Rate Limit

**Files:**
- Modify: `tests/test_local_douban_client.py`

- [ ] **Step 1: Write the failing tests**

Add imports and two tests:

```python
from atv_player.metadata.providers.local_douban_client import (
    DoubanBlockedError,
    DoubanRateLimitedError,
    LocalDoubanClient,
)


def test_local_douban_client_skips_second_request_inside_rate_limit_window() -> None:
    now = 100.0
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="[]")

    client = LocalDoubanClient(
        transport=httpx.MockTransport(handler),
        monotonic=lambda: now,
    )

    assert client.search("深空彼岸") == []

    with pytest.raises(DoubanRateLimitedError):
        client.search("深空彼岸")

    assert len(calls) == 1


def test_local_douban_client_allows_request_after_rate_limit_window() -> None:
    now = 100.0
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="[]")

    client = LocalDoubanClient(
        transport=httpx.MockTransport(handler),
        monotonic=lambda: now,
    )

    client.search("深空彼岸")
    now = 110.0
    client.search("深空彼岸")

    assert len(calls) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_local_douban_client.py -q`

Expected: FAIL because `DoubanRateLimitedError` and `monotonic` injection do not exist yet.

### Task 2: Implement The Nonblocking Limiter

**Files:**
- Modify: `src/atv_player/metadata/providers/local_douban_client.py`
- Test: `tests/test_local_douban_client.py`

- [ ] **Step 1: Add the error and limiter state**

Add `time`, `Lock`, and the new exception/fields:

```python
from threading import Lock
import time


class DoubanRateLimitedError(DoubanBlockedError):
    pass


class LocalDoubanClient:
    _RATE_LIMIT_SECONDS = 10.0
    _rate_limit_lock = Lock()
    _last_allowed_at: float | None = None
```

- [ ] **Step 2: Inject the clock and enforce the gate**

Extend `__init__` and add `_ensure_rate_limit_available()`:

```python
def __init__(
    self,
    cookie: str = "",
    transport: httpx.BaseTransport | None = None,
    proxy_decider: ProxyDecider | None = None,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    self._cookie = cookie.strip()
    self._monotonic = monotonic
    ...

def _ensure_rate_limit_available(self, url: str) -> None:
    now = self._monotonic()
    with self._rate_limit_lock:
        if (
            self._last_allowed_at is not None
            and now - self._last_allowed_at < self._RATE_LIMIT_SECONDS
        ):
            raise DoubanRateLimitedError(f"豆瓣官方请求过于频繁: {url}")
        type(self)._last_allowed_at = now
```

Call it first in `_get_text()`:

```python
def _get_text(self, url: str, params: dict[str, object] | None = None) -> str:
    self._ensure_rate_limit_available(url)
    response = self._client.get(url, params=params, headers=self._headers())
```

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest tests/test_local_douban_client.py -q`

Expected: PASS.

### Task 3: Verify Provider Compatibility

**Files:**
- Test: `tests/test_metadata_douban_source_providers.py`
- Test: `tests/test_metadata_douban_provider.py`

- [ ] **Step 1: Run official and legacy Douban provider tests**

Run:

```bash
uv run pytest tests/test_local_douban_client.py tests/test_metadata_douban_source_providers.py tests/test_metadata_douban_provider.py -q
```

Expected: PASS because `DoubanRateLimitedError` subclasses `DoubanBlockedError`, so existing provider error handling remains valid.

