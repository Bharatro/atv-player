# Danmaku Provider Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make segmented danmaku downloads use a fixed concurrency of `4` across Tencent, IQiyi, MGTV, Youku, and Bilibili without changing resolve APIs or result ordering.

**Architecture:** Add one small shared helper in `src/atv_player/danmaku/providers/` that runs blocking segment fetch functions with bounded parallelism and ordered result collection. Update each segmented provider to route only its segment-download phase through that helper while preserving each provider's existing parsing and failure semantics.

**Tech Stack:** Python, `concurrent.futures.ThreadPoolExecutor`, `pytest`, `httpx`

---

### Task 1: Add shared bounded-concurrency helper

**Files:**
- Create: `src/atv_player/danmaku/providers/_concurrency.py`

- [ ] **Step 1: Write the helper**

```python
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_ordered_bounded(items: Iterable[T], worker: Callable[[T], R], *, max_workers: int = 4) -> list[R]:
    rows = list(items)
    if not rows:
        return []
    worker_count = max(1, min(max_workers, len(rows)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(worker, row) for row in rows]
        return [future.result() for future in futures]
```

- [ ] **Step 2: No dedicated test for helper**
Helper behavior is verified through provider-level concurrency tests below.

### Task 2: Convert segmented providers to `4` concurrent downloads

**Files:**
- Modify: `src/atv_player/danmaku/providers/tencent.py`
- Modify: `src/atv_player/danmaku/providers/iqiyi.py`
- Modify: `src/atv_player/danmaku/providers/mgtv.py`
- Modify: `src/atv_player/danmaku/providers/youku.py`
- Modify: `src/atv_player/danmaku/providers/bilibili.py`

- [ ] **Step 1: Replace serial segment loops**

```python
segment_payloads = run_ordered_bounded(segment_urls, fetch_segment, max_workers=4)
```

Use provider-specific worker functions so each provider keeps its existing parse and error behavior.

- [ ] **Step 2: Preserve ordering and semantics**
Tencent and IQiyi should continue to sort/finalize records exactly as before. MGTV should still propagate hard segment failures. Youku should still tolerate `httpx.HTTPError` per segment but continue to raise on full failure or response parse errors.

### Task 3: Add provider concurrency regression tests

**Files:**
- Modify: `tests/test_danmaku_tencent_provider.py`
- Modify: `tests/test_danmaku_iqiyi_provider.py`
- Modify: `tests/test_danmaku_mgtv_provider.py`
- Modify: `tests/test_danmaku_youku_provider.py`
- Modify: `tests/test_danmaku_bilibili_provider.py`

- [ ] **Step 1: Write failing tests**
Add one test per provider that:
- drives at least `6` segment requests
- tracks in-flight segment fetches with a lock
- sleeps briefly inside each segment request
- asserts `max_active == 4`

- [ ] **Step 2: Run focused provider tests**

Run:
`uv run pytest tests/test_danmaku_tencent_provider.py tests/test_danmaku_iqiyi_provider.py tests/test_danmaku_mgtv_provider.py tests/test_danmaku_youku_provider.py -k "concurrency" -v`

Expected: Fail before implementation, pass after implementation.

### Task 4: Run relevant resolve regressions

**Files:**
- Test only

- [ ] **Step 1: Run focused resolve suite**

Run:
`uv run pytest tests/test_danmaku_tencent_provider.py tests/test_danmaku_iqiyi_provider.py tests/test_danmaku_mgtv_provider.py tests/test_danmaku_youku_provider.py -k "resolve" -v`

Expected: Existing resolve behaviors still pass alongside new concurrency tests.
