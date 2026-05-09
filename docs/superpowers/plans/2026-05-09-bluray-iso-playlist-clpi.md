# Blu-ray ISO Playlist And CLPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade remote Blu-ray ISO playback so the default title is built from `MPLS` play items plus on-demand `CLPI` trimming, then exposed as one logical proxied stream instead of a single largest `.m2ts`.

**Architecture:** Keep the existing remote UDF reader, cached physical stream source, and `/iso/` proxy contract unchanged. Extend `bluray_iso.py` with richer playlist metadata, a narrow `CLPI` entry-point parser, byte-range trimming helpers, and a remote-UDF playback path that assembles all trimmed clip segments into one virtual source before falling back to the existing largest-`m2ts` heuristic.

**Tech Stack:** Python 3, `httpx`, `pycdlib`, existing `bluray_iso.py` range-cache utilities, `pytest`

---

## File Map

- `src/atv_player/player/bluray_iso.py`
  Responsibility: parse richer `MPLS` metadata, parse minimal `CLPI` entry points, trim cached `.m2ts` sources, and assemble playlist-backed remote UDF playback plans.
- `tests/test_bluray_iso.py`
  Responsibility: cover playlist metadata parsing, `CLPI` entry-point parsing, 192-byte alignment, cached-source slicing, playlist-backed playback assembly, playlist retry, and fallback behavior.
- `tests/test_hls_proxy_server.py`
  Responsibility: keep regression coverage on playlist-backed logical source reads through the existing `/iso/` proxy path.

## Task 1: Expand MPLS Parsing To Preserve Play Items

**Files:**
- Modify: `tests/test_bluray_iso.py`
- Modify: `src/atv_player/player/bluray_iso.py`

- [ ] **Step 1: Write the failing playlist metadata test**

Replace `test_parse_mpls_playlist_extracts_clip_sequence_and_duration()` in `tests/test_bluray_iso.py` with:

```python
def test_parse_mpls_playlist_extracts_play_items_and_duration() -> None:
    parsed = bluray_iso._parse_mpls_playlist(
        "/BDMV/PLAYLIST/00002.MPLS",
        _build_test_mpls(
            [
                ("00003", 90000, 180000),
                ("00004", 0, 270000),
            ]
        ),
    )

    assert parsed.path == "/BDMV/PLAYLIST/00002.MPLS"
    assert parsed.play_items == (
        bluray_iso._MplsPlayItem(
            clip_id="00003",
            stream_path="/BDMV/STREAM/00003.M2TS",
            in_time=90000,
            out_time=180000,
            duration=90000,
        ),
        bluray_iso._MplsPlayItem(
            clip_id="00004",
            stream_path="/BDMV/STREAM/00004.M2TS",
            in_time=0,
            out_time=270000,
            duration=270000,
        ),
    )
    assert parsed.duration == 360000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bluray_iso.py::test_parse_mpls_playlist_extracts_play_items_and_duration -v`

Expected: FAIL because `_parse_mpls_playlist()` still takes one argument and `_ParsedMplsPlaylist` has no `path` or `play_items`.

- [ ] **Step 3: Write the minimal playlist model and parser update**

In `src/atv_player/player/bluray_iso.py`, replace the existing playlist dataclass with:

```python
@dataclass(frozen=True, slots=True)
class _MplsPlayItem:
    clip_id: str
    stream_path: str
    in_time: int
    out_time: int
    duration: int


@dataclass(frozen=True, slots=True)
class _ParsedMplsPlaylist:
    path: str
    play_items: tuple[_MplsPlayItem, ...]
    duration: int
```

Then update `_parse_mpls_playlist()` to preserve ordered play-item metadata:

