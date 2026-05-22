# YouTube Karaoke Speaker Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert eligible YouTube `yt-dlp` subtitles from `vtt/srt` into generated `ASS` subtitles with approximate per-character karaoke highlighting and simple speaker-based color separation.

**Architecture:** Keep subtitle discovery in `yt_dlp_service.py` unchanged and add one new pure helper module that parses ordinary subtitle text and renders styled `ASS`. Integrate only at `PlayerWindow._load_external_subtitle()` so the existing subtitle-fetch, temp-file, and `mpv` loading flow stays intact and failures cleanly fall back to the original subtitle text.

**Tech Stack:** Python, dataclasses, PySide6, pytest, `httpx`, `mpv`, ASS subtitle syntax

---

## File Structure

- Create: `src/atv_player/youtube_subtitle_ass.py`
  Own plain-text subtitle parsing, speaker-prefix detection, approximate karaoke segmentation, and `ASS` rendering.
- Modify: `src/atv_player/ui/player_window.py:7625-7676`
  Keep subtitle fetching and HTML guard behavior, then add a narrow optional `yt-dlp` YouTube subtitle conversion branch before the temp file is written.
- Create: `tests/test_youtube_subtitle_ass.py`
  Cover parsing, speaker detection, palette reuse, karaoke rendering, and unsupported-input fallbacks.
- Modify: `tests/test_player_window_ui.py:11794-11845`
  Add `PlayerWindow` integration coverage for `.ass` conversion, non-YouTube passthrough, and conversion failure fallback.

### Task 1: Add Focused Failing Tests For YouTube Subtitle Conversion

**Files:**
- Create: `tests/test_youtube_subtitle_ass.py`
- Test: `tests/test_youtube_subtitle_ass.py`

- [ ] **Step 1: Write the failing conversion tests**

```python
from atv_player.youtube_subtitle_ass import convert_youtube_subtitle_text_to_ass


def test_convert_webvtt_with_speaker_prefixes_emits_ass_styles_and_kf_tags() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:01.200\n"
        "Alice: Hello!\n\n"
        "00:00:01.200 --> 00:00:02.400\n"
        "[Bob] Hi.\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "[Script Info]" in subtitle
    assert "Style: YouTubeDefault" in subtitle
    assert "Style: YouTubeSpeaker1" in subtitle
    assert "Style: YouTubeSpeaker2" in subtitle
    assert "Dialogue: 0,0:00:00.00,0:00:01.20,YouTubeSpeaker1" in subtitle
    assert "Dialogue: 0,0:00:01.20,0:00:02.40,YouTubeSpeaker2" in subtitle
    assert r"{\kf" in subtitle
    assert "Alice:" not in subtitle
    assert "[Bob]" not in subtitle


def test_convert_srt_without_speaker_prefix_uses_default_style() -> None:
    text = (
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "你好 世界\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,YouTubeDefault" in subtitle
    assert r"{\kf" in subtitle


def test_convert_returns_none_for_unsupported_or_empty_text() -> None:
    assert convert_youtube_subtitle_text_to_ass("") is None
    assert convert_youtube_subtitle_text_to_ass("<tt>Hello</tt>") is None
```

- [ ] **Step 2: Run the new test file to verify it fails**

Run: `uv run pytest tests/test_youtube_subtitle_ass.py -v`
Expected: FAIL with `ModuleNotFoundError` for `atv_player.youtube_subtitle_ass`.

- [ ] **Step 3: Extend the test file with palette reuse and static-fallback coverage**

```python
def test_convert_reuses_same_style_for_repeated_speaker() -> None:
    text = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:01.000\n"
        "Alice: One\n\n"
        "00:00:01.000 --> 00:00:02.000\n"
        "Alice: Two\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert subtitle.count("Style: YouTubeSpeaker1") == 1
    assert subtitle.count("Dialogue: 0,0:00:00.00,0:00:01.00,YouTubeSpeaker1") == 1
    assert subtitle.count("Dialogue: 0,0:00:01.00,0:00:02.00,YouTubeSpeaker1") == 1


def test_convert_degrades_punctuation_only_cue_to_static_dialogue() -> None:
    text = (
        "1\n"
        "00:00:00,000 --> 00:00:00,400\n"
        "...\n"
    )

    subtitle = convert_youtube_subtitle_text_to_ass(text)

    assert subtitle is not None
    assert "Dialogue: 0,0:00:00.00,0:00:00.40,YouTubeDefault" in subtitle
    assert r"{\kf" not in subtitle
```

