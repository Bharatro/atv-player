# NetEase YRC Karaoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add host-side `netease-yrc` parsing so spider plugin karaoke payloads generate usable `ASS` subtitles instead of falling back as unsupported.

**Architecture:** Extend the existing parser dispatch in `src/atv_player/karaoke/parser.py` with one focused NetEase YRC parser that normalizes absolute per-word timing into the current `KaraokeDocument` model. Keep the controller and `ASS` renderer unchanged, and prove the behavior through parser-level tests plus one spider controller integration test.

**Tech Stack:** Python, pytest, existing karaoke normalization/rendering code in `src/atv_player/karaoke`, spider controller subtitle cache flow

---

### Task 1: Add Failing Parser Coverage For NetEase YRC

**Files:**
- Modify: `tests/test_karaoke_parser.py`
- Read: `src/atv_player/karaoke/parser.py`

- [ ] **Step 1: Write the failing happy-path parser test**

```python
def test_parse_netease_yrc_normalizes_absolute_word_timing_and_preserves_spaces() -> None:
    document = parse_raw_karaoke(
        "netease-yrc",
        """[20100,4770](20100,470,0)音(20570,270,0)乐(20840,460,0)停(21300,280,0)止(21580,1090,0)了 (22670,330,0)引(23000,260,0)擎(23260,530,0)熄(23790,350,0)火(24140,730,0)了""",
    )

    assert document.source_format == "netease-yrc"
    assert document.lines[0].start_ms == 20100
    assert document.lines[0].end_ms == 24870
    assert document.lines[0].text == "音乐停止了 引擎熄火了"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("音", 20100, 20570),
        ("乐", 20570, 20840),
        ("停", 20840, 21300),
        ("止", 21300, 21580),
        ("了 ", 21580, 22670),
        ("引", 22670, 23000),
        ("擎", 23000, 23260),
        ("熄", 23260, 23790),
        ("火", 23790, 24140),
        ("了", 24140, 24870),
    ]
```

- [ ] **Step 2: Run the new parser test to verify it fails**

Run: `uv run pytest tests/test_karaoke_parser.py::test_parse_netease_yrc_normalizes_absolute_word_timing_and_preserves_spaces -v`

Expected: FAIL because `parse_raw_karaoke("netease-yrc", ...)` currently returns an empty document.

- [ ] **Step 3: Write the failing malformed-token resilience test**

```python
def test_parse_netease_yrc_skips_bad_tokens_but_keeps_valid_words() -> None:
    document = parse_raw_karaoke(
        "netease-yrc",
        """[0,1600](0,400,0)我(bad)坏(400,400,0)很(800,0,0)词(1200,400,0)好""",
    )

    assert document.source_format == "netease-yrc"
    assert len(document.lines) == 1
    assert document.lines[0].text == "我很好"
    assert [(word.text, word.start_ms, word.end_ms) for word in document.lines[0].words] == [
        ("我", 0, 400),
        ("很", 400, 800),
        ("好", 1200, 1600),
    ]
```

- [ ] **Step 4: Run the malformed-token parser test to verify it fails**

Run: `uv run pytest tests/test_karaoke_parser.py::test_parse_netease_yrc_skips_bad_tokens_but_keeps_valid_words -v`

Expected: FAIL because `parse_raw_karaoke("netease-yrc", ...)` currently returns zero lines.

- [ ] **Step 5: Tighten the unsupported-format test so it still covers true unknown formats**

Replace:

```python
document = parse_raw_karaoke("netease-yrc", "[0,1000](0,1000,0)测试")
```

With:

```python
document = parse_raw_karaoke("unknown-karaoke", "[0,1000](0,1000,0)测试")
```

- [ ] **Step 6: Run the focused parser test file and confirm only the new NetEase cases fail**

Run: `uv run pytest tests/test_karaoke_parser.py -v`

Expected: existing QQ/Kugou and unknown-format tests PASS; new NetEase tests FAIL.

- [ ] **Step 7: Commit the red parser tests**

```bash
git add tests/test_karaoke_parser.py
git commit -m "test: cover netease yrc karaoke parsing"
```