```python
def _parse_mpls_playlist(path: str, data: bytes) -> _ParsedMplsPlaylist:
    if len(data) < 20 or data[:4] != b"MPLS":
        raise ValueError("无效的 Blu-ray playlist")
    playlist_start = _read_u32be(data, 8)
    playlist_length = _read_u32be(data, playlist_start)
    playlist_end = min(len(data), playlist_start + 4 + playlist_length)
    header_offset = playlist_start + 4
    play_item_count = _read_u16be(data, header_offset + 2)
    play_item_offset = header_offset + 6
    play_items: list[_MplsPlayItem] = []
    total_duration = 0
    for _ in range(play_item_count):
        item_length = _read_u16be(data, play_item_offset)
        item_start = play_item_offset + 2
        item_end = item_start + item_length
        if item_end > playlist_end or item_end > len(data):
            raise ValueError("MPLS play item 超出边界")
        clip_id = data[item_start : item_start + 5].decode("ascii", errors="ignore").strip().upper()
        clip_codec = data[item_start + 5 : item_start + 9].decode("ascii", errors="ignore").strip().upper()
        in_time = _read_u32be(data, item_start + 12)
        out_time = _read_u32be(data, item_start + 16)
        duration = max(0, out_time - in_time)
        if clip_id and clip_codec == "M2TS":
            play_items.append(
                _MplsPlayItem(
                    clip_id=clip_id,
                    stream_path=f"/BDMV/STREAM/{clip_id}.M2TS",
                    in_time=in_time,
                    out_time=out_time,
                    duration=duration,
                )
            )
            total_duration += duration
        play_item_offset = item_end
    if not play_items:
        raise ValueError("Blu-ray playlist 中没有可播放的片段")
    return _ParsedMplsPlaylist(path=_normalize_iso_path(path), play_items=tuple(play_items), duration=total_duration)
```

Update the existing caller inside `_prepare_remote_udf_playlist_playback()` from:

```python
parsed = _parse_mpls_playlist(playlist_data)
```

to:

```python
parsed = _parse_mpls_playlist(playlist_path, playlist_data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bluray_iso.py::test_parse_mpls_playlist_extracts_play_items_and_duration -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/bluray_iso.py tests/test_bluray_iso.py
git commit -m "feat: preserve bluray playlist play item metadata"
```

## Task 2: Add CLPI Entry-Point Parsing And Cached-Source Trimming Helpers

**Files:**
- Modify: `tests/test_bluray_iso.py`
- Modify: `src/atv_player/player/bluray_iso.py`

- [ ] **Step 1: Write the failing CLPI and trim-helper tests**

Append these helpers and tests to `tests/test_bluray_iso.py` after `_build_test_mpls()`:

```python
def _build_test_clpi(entry_points: list[tuple[int, int]]) -> bytes:
    cpi_body = bytearray()
    cpi_body.extend(len(entry_points).to_bytes(2, "big"))
    for time_45k, byte_offset in entry_points:
        cpi_body.extend(int(time_45k).to_bytes(4, "big"))
        cpi_body.extend(int(byte_offset).to_bytes(4, "big"))
    cpi_start = 24
    header = bytearray(b"HDMV0200")
    header.extend((0).to_bytes(4, "big"))
    header.extend((0).to_bytes(4, "big"))
    header.extend(cpi_start.to_bytes(4, "big"))
    header.extend((0).to_bytes(4, "big"))
    return bytes(header + cpi_body)


def test_parse_clpi_extracts_entry_points() -> None:
    parsed = bluray_iso._parse_clpi_entry_points("00003", _build_test_clpi([(0, 384), (90000, 768), (180000, 1344)]))

    assert parsed == bluray_iso._ParsedClpi(
        clip_id="00003",
        entry_points=(
            bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=384),
            bluray_iso._ClpiEntryPoint(time_45k=90000, byte_offset=768),
            bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=1344),
        ),
    )


def test_compute_trimmed_clip_range_aligns_to_192_byte_packets() -> None:
    parsed_clpi = bluray_iso._ParsedClpi(
        clip_id="00003",
        entry_points=(
            bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=383),
            bluray_iso._ClpiEntryPoint(time_45k=90000, byte_offset=768),
            bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=1345),
        ),
    )

    assert bluray_iso._compute_trimmed_clip_range(parsed_clpi, 1, 180000) == (192, 1344)


def test_slice_cached_iso_stream_source_rebases_trimmed_segments() -> None:
    source = bluray_iso._CachedIsoStreamSource(
        size=18,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=10, physical_start=100),
            bluray_iso._CachedIsoSegment(logical_offset=10, length=8, physical_start=500),
        ),
    )

    sliced = bluray_iso._slice_cached_iso_stream_source(source, 6, 8)

    assert sliced == bluray_iso._CachedIsoStreamSource(
        size=8,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=4, physical_start=106),
            bluray_iso._CachedIsoSegment(logical_offset=4, length=4, physical_start=500),
        ),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bluray_iso.py::test_parse_clpi_extracts_entry_points tests/test_bluray_iso.py::test_compute_trimmed_clip_range_aligns_to_192_byte_packets tests/test_bluray_iso.py::test_slice_cached_iso_stream_source_rebases_trimmed_segments -v`

