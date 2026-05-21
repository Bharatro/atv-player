# YouTube Max Quality Cap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global playback setting that caps YouTube's default resolved quality without changing in-player manual downswitch behavior.

**Architecture:** Store a `youtube_max_height` integer in `AppConfig` and SQLite settings, expose it in the advanced playback settings dialog, and let `YtdlpService` use it when callers do not provide an explicit `max_height`. Keep `0` as the unlimited sentinel.

**Tech Stack:** Python, PySide6, SQLite, pytest

---

### Task 1: Add failing tests for config persistence and default yt-dlp cap

**Files:**
- Modify: `tests/test_app.py`
- Modify: `tests/test_yt_dlp_service.py`
- Modify: `tests/test_storage.py` or existing storage-focused coverage in `tests/test_app.py` if storage tests already live there

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

```python
config = AppConfig(youtube_max_height=1080)
assert config.youtube_max_height == 1080
```

```python
dialog.youtube_max_height_combo.setCurrentIndex(dialog.youtube_max_height_combo.findData(1080))
dialog._save()
assert config.youtube_max_height == 1080
```

```python
repo.save_config(AppConfig(youtube_max_height=720))
assert repo.load_config().youtube_max_height == 720
```

```python
service = YtdlpService(config_loader=lambda: AppConfig(youtube_max_height=1080))
service.resolve("https://www.youtube.com/watch?v=test")
assert captured_max_height == 1080
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py tests/test_yt_dlp_service.py -k "youtube_max_height or default_max_height" -q`

Expected: FAIL with missing field / missing UI control / wrong default `max_height`

- [ ] **Step 3: Write minimal implementation**

Implement only the new config field, dialog control, storage wiring, and yt-dlp default cap behavior needed by the tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py tests/test_yt_dlp_service.py -k "youtube_max_height or default_max_height" -q`

Expected: PASS

- [ ] **Step 5: Run a small regression slice**

Run: `uv run pytest tests/test_app.py tests/test_yt_dlp_service.py -k "advanced_settings or ytdlp" -q`

Expected: PASS