### Task 2: Implement NetEase YRC Parsing In The Existing Dispatcher

**Files:**
- Modify: `src/atv_player/karaoke/parser.py`
- Verify: `tests/test_karaoke_parser.py`

- [ ] **Step 1: Add NetEase YRC dispatch and regex definitions**

Extend `src/atv_player/karaoke/parser.py` with one new branch and one token regex:

```python
_NETEASE_YRC_LINE_RE = re.compile(r"^\[(?P<start>\d+),(?P<duration>\d+)\](?P<body>.+)$")
_NETEASE_YRC_WORD_RE = re.compile(r"\((?P<start>\d+),(?P<duration>\d+),(?P<flag>\d+)\)(?P<text>[^()]*)")


def parse_raw_karaoke(format_name: str, text: str, translation: str = "") -> KaraokeDocument:
    normalized = str(format_name or "").strip().lower()
    if normalized == "qqmusic-qrc":
        return parse_qqmusic_qrc(text, translation=translation)
    if normalized == "kugou-krc":
        return parse_kugou_krc(text, translation=translation)
    if normalized == "netease-yrc":
        return parse_netease_yrc(text, translation=translation)
    return KaraokeDocument(source_format=normalized)
```

- [ ] **Step 2: Implement the minimal `parse_netease_yrc()` function**

Add this function to `src/atv_player/karaoke/parser.py`:

```python
def parse_netease_yrc(text: str, translation: str = "") -> KaraokeDocument:
    lines: list[KaraokeLine] = []
    for raw_line in str(text or "").splitlines():
        match = _NETEASE_YRC_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        line_start = int(match.group("start"))
        line_duration = int(match.group("duration"))
        words: list[KaraokeWord] = []
        for word_match in _NETEASE_YRC_WORD_RE.finditer(match.group("body")):
            token_text = word_match.group("text")
            token_duration = int(word_match.group("duration"))
            if token_text == "" or token_duration <= 0:
                continue
            word_start = int(word_match.group("start"))
            word_end = word_start + token_duration
            words.append(KaraokeWord(text=token_text, start_ms=word_start, end_ms=word_end))
        line_text = "".join(word.text for word in words)
        if line_text:
            lines.append(
                KaraokeLine(
                    start_ms=line_start,
                    end_ms=line_start + line_duration,
                    text=line_text,
                    words=words,
                )
            )
    return KaraokeDocument(source_format="netease-yrc", lines=lines)
```

- [ ] **Step 3: Run the focused happy-path parser test and confirm it passes**

Run: `uv run pytest tests/test_karaoke_parser.py::test_parse_netease_yrc_normalizes_absolute_word_timing_and_preserves_spaces -v`

Expected: PASS

- [ ] **Step 4: Run the malformed-token parser test and confirm it passes**

Run: `uv run pytest tests/test_karaoke_parser.py::test_parse_netease_yrc_skips_bad_tokens_but_keeps_valid_words -v`

Expected: PASS

- [ ] **Step 5: Run the full parser test file and confirm all parser cases pass**

Run: `uv run pytest tests/test_karaoke_parser.py -v`

Expected: all tests PASS, including QQ, Kugou, NetEase, and unknown-format coverage.

- [ ] **Step 6: Refactor only if needed to keep shared parsing logic readable**

If duplication becomes distracting, keep any cleanup local to `src/atv_player/karaoke/parser.py` and do not change behavior. Acceptable cleanup example:

```python
def _build_line(start_ms: int, duration_ms: int, words: list[KaraokeWord]) -> KaraokeLine | None:
    line_text = "".join(word.text for word in words)
    if not line_text:
        return None
    return KaraokeLine(
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
        text=line_text,
        words=words,
    )
```

- [ ] **Step 7: Commit the green parser implementation**

```bash
git add src/atv_player/karaoke/parser.py tests/test_karaoke_parser.py
git commit -m "feat: parse netease yrc karaoke lyrics"
```

### Task 3: Prove Spider Controller Prefers Generated NetEase Karaoke Subtitles