Expected: FAIL because `_ParsedClpi`, `_ClpiEntryPoint`, `_parse_clpi_entry_points()`, `_compute_trimmed_clip_range()`, and `_slice_cached_iso_stream_source()` do not exist yet.

- [ ] **Step 3: Write the minimal CLPI and trim helpers**

In `src/atv_player/player/bluray_iso.py`, add the new dataclasses near the existing private metadata models:

```python
@dataclass(frozen=True, slots=True)
class _ClpiEntryPoint:
    time_45k: int
    byte_offset: int


@dataclass(frozen=True, slots=True)
class _ParsedClpi:
    clip_id: str
    entry_points: tuple[_ClpiEntryPoint, ...]
```

Add a narrow parser that reads the synthetic CPI layout from the tests:

```python
def _parse_clpi_entry_points(clip_id: str, data: bytes) -> _ParsedClpi:
    if len(data) < 26 or data[:4] != b"HDMV":
        raise ValueError("无效的 Blu-ray clip info")
    cpi_start = _read_u32be(data, 16)
    entry_count = _read_u16be(data, cpi_start)
    cursor = cpi_start + 2
    entry_points: list[_ClpiEntryPoint] = []
    for _ in range(entry_count):
        entry_points.append(
            _ClpiEntryPoint(
                time_45k=_read_u32be(data, cursor),
                byte_offset=_read_u32be(data, cursor + 4),
            )
        )
        cursor += 8
    if not entry_points:
        raise ValueError("Blu-ray clip info 中没有可用入口点")
    return _ParsedClpi(clip_id=clip_id, entry_points=tuple(sorted(entry_points, key=lambda item: item.time_45k)))
```

Add trim helpers below `_compose_cached_iso_stream_sources()`:

```python
def _compute_trimmed_clip_range(parsed_clpi: _ParsedClpi, in_time: int, out_time: int) -> tuple[int, int]:
    start_point = next(
        (entry for entry in parsed_clpi.entry_points if entry.time_45k >= in_time),
        parsed_clpi.entry_points[-1],
    )
    end_point = next(
        (entry for entry in reversed(parsed_clpi.entry_points) if entry.time_45k <= out_time),
        parsed_clpi.entry_points[0],
    )
    start = (start_point.byte_offset // 192) * 192
    end_exclusive = ((end_point.byte_offset // 192) + 1) * 192
    if end_exclusive <= start:
        raise ValueError("Blu-ray clip 裁剪区间无效")
    return start, end_exclusive


def _slice_cached_iso_stream_source(
    source: _CachedIsoStreamSource,
    start: int,
    length: int,
) -> _CachedIsoStreamSource:
    if start < 0 or length <= 0 or start + length > source.size:
        raise ValueError("Blu-ray clip 裁剪区间超出边界")
    end_exclusive = start + length
    segments: list[_CachedIsoSegment] = []
    logical_offset = 0
    for segment in source.segments:
        segment_start = segment.logical_offset
        segment_end = segment.logical_offset + segment.length
        if segment_end <= start:
            continue
        if segment_start >= end_exclusive:
            break
        local_start = max(start, segment_start)
        local_end = min(end_exclusive, segment_end)
        slice_length = local_end - local_start
        segments.append(
            _CachedIsoSegment(
                logical_offset=logical_offset,
                length=slice_length,
                physical_start=segment.physical_start + (local_start - segment_start),
            )
        )
        logical_offset += slice_length
    if logical_offset != length or not segments:
        raise ValueError("Blu-ray clip 裁剪区间无法映射到底层分段")
    return _CachedIsoStreamSource(size=length, segments=tuple(segments))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bluray_iso.py::test_parse_clpi_extracts_entry_points tests/test_bluray_iso.py::test_compute_trimmed_clip_range_aligns_to_192_byte_packets tests/test_bluray_iso.py::test_slice_cached_iso_stream_source_rebases_trimmed_segments -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/bluray_iso.py tests/test_bluray_iso.py
git commit -m "feat: add bluray clipinfo trim helpers"
```