- [ ] **Step 4: Re-run the test file and confirm it still fails for the missing module**

Run: `uv run pytest tests/test_youtube_subtitle_ass.py -v`
Expected: FAIL because the conversion module still does not exist.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/test_youtube_subtitle_ass.py
git commit -m "test: cover YouTube subtitle ass conversion"
```

### Task 2: Implement The Pure YouTube Subtitle To ASS Helper

**Files:**
- Create: `src/atv_player/youtube_subtitle_ass.py`
- Test: `tests/test_youtube_subtitle_ass.py`

- [ ] **Step 1: Create the new module with dataclasses, public API, and format dispatch**

```python
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(slots=True)
class Cue:
    start_ms: int
    end_ms: int
    raw_text: str


@dataclass(slots=True)
class StyledCue:
    start_ms: int
    end_ms: int
    speaker: str
    content_text: str
    style_name: str
    segments: list[tuple[str, int]]


def convert_youtube_subtitle_text_to_ass(text: str) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    cues = _parse_subtitle_cues(normalized)
    if not cues:
        return None
    styled_cues = _style_cues(cues)
    if not styled_cues:
        return None
    return _render_ass(styled_cues)
```

- [ ] **Step 2: Implement cue parsing for WebVTT and SRT**

```python
_VTT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
_SRT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def _parse_subtitle_cues(text: str) -> list[Cue]:
    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        return _parse_webvtt_cues(stripped)
    if "-->" in stripped and "," in stripped:
        return _parse_srt_cues(stripped)
    return []


def _parse_webvtt_cues(text: str) -> list[Cue]:
    lines = text.splitlines()
    cues: list[Cue] = []
    index = 0
    while index < len(lines):
        timing_match = _VTT_TIMING_RE.search(lines[index].strip())
        if timing_match is None:
            index += 1
            continue
        index += 1
        payload: list[str] = []
        while index < len(lines) and lines[index].strip():
            payload.append(lines[index].strip())
            index += 1
        cue_text = " ".join(part for part in payload if part).strip()
        if cue_text:
            cues.append(
                Cue(
                    start_ms=_parse_timestamp_ms(timing_match.group("start")),
                    end_ms=_parse_timestamp_ms(timing_match.group("end")),
                    raw_text=cue_text,
                )
            )
        index += 1
    return [cue for cue in cues if cue.end_ms > cue.start_ms]