**Files:**
- Modify: `tests/test_spider_plugin_controller.py`
- Read: `src/atv_player/plugins/controller.py`
- Verify: `src/atv_player/karaoke/ass.py`

- [ ] **Step 1: Replace the old unsupported-NetEase controller test with a failing success-path test**

Update `tests/test_spider_plugin_controller.py` so the NetEase case expects generated karaoke output:

```python
def test_controller_build_request_prefers_generated_netease_karaoke_subtitle_over_subt(
    tmp_path, monkeypatch
) -> None:
    cache_root = tmp_path / "app-cache"
    monkeypatch.setattr(controller_module, "app_cache_dir", lambda: cache_root)
    controller = SpiderPluginController(
        LyricPayloadSpider(
            {
                "format": "netease-yrc",
                "text": "[0,1800](0,450,0)轻(450,450,0)舟(900,450,0)已(1350,450,0)过",
            },
            subt="https://cdn.example/fallback.srt",
        ),
        plugin_name="歌词插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert len(first.external_subtitles) == 1
    subtitle = first.external_subtitles[0]
    assert subtitle.name == "逐字歌词 [插件]"
    assert subtitle.format == "text/x-ass"
    assert subtitle.source == "spider"
    assert Path(subtitle.url).suffix == ".ass"
    assert r"{\kf45}轻{\kf45}舟{\kf45}已{\kf45}过" in Path(subtitle.url).read_text(encoding="utf-8")
```

- [ ] **Step 2: Add or keep one true unknown-format fallback test**

Keep fallback coverage by using a genuinely unsupported format:

```python
def test_controller_build_request_falls_back_to_subt_when_lyric_format_is_unknown() -> None:
    controller = SpiderPluginController(
        LyricPayloadSpider(
            {"format": "unknown-karaoke", "text": "[0,1000](0,1000,0)测试"},
            subt="https://cdn.example/fallback.srt",
        ),
        plugin_name="歌词插件",
        search_enabled=True,
    )

    request = controller.build_request("/detail/1")
    first = request.playlists[0][0]

    assert request.playback_loader is not None
    request.playback_loader(first)

    assert [(sub.name, sub.url, sub.format, sub.source) for sub in first.external_subtitles] == [
        ("外挂字幕 [插件]", "https://cdn.example/fallback.srt", "application/x-subrip", "spider"),
    ]
```

- [ ] **Step 3: Run the new NetEase controller test to verify the old behavior is gone**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_prefers_generated_netease_karaoke_subtitle_over_subt -v`

Expected: FAIL before parser implementation is merged, or PASS after Task 2; either result is acceptable as long as the assertion matches the new intended behavior.

- [ ] **Step 4: Run the focused controller fallback test**

Run: `uv run pytest tests/test_spider_plugin_controller.py::test_controller_build_request_falls_back_to_subt_when_lyric_format_is_unknown -v`

Expected: PASS

- [ ] **Step 5: Run the combined karaoke regression slice**

Run: `uv run pytest tests/test_karaoke_parser.py tests/test_spider_plugin_controller.py -v`

Expected: PASS

- [ ] **Step 6: Commit the controller coverage update**

```bash
git add tests/test_spider_plugin_controller.py tests/test_karaoke_parser.py src/atv_player/karaoke/parser.py
git commit -m "test: cover netease karaoke subtitle integration"
```

### Task 4: Final Verification

**Files:**
- Verify: `tests/test_karaoke_parser.py`
- Verify: `tests/test_spider_plugin_controller.py`

- [ ] **Step 1: Run the exact regression suite used by this feature**

Run: `uv run pytest tests/test_karaoke_parser.py tests/test_spider_plugin_controller.py -q`

Expected: all tests PASS with no NetEase fallback regressions.

- [ ] **Step 2: Inspect the diff before closing**

Run: `git diff --stat HEAD~3..HEAD`

Expected: changes limited to the parser and the two targeted test files.

- [ ] **Step 3: Summarize residual risk**

Document in the handoff that this change intentionally does not parse NetEase translation lyrics and treats YRC word starts as absolute timestamps based on observed source samples.