## Task 3: Build Playlist-Backed Remote UDF Playback Plans

**Files:**
- Modify: `tests/test_bluray_iso.py`
- Modify: `src/atv_player/player/bluray_iso.py`

- [ ] **Step 1: Replace the old playlist-selection tests with playlist-assembly tests**

In `tests/test_bluray_iso.py`, replace `test_prepare_iso_playback_prefers_largest_clip_from_longest_playlist_for_remote_udf()` with:

```python
def test_prepare_iso_playback_builds_trimmed_virtual_stream_from_playlist_for_remote_udf(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    sources = {
        "/BDMV/STREAM/00001.M2TS": bluray_iso._CachedIsoStreamSource(
            size=1536,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1536, physical_start=1000),),
        ),
        "/BDMV/STREAM/00002.M2TS": bluray_iso._CachedIsoStreamSource(
            size=1536,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1536, physical_start=4000),),
        ),
    }

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            ("/BDMV/PLAYLIST/00002.MPLS", _build_test_mpls([("00001", 0, 90000), ("00002", 0, 180000)])),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(bluray_iso, "_build_cached_iso_stream_source", lambda iso, entry_ref: sources[entry_ref.path])
    monkeypatch.setattr(
        bluray_iso,
        "_read_remote_udf_clipinfo",
        lambda iso, clip_id: {
            "00001": bluray_iso._ParsedClpi(
                clip_id="00001",
                entry_points=(
                    bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=384),
                    bluray_iso._ClpiEntryPoint(time_45k=90000, byte_offset=768),
                ),
            ),
            "00002": bluray_iso._ParsedClpi(
                clip_id="00002",
                entry_points=(
                    bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=192),
                    bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=576),
                ),
            ),
        }[clip_id],
    )
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=9999)],
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00001.M2TS"
    assert plan.stream.size == 960
    assert plan.source == bluray_iso._CachedIsoStreamSource(
        size=960,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=768, physical_start=1384),
            bluray_iso._CachedIsoSegment(logical_offset=768, length=192, physical_start=4192),
        ),
    )
```

Replace `test_prepare_iso_playback_only_resolves_selected_playlist_clips_for_remote_udf()` with:

```python
def test_prepare_iso_playback_only_resolves_selected_playlist_clipinfo_for_remote_udf(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    resolved_clip_ids: list[str] = []

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            ("/BDMV/PLAYLIST/00001.MPLS", _build_test_mpls([("00080", 0, 90000)])),
            ("/BDMV/PLAYLIST/00002.MPLS", _build_test_mpls([("00001", 0, 90000), ("00002", 0, 180000)])),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: bluray_iso._CachedIsoStreamSource(
            size=1536,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1536, physical_start=1000),),
        ),
    )

    def fake_read_remote_udf_clipinfo(iso, clip_id):
        resolved_clip_ids.append(clip_id)
        return bluray_iso._ParsedClpi(
            clip_id=clip_id,
            entry_points=(
                bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=192),
                bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=576),
            ),
        )

    monkeypatch.setattr(bluray_iso, "_read_remote_udf_clipinfo", fake_read_remote_udf_clipinfo)
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=9999)],
    )

    bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert resolved_clip_ids == ["00001", "00002"]
```

Append one retry/fallback regression test:

```python
def test_prepare_iso_playback_tries_next_playlist_when_first_clipinfo_trim_fails(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            ("/BDMV/PLAYLIST/00003.MPLS", _build_test_mpls([("00080", 0, 90000)])),
            ("/BDMV/PLAYLIST/00002.MPLS", _build_test_mpls([("00001", 0, 90000), ("00002", 0, 180000)])),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: bluray_iso._CachedIsoStreamSource(
            size=1536,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1536, physical_start=2000),),
        ),
    )

    def fake_read_remote_udf_clipinfo(iso, clip_id):
        if clip_id == "00080":
            raise ValueError("bad clpi")
        return bluray_iso._ParsedClpi(
            clip_id=clip_id,
            entry_points=(
                bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=192),
                bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=576),
            ),
        )

    monkeypatch.setattr(bluray_iso, "_read_remote_udf_clipinfo", fake_read_remote_udf_clipinfo)
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=9999)],
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00001.M2TS"
    assert plan.stream.size == 768


def test_prepare_iso_playback_falls_back_to_largest_stream_when_all_playlists_fail(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            ("/BDMV/PLAYLIST/00002.MPLS", _build_test_mpls([("00001", 0, 90000), ("00002", 0, 180000)])),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_read_remote_udf_clipinfo", lambda iso, clip_id: (_ for _ in ()).throw(ValueError("bad clpi")))
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [
            BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=20),
            BluRayIsoStream(path="/BDMV/STREAM/00010.M2TS", size=10),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path, record=SimpleNamespace()))
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: bluray_iso._CachedIsoStreamSource(
            size=entry_ref.path.endswith("00080.M2TS") and 20 or 10,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=20 if entry_ref.path.endswith("00080.M2TS") else 10, physical_start=300),),
        ),
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream == BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bluray_iso.py::test_prepare_iso_playback_builds_trimmed_virtual_stream_from_playlist_for_remote_udf tests/test_bluray_iso.py::test_prepare_iso_playback_only_resolves_selected_playlist_clipinfo_for_remote_udf tests/test_bluray_iso.py::test_prepare_iso_playback_tries_next_playlist_when_first_clipinfo_trim_fails tests/test_bluray_iso.py::test_prepare_iso_playback_falls_back_to_largest_stream_when_all_playlists_fail -v`

Expected: FAIL because `_prepare_remote_udf_playlist_playback()` still chooses the largest referenced clip and has no `_read_remote_udf_clipinfo()` path.

- [ ] **Step 3: Implement playlist-backed source assembly**

In `src/atv_player/player/bluray_iso.py`, add a helper to load one referenced `CLPI` lazily:

```python
def _read_remote_udf_clipinfo(remote_iso: _RemoteUdfIso, clip_id: str) -> _ParsedClpi:
    clipinfo_path = f"/BDMV/CLIPINF/{clip_id}.CLPI"
    entry_ref = _find_remote_udf_entry(remote_iso, clipinfo_path)
    return _parse_clpi_entry_points(clip_id, _read_remote_udf_file(remote_iso, entry_ref))
```

Add a helper that converts one play item into one trimmed child source:

```python
def _build_trimmed_playlist_clip_source(
    remote_iso: _RemoteUdfIso,
    play_item: _MplsPlayItem,
) -> _CachedIsoStreamSource:
    clip_entry_ref = _find_remote_udf_entry(remote_iso, play_item.stream_path)
    clip_source = _build_cached_iso_stream_source(remote_iso, clip_entry_ref)
    parsed_clpi = _read_remote_udf_clipinfo(remote_iso, play_item.clip_id)
    start, end_exclusive = _compute_trimmed_clip_range(parsed_clpi, play_item.in_time, play_item.out_time)
    return _slice_cached_iso_stream_source(clip_source, start, end_exclusive - start)
```

Then replace `_prepare_remote_udf_playlist_playback()` with playlist-backed assembly:

```python
def _prepare_remote_udf_playlist_playback(remote_iso: _RemoteUdfIso) -> IsoPlaybackPlan | None:
    playlist_candidates: list[_ParsedMplsPlaylist] = []
    try:
        playlists = _iter_remote_udf_playlists(remote_iso)
    except ValueError:
        return None
    for playlist_path, playlist_data in playlists:
        try:
            playlist_candidates.append(_parse_mpls_playlist(playlist_path, playlist_data))
        except ValueError:
            continue
    for parsed in sorted(playlist_candidates, key=lambda item: (item.duration, item.path), reverse=True):
        try:
            child_sources = [
                _build_trimmed_playlist_clip_source(remote_iso, play_item)
                for play_item in parsed.play_items
            ]
        except ValueError:
            continue
        composed = _compose_cached_iso_stream_sources(child_sources)
        first_path = parsed.play_items[0].stream_path
        return IsoPlaybackPlan(
            stream=BluRayIsoStream(path=first_path, size=composed.size),
            source=composed,
        )
    return None
```

