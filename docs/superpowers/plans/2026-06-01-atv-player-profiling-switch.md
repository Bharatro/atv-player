# ATV Player Profiling Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in environment-variable profiling mode for the desktop app so startup and runtime hotspots can be captured without changing the normal launch path.

**Architecture:** Keep the change isolated to `src/atv_player/main.py` with a small helper that wraps either initialization only or the full Qt event loop in `cProfile`. Expose output path and mode through environment variables so the profiling behavior stays external to the application config and can be toggled from the shell.

**Tech Stack:** Python 3.12, `cProfile`, `pstats`, PySide6, pytest

---

### Task 1: Add profiling mode coverage

**Files:**
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_writes_profile_output_when_atv_profile_is_enabled(monkeypatch, tmp_path) -> None:
    profile_output = tmp_path / "profile.prof"
    monkeypatch.setenv("ATV_PROFILE", "runtime")
    monkeypatch.setenv("ATV_PROFILE_OUTPUT", str(profile_output))
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -q`
Expected: FAIL because `ATV_PROFILE` is not handled yet.

- [ ] **Step 3: Write minimal implementation**

No code in this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -q`
Expected: PASS after the profiling hook exists.

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py src/atv_player/main.py docs/superpowers/plans/2026-06-01-atv-player-profiling-switch.md
git commit -m "feat: add app profiling switch"
```

### Task 2: Implement profiling wrapper

**Files:**
- Modify: `src/atv_player/main.py`

- [ ] **Step 1: Write the failing test**

Covered by Task 1.

- [ ] **Step 2: Run test to verify it fails**

Covered by Task 1.

- [ ] **Step 3: Write minimal implementation**

Add a helper that:

```python
import cProfile
import os
from pathlib import Path
import pstats

def _profile_output_path() -> Path:
    ...

def _run_with_optional_profiling(mode: str | None, runner: Callable[[], int]) -> int:
    ...
```

`startup` should profile only `build_application()` plus window setup. `runtime` should profile the whole app execution. The helper should dump stats to `ATV_PROFILE_OUTPUT` or `atv-player-profile.prof` in the current working directory.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/main.py
git commit -m "feat: add optional cprofile support"
```

### Task 3: Verify command-line usage

**Files:**
- None

- [ ] **Step 1: Write the failing test**

No new test needed.

- [ ] **Step 2: Run test to verify it fails**

N/A

- [ ] **Step 3: Write minimal implementation**

Document the shell usage in the final response:

```bash
ATV_PROFILE=runtime ATV_PROFILE_OUTPUT=profile.prof uv run atv-player
```

- [ ] **Step 4: Run test to verify it passes**

Run the targeted test file and confirm the app still starts without the env vars.

- [ ] **Step 5: Commit**

No extra commit required.