def _parse_srt_cues(text: str) -> list[Cue]:
    blocks = re.split(r"\n\s*\n", text.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if _SRT_TIMING_RE.search(lines[0]):
            timing_line = lines[0]
            payload_lines = lines[1:]
        elif len(lines) >= 2 and _SRT_TIMING_RE.search(lines[1]):
            timing_line = lines[1]
            payload_lines = lines[2:]
        else:
            continue
        timing_match = _SRT_TIMING_RE.search(timing_line)
        if timing_match is None:
            continue
        cue_text = " ".join(payload_lines).strip()
        if not cue_text:
            continue
        cues.append(
            Cue(
                start_ms=_parse_timestamp_ms(timing_match.group("start")),
                end_ms=_parse_timestamp_ms(timing_match.group("end")),
                raw_text=cue_text,
            )
        )
    return [cue for cue in cues if cue.end_ms > cue.start_ms]
```

- [ ] **Step 3: Implement speaker detection, segment building, and ASS rendering**

```python
_BRACKET_SPEAKER_RE = re.compile(r"^(?:\[(?P<speaker1>[^\]]+)\]|【(?P<speaker2>[^】]+)】)\s*(?P<text>.+)$")
_COLON_SPEAKER_RE = re.compile(r"^(?P<speaker>[^:：]{1,40})[:：]\s*(?P<text>.+)$")
_DASH_SPEAKER_RE = re.compile(r"^(?P<speaker>[^-]{1,40})\s-\s(?P<text>.+)$")
_SPEAKER_PALETTE = ("YouTubeSpeaker1", "YouTubeSpeaker2", "YouTubeSpeaker3", "YouTubeSpeaker4")


def _style_cues(cues: list[Cue]) -> list[StyledCue]:
    style_by_speaker: dict[str, str] = {}
    styled: list[StyledCue] = []
    for cue in cues:
        speaker, content_text = _split_speaker_prefix(cue.raw_text)
        normalized_content = content_text.strip()
        style_name = "YouTubeDefault"
        if speaker:
            speaker_key = " ".join(speaker.split()).casefold()
            if speaker_key not in style_by_speaker:
                style_by_speaker[speaker_key] = _SPEAKER_PALETTE[len(style_by_speaker) % len(_SPEAKER_PALETTE)]
            style_name = style_by_speaker[speaker_key]
        segments = _build_segments(normalized_content, cue.end_ms - cue.start_ms)
        styled.append(
            StyledCue(
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                speaker=speaker,
                content_text=normalized_content,
                style_name=style_name,
                segments=segments,
            )
        )
    return [cue for cue in styled if cue.content_text]


def _split_speaker_prefix(text: str) -> tuple[str, str]:
    for pattern in (_BRACKET_SPEAKER_RE, _COLON_SPEAKER_RE, _DASH_SPEAKER_RE):
        match = pattern.match(text.strip())
        if match is None:
            continue
        speaker = match.groupdict().get("speaker") or match.groupdict().get("speaker1") or match.groupdict().get("speaker2") or ""
        content = str(match.group("text") or "").strip()
        if content:
            return " ".join(speaker.split()), content
    return "", text.strip()


def _build_segments(text: str, duration_ms: int) -> list[tuple[str, int]]:
    visible_units = [char for char in text if not char.isspace() and char not in ".,!?;:，。！？；：…"]
    if len(visible_units) < 2 or duration_ms < len(visible_units) * 10:
        return []
    base_duration = max(1, round(duration_ms / len(visible_units) / 10))
    segments: list[tuple[str, int]] = []
    current_index = -1
    for char in text:
        if char.isspace() or char in ".,!?;:，。！？；：…":
            if segments:
                previous_text, previous_duration = segments[-1]
                segments[-1] = (previous_text + char, previous_duration)
            else:
                segments.append((char, 1))
            continue
        current_index += 1
        segments.append((char, base_duration))
    return segments


def _render_ass(cues: list[StyledCue]) -> str:
    events = [_render_dialogue(cue) for cue in cues]
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: YouTubeDefault,Arial,44,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker1,Arial,44,&H00FFF27A,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker2,Arial,44,&H0078F0FF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker3,Arial,44,&H0090FF9A,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "Style: YouTubeSpeaker4,Arial,44,&H0099B6FF,&H0000D7FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,60,60,110,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
        ]
    )
```

- [ ] **Step 4: Add the dialogue renderer, timestamp conversion, and ASS escaping**

```python
def _render_dialogue(cue: StyledCue) -> str:
    if cue.segments:
        text = "".join(rf"{{\kf{duration}}}{_escape_ass(segment)}" for segment, duration in cue.segments)
    else:
        text = _escape_ass(cue.content_text)
    return (
        f"Dialogue: 0,{_ass_time(cue.start_ms)},{_ass_time(cue.end_ms)},"
        f"{cue.style_name},,0,0,0,,{text}"
    )


def _parse_timestamp_ms(value: str) -> int:
    normalized = value.replace(",", ".")
    hours, minutes, seconds = normalized.split(":")
    whole_seconds, millis = seconds.split(".")
    return (
        int(hours) * 3600 * 1000
        + int(minutes) * 60 * 1000
        + int(whole_seconds) * 1000
        + int(millis)
    )


def _ass_time(value_ms: int) -> str:
    total_cs = max(0, round(value_ms / 10))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, centiseconds = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