Keep the existing fallback path in `prepare_iso_playback()` unchanged so remote UDF playback still returns the largest plain stream when all playlist candidates fail.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bluray_iso.py::test_prepare_iso_playback_builds_trimmed_virtual_stream_from_playlist_for_remote_udf tests/test_bluray_iso.py::test_prepare_iso_playback_only_resolves_selected_playlist_clipinfo_for_remote_udf tests/test_bluray_iso.py::test_prepare_iso_playback_tries_next_playlist_when_first_clipinfo_trim_fails tests/test_bluray_iso.py::test_prepare_iso_playback_falls_back_to_largest_stream_when_all_playlists_fail -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atv_player/player/bluray_iso.py tests/test_bluray_iso.py
git commit -m "feat: assemble bluray playlists from clipinfo trims"
```

## Task 4: Run Regression Coverage On Logical Source Reads

**Files:**
- Modify: `tests/test_hls_proxy_server.py`
- Modify: `tests/test_bluray_iso.py`

- [ ] **Step 1: Add one proxy regression test for multi-segment logical sources**

Append this test to `tests/test_hls_proxy_server.py` near the existing cached ISO source range tests:

```python
def test_local_hls_proxy_server_serves_composed_iso_source_across_segment_boundaries() -> None:
    remote_bytes = bytes(range(64)) * 128
    requests: list[str] = []

    class FakeResponse:
        def __init__(self, start: int, end: int) -> None:
            self.content = remote_bytes[start : end + 1]
            self.status_code = 206
            self.headers = {"Content-Range": f"bytes {start}-{end}/{len(remote_bytes)}"}

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, headers: dict[str, str], timeout: float, follow_redirects: bool) -> FakeResponse:
        requests.append(headers["Range"])
        start_text, end_text = headers["Range"].removeprefix("bytes=").split("-", 1)
        return FakeResponse(int(start_text), int(end_text))

    server = LocalHlsProxyServer(get=fake_get)
    source = _CachedIsoStreamSource(
        size=12,
        segments=(
            _CachedIsoSegment(logical_offset=0, length=8, physical_start=100),
            _CachedIsoSegment(logical_offset=8, length=4, physical_start=300),
        ),
    )
    media_url = server.create_iso_media_url(
        "http://media.example/disc.iso",
        {},
        stream_path="/BDMV/STREAM/00001.M2TS",
        stream_size=12,
        iso_stream_source=source,
    )
    token = media_url.split("/iso/", 1)[1].split("/", 1)[0]

    status, headers, body = server.handle_request(
        "GET",
        f"/iso/{token}/BDMV/STREAM/00001.M2TS",
        {"Range": "bytes=6-9"},
    )

    assert status == 206
    assert ("Content-Range", "bytes 6-9/12") in headers
    assert body == remote_bytes[106:108] + remote_bytes[300:302]
    assert requests == ["bytes=106-107", "bytes=300-301"]
```

- [ ] **Step 2: Run test to verify it fails or proves existing coverage is already sufficient**

Run: `uv run pytest tests/test_hls_proxy_server.py::test_local_hls_proxy_server_serves_composed_iso_source_across_segment_boundaries -v`

Expected: PASS if the existing source-range reader already handles composed sources correctly. If it fails, fix only the range-reader logic in `src/atv_player/player/bluray_iso.py` until it passes.

- [ ] **Step 3: Run the full focused regression suite**

Run: `uv run pytest tests/test_bluray_iso.py tests/test_hls_proxy_server.py -v`

Expected: PASS with the new playlist-backed remote UDF behavior and no proxy regression.

- [ ] **Step 4: Commit**

```bash
git add tests/test_hls_proxy_server.py tests/test_bluray_iso.py src/atv_player/player/bluray_iso.py
git commit -m "test: verify bluray playlist logical stream proxy reads"
```