```

- [ ] **Step 5: Run the new conversion tests and verify they pass**

Run: `uv run pytest tests/test_youtube_subtitle_ass.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/atv_player/youtube_subtitle_ass.py tests/test_youtube_subtitle_ass.py
git commit -m "feat: add YouTube subtitle ass conversion helper"
```

### Task 3: Add Failing PlayerWindow Integration Tests

**Files:**
- Modify: `tests/test_player_window_ui.py`
- Test: `tests/test_player_window_ui.py`

- [ ] **Step 1: Write the failing YouTube-to-ASS integration test**

```python
def test_player_window_converts_ytdlp_youtube_vtt_to_ass_before_loading(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def __init__(self) -> None:
            self.loaded_external_subtitles: list[tuple[str, bool]] = []

        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            self.loaded_external_subtitles.append((path, select_for_secondary))
            return 91

    class TextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda url, **kwargs: TextResponse("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nAlice: hello\n"),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="yt1", vod_name="YT"),
        playlist=[
            PlayItem(
                title="Video",
                url="https://stream.test/video.mp4",
                original_url="https://www.youtube.com/watch?v=test123",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="English [yt-dlp]",
                        lang="en",
                        url="https://sub.example/en.vtt",
                        format="vtt",
                        source="ytdlp",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)

    track_id, subtitle_path = window._load_external_subtitle(
        session.playlist[0].external_subtitles[0],
        secondary=False,
    )

    assert track_id == 91
    assert subtitle_path.suffix == ".ass"
    assert "[Script Info]" in subtitle_path.read_text(encoding="utf-8")
    assert window.video.loaded_external_subtitles == [(str(subtitle_path), False)]
```

- [ ] **Step 2: Write the failing passthrough and conversion-fallback tests**

```python
def test_player_window_keeps_non_youtube_ytdlp_vtt_as_vtt(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            return 91

    class TextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda url, **kwargs: TextResponse("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n"),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="vm1", vod_name="VM"),
        playlist=[
            PlayItem(
                title="Video",
                url="https://stream.test/video.mp4",
                original_url="https://vimeo.com/123456",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="English [yt-dlp]",
                        lang="en",
                        url="https://sub.example/en.vtt",
                        format="vtt",
                        source="ytdlp",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)

    _track_id, subtitle_path = window._load_external_subtitle(
        session.playlist[0].external_subtitles[0],
        secondary=False,
    )

    assert subtitle_path.suffix == ".vtt"


def test_player_window_falls_back_to_original_vtt_when_conversion_raises(qtbot, monkeypatch) -> None:
    class FakeVideo:
        def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
            return 91

    class TextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(
        player_window_module.httpx,
        "get",
        lambda url, **kwargs: TextResponse("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n"),
    )
    monkeypatch.setattr(
        player_window_module,
        "convert_youtube_subtitle_text_to_ass",
        lambda text: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    session = PlayerSession(
        vod=VodItem(vod_id="yt1", vod_name="YT"),
        playlist=[
            PlayItem(
                title="Video",
                url="https://stream.test/video.mp4",
                original_url="https://www.youtube.com/watch?v=test123",
                external_subtitles=[
                    ExternalSubtitleOption(
                        name="English [yt-dlp]",
                        lang="en",
                        url="https://sub.example/en.vtt",
                        format="vtt",
                        source="ytdlp",
                    )
                ],
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
    )
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(session)

    _track_id, subtitle_path = window._load_external_subtitle(
        session.playlist[0].external_subtitles[0],
        secondary=False,
    )

    assert subtitle_path.suffix == ".vtt"
    assert subtitle_path.read_text(encoding="utf-8").startswith("WEBVTT")
```

- [ ] **Step 3: Run only the new player-window tests to verify they fail**

Run: `uv run pytest tests/test_player_window_ui.py -k "converts_ytdlp_youtube_vtt_to_ass_before_loading or keeps_non_youtube_ytdlp_vtt_as_vtt or falls_back_to_original_vtt_when_conversion_raises" -v`
Expected: FAIL because `PlayerWindow` still writes the fetched text unchanged and never imports the conversion helper.

- [ ] **Step 4: Commit the failing integration tests**

```bash
git add tests/test_player_window_ui.py
git commit -m "test: cover YouTube subtitle ass player integration"
```

### Task 4: Integrate Conversion Into PlayerWindow With Safe Fallbacks

**Files:**
- Modify: `src/atv_player/ui/player_window.py:1-120`
- Modify: `src/atv_player/ui/player_window.py:7634-7676`
- Test: `tests/test_player_window_ui.py`
- Test: `tests/test_youtube_subtitle_ass.py`

- [ ] **Step 1: Import the conversion helper and add a narrow eligibility helper**

```python
from atv_player.youtube_subtitle_ass import convert_youtube_subtitle_text_to_ass
```

```python
def _should_convert_ytdlp_youtube_subtitle_to_ass(
    self,
    subtitle: ExternalSubtitleOption,
    text: str,
) -> bool:
    if subtitle.source != "ytdlp":
        return False
    normalized_suffix = self._external_subtitle_suffix(subtitle, text)
    if normalized_suffix not in {".vtt", ".srt"}:
        return False
    current_item = self._current_play_item()
    source_url = "" if current_item is None else str(current_item.original_url or current_item.url or "").strip()
    host = urlparse(source_url).netloc.casefold()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
```

- [ ] **Step 2: Wrap conversion inside `_load_external_subtitle()` and keep the existing HTML guard first**

```python
def _load_external_subtitle(
    self,
    subtitle: ExternalSubtitleOption,
    *,
    secondary: bool,
) -> tuple[int | None, Path]:
    text = self._fetch_external_subtitle_text(subtitle)
    if not text.strip():
        raise ValueError("字幕内容为空")
    self._validate_external_subtitle_text(subtitle, text)

    subtitle_text = text
    suffix = self._external_subtitle_suffix(subtitle, text)
    if self._should_convert_ytdlp_youtube_subtitle_to_ass(subtitle, text):
        try:
            converted = convert_youtube_subtitle_text_to_ass(text)
        except Exception as exc:
            logger.warning("Failed to convert yt-dlp YouTube subtitle to ASS: %s", exc)
        else:
            if converted:
                subtitle_text = converted
                suffix = ".ass"

    subtitle_path = self._write_external_subtitle_file(subtitle_text, suffix)
    track_id = self.video.load_external_subtitle(str(subtitle_path), select_for_secondary=secondary)
    return track_id, subtitle_path
```

- [ ] **Step 3: Run the focused player-window and helper tests**

Run: `uv run pytest tests/test_youtube_subtitle_ass.py tests/test_player_window_ui.py -k "youtube_subtitle_ass or ytdlp_youtube_vtt_to_ass or keeps_non_youtube_ytdlp_vtt_as_vtt or falls_back_to_original_vtt_when_conversion_raises or translated_vtt_html_response" -v`
Expected: PASS

- [ ] **Step 4: Run the broader external-subtitle regression slice**

Run: `uv run pytest tests/test_player_window_ui.py -k "external_subtitle or ytdlp_webvtt or translated_vtt_html_response" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/ui/player_window.py src/atv_player/youtube_subtitle_ass.py tests/test_player_window_ui.py tests/test_youtube_subtitle_ass.py
git commit -m "feat: convert YouTube yt-dlp subtitles to karaoke ass"
```

## Self-Review

Spec coverage check:

- YouTube-only eligibility is implemented in Task 4 via `subtitle.source`, suffix check, and YouTube host detection.
- Uploaded subtitles plus automatic captions are both covered because conversion happens after text fetch and only depends on the fetched `vtt/srt` text.
- Speaker-prefix detection and fixed palette reuse are implemented in Task 2 and verified in Task 1 tests.
- Approximate per-character karaoke timing and cue-level static fallback are implemented in Task 2 and verified in Task 1 tests.
- Player fallback to original subtitle text on unsupported input or conversion failure is implemented and tested in Tasks 3 and 4.
- Existing blocked-HTML YouTube caption guard is preserved and explicitly included in Task 4 regression commands.

Placeholder scan:

- No `TODO`, `TBD`, or deferred “implement later” steps remain.
- Every code-changing step contains explicit code blocks.
- Every verification step includes an exact `pytest` command and expected outcome.

Type consistency check:

- The plan consistently uses `convert_youtube_subtitle_text_to_ass()`, `Cue`, `StyledCue`, `YouTubeDefault`, and `YouTubeSpeaker1` through `YouTubeSpeaker4`.
- `PlayerWindow` integration refers to `_should_convert_ytdlp_youtube_subtitle_to_ass()` in both the tests and implementation step.
