from types import SimpleNamespace

import atv_player.player.bluray_iso as bluray_iso
from atv_player.player.bluray_iso import (
    BluRayIsoStream,
    BlurayIsoInspector,
    _UdfPartitionExtent,
    _UdfPartitionResolver,
    _map_udf_partition_block_direct,
    _parse_udf_metadata_partition_map,
    is_remote_iso_url,
    pick_main_feature_stream,
)


def test_is_remote_iso_url_accepts_http_iso_with_query() -> None:
    assert is_remote_iso_url("http://media.example/movie.iso?token=1") is True
    assert is_remote_iso_url("https://media.example/MOVIE.ISO") is True
    assert is_remote_iso_url("https://media.example/movie.mkv") is False
    assert is_remote_iso_url("/tmp/movie.iso") is False


def test_pick_main_feature_stream_prefers_largest_m2ts() -> None:
    streams = [
        BluRayIsoStream(path="/BDMV/STREAM/00001.m2ts", size=1048576),
        BluRayIsoStream(path="/BDMV/STREAM/00080.m2ts", size=8589934592),
        BluRayIsoStream(path="/BDMV/STREAM/00010.m2ts", size=2147483648),
    ]

    selected = pick_main_feature_stream(streams)

    assert selected.path == "/BDMV/STREAM/00080.m2ts"


def test_inspector_rejects_non_bluray_layout() -> None:
    inspector = BlurayIsoInspector(
        list_entries=lambda url, headers: [
            "/README.TXT",
            "/VIDEO_TS/VTS_01_1.VOB",
        ]
    )

    try:
        inspector.inspect("http://media.example/disc.iso", {})
    except ValueError as exc:
        assert str(exc) == "远程 ISO 不是受支持的 Blu-ray 目录结构"
    else:
        raise AssertionError("expected ValueError")


def test_bluray_iso_inspector_caches_prepare_playback_result() -> None:
    calls: list[tuple[str, dict[str, str]]] = []
    plan = bluray_iso.IsoPlaybackPlan(
        stream=BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=123),
        source=object(),
    )
    inspector = BlurayIsoInspector(
        prepare_playback=lambda url, headers: calls.append((url, dict(headers))) or plan,
    )

    first = inspector.prepare_playback("http://media.example/disc.iso", {"Referer": "https://site.example"})
    second = inspector.prepare_playback("http://media.example/disc.iso", {"Referer": "https://site.example"})

    assert first is plan
    assert second is plan
    assert calls == [
        ("http://media.example/disc.iso", {"Referer": "https://site.example"}),
    ]


def test_list_iso_entries_falls_back_to_udf_when_pycdlib_rejects_missing_pvd(monkeypatch) -> None:
    class FakeInvalidISO(Exception):
        pass

    class FakeReader:
        def __init__(self, url: str, headers: dict[str, str], *, get=None) -> None:
            del url, headers, get

        def _ensure_size(self) -> int:
            return 2048 * 600

    class FakePyCdlib:
        def __init__(self) -> None:
            self._has_udf = True
            self.logical_block_size = 2048
            self._cdfp = None
            self._initialized = False

        def open_fp(self, fp) -> None:
            self._cdfp = fp
            raise FakeInvalidISO("Valid ISO9660 filesystems must have at least one PVD")

        def _parse_udf_descriptors(self) -> None:
            self.udf_parsed = True

        def _walk_udf_directories(self, _extent_to_inode) -> None:
            self.udf_walked = True

        def walk(self, **kwargs):
            assert kwargs == {"udf_path": "/"}
            return [
                ("/", ["BDMV"], []),
                ("/BDMV", ["STREAM"], ["index.bdmv"]),
                ("/BDMV/STREAM", [], ["00080.m2ts"]),
            ]

        def close(self) -> None:
            return None

    fake_module = SimpleNamespace(
        PyCdlib=FakePyCdlib,
        pycdlibexception=SimpleNamespace(PyCdlibInvalidISO=FakeInvalidISO),
    )
    monkeypatch.setattr(bluray_iso, "_load_pycdlib", lambda: fake_module)
    monkeypatch.setattr(bluray_iso, "RemoteRangeReader", FakeReader)

    entries = bluray_iso.list_iso_entries("http://media.example/disc.iso", {})

    assert entries == [
        "/",
        "/BDMV",
        "/BDMV/INDEX.BDMV",
        "/BDMV/STREAM",
        "/BDMV/STREAM/00080.M2TS",
    ]


def test_list_iso_entries_falls_back_to_logical_volume_file_set_pointer(monkeypatch) -> None:
    class FakeInvalidISO(Exception):
        pass

    class FakeReader:
        def __init__(self, url: str, headers: dict[str, str], *, get=None) -> None:
            del url, headers, get

        def _ensure_size(self) -> int:
            return 2048 * 600

    class FakeCdfp:
        def __init__(self) -> None:
            self.position = 0

        def _ensure_size(self) -> int:
            return 2048 * 600

        def seek(self, offset: int, whence: int = 0) -> int:
            if whence != 0:
                raise AssertionError("unexpected whence")
            self.position = offset
            return self.position

        def read(self, length: int) -> bytes:
            assert self.position == 112 * 2048
            assert length == 4096
            return b"F" * length

    class FakePyCdlib:
        def __init__(self) -> None:
            self._has_udf = True
            self.logical_block_size = 2048
            self._cdfp = FakeCdfp()
            self._initialized = False

        def open_fp(self, fp) -> None:
            del fp
            raise FakeInvalidISO("Valid ISO9660 filesystems must have at least one PVD")

        def _seek_to_extent(self, extent: int) -> None:
            self._cdfp.seek(extent * self.logical_block_size)

        def _parse_udf_descriptors(self) -> None:
            self.udf_main_descs = SimpleNamespace(
                logical_volumes=[
                    SimpleNamespace(
                        logical_volume_contents_use=SimpleNamespace(log_block_num=12, part_ref_num=0)
                    )
                ],
                partitions=[SimpleNamespace(part_num=0, part_start_location=100, part_length=600)],
            )
            raise FakeInvalidISO("UDF File Set Tag identifier not 256")

        def _walk_udf_directories(self, _extent_to_inode) -> None:
            assert getattr(self, "udf_file_set", None) == "file-set"
            self.udf_walked = True

        def walk(self, **kwargs):
            assert kwargs == {"udf_path": "/"}
            return [
                ("/", ["BDMV"], []),
                ("/BDMV", ["STREAM"], ["index.bdmv"]),
                ("/BDMV/STREAM", [], ["00080.m2ts"]),
            ]

        def close(self) -> None:
            return None

    def fake_parse_file_set(data: bytes, current_extent: int, logical_block_size: int):
        assert data == b"F" * 4096
        assert current_extent == 112
        assert logical_block_size == 2048
        return "file-set", "file-set-terminator"

    fake_module = SimpleNamespace(
        PyCdlib=FakePyCdlib,
        pycdlibexception=SimpleNamespace(PyCdlibInvalidISO=FakeInvalidISO),
    )
    monkeypatch.setattr(bluray_iso, "_load_pycdlib", lambda: fake_module)
    monkeypatch.setattr(bluray_iso, "_load_pycdlib_udf", lambda: SimpleNamespace(parse_file_set=fake_parse_file_set))
    monkeypatch.setattr(bluray_iso, "RemoteRangeReader", FakeReader)

    entries = bluray_iso.list_iso_entries("http://media.example/disc.iso", {})

    assert entries == [
        "/",
        "/BDMV",
        "/BDMV/INDEX.BDMV",
        "/BDMV/STREAM",
        "/BDMV/STREAM/00080.M2TS",
    ]


def test_list_iso_entries_resolves_file_set_partition_via_partition_map(monkeypatch) -> None:
    class FakeInvalidISO(Exception):
        pass

    class FakeReader:
        def __init__(self, url: str, headers: dict[str, str], *, get=None) -> None:
            del url, headers, get

        def _ensure_size(self) -> int:
            return 2048 * 600

    class FakeCdfp:
        def __init__(self) -> None:
            self.position = 0

        def _ensure_size(self) -> int:
            return 2048 * 600

        def seek(self, offset: int, whence: int = 0) -> int:
            if whence != 0:
                raise AssertionError("unexpected whence")
            self.position = offset
            return self.position

        def read(self, length: int) -> bytes:
            assert self.position == 212 * 2048
            assert length == 4096
            return b"P" * length

    class FakePyCdlib:
        def __init__(self) -> None:
            self._has_udf = True
            self.logical_block_size = 2048
            self._cdfp = FakeCdfp()
            self._initialized = False

        def open_fp(self, fp) -> None:
            del fp
            raise FakeInvalidISO("Valid ISO9660 filesystems must have at least one PVD")

        def _seek_to_extent(self, extent: int) -> None:
            self._cdfp.seek(extent * self.logical_block_size)

        def _parse_udf_descriptors(self) -> None:
            self.udf_main_descs = SimpleNamespace(
                logical_volumes=[
                    SimpleNamespace(
                        logical_volume_contents_use=SimpleNamespace(log_block_num=12, part_ref_num=1),
                        partition_maps=[
                            SimpleNamespace(part_num=7),
                            SimpleNamespace(part_num=0),
                        ],
                    )
                ],
                partitions=[SimpleNamespace(part_num=0, part_start_location=200, part_length=600)],
            )
            raise FakeInvalidISO("UDF File Set Tag identifier not 256")

        def _walk_udf_directories(self, _extent_to_inode) -> None:
            assert getattr(self, "udf_file_set", None) == "file-set"

        def walk(self, **kwargs):
            assert kwargs == {"udf_path": "/"}
            return [
                ("/", ["BDMV"], []),
                ("/BDMV", ["STREAM"], ["index.bdmv"]),
                ("/BDMV/STREAM", [], ["00080.m2ts"]),
            ]

        def close(self) -> None:
            return None

    def fake_parse_file_set(data: bytes, current_extent: int, logical_block_size: int):
        assert data == b"P" * 4096
        assert current_extent == 212
        assert logical_block_size == 2048
        return "file-set", "file-set-terminator"

    fake_module = SimpleNamespace(
        PyCdlib=FakePyCdlib,
        pycdlibexception=SimpleNamespace(PyCdlibInvalidISO=FakeInvalidISO),
    )
    monkeypatch.setattr(bluray_iso, "_load_pycdlib", lambda: fake_module)
    monkeypatch.setattr(bluray_iso, "_load_pycdlib_udf", lambda: SimpleNamespace(parse_file_set=fake_parse_file_set))
    monkeypatch.setattr(bluray_iso, "RemoteRangeReader", FakeReader)

    entries = bluray_iso.list_iso_entries("http://media.example/disc.iso", {})

    assert entries == [
        "/",
        "/BDMV",
        "/BDMV/INDEX.BDMV",
        "/BDMV/STREAM",
        "/BDMV/STREAM/00080.M2TS",
    ]


def test_parse_udf_metadata_partition_map_reads_underlying_partition_and_file_location() -> None:
    metadata_map = _parse_udf_metadata_partition_map(
        bytes.fromhex(
            "0000002a554446204d6574616461746120506172746974696f6e5002000000000000010000000000000073505e01ffffffff200000002000010000000000"
        )
    )

    assert metadata_map.part_num == 0
    assert metadata_map.metadata_file_location == 0


def test_map_udf_partition_block_direct_uses_metadata_extents() -> None:
    resolver = _UdfPartitionResolver(
        part_ref_num=1,
        physical_partition_start=288,
        extents=(
            _UdfPartitionExtent(logical_start_block=0, block_count=384, physical_start_block=320),
            _UdfPartitionExtent(logical_start_block=384, block_count=16, physical_start_block=800),
        ),
    )

    assert _map_udf_partition_block_direct(resolver, 0) == 320
    assert _map_udf_partition_block_direct(resolver, 383) == 703
    assert _map_udf_partition_block_direct(resolver, 384) == 800


def test_remote_range_reader_coalesces_small_reads_with_window_cache() -> None:
    remote_bytes = bytes(range(256)) * 2
    requests: list[str] = []

    class FakeResponse:
        def __init__(self, start: int, end: int, total_size: int, payload: bytes) -> None:
            self.status_code = 206
            self.headers = {"Content-Range": f"bytes {start}-{end}/{total_size}"}
            self.content = payload

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, headers: dict[str, str], *, timeout: float, follow_redirects: bool):
        del url, timeout, follow_redirects
        range_header = headers["Range"]
        requests.append(range_header)
        start, end = map(int, range_header.removeprefix("bytes=").split("-", 1))
        bounded_end = min(end, len(remote_bytes) - 1)
        return FakeResponse(
            start,
            bounded_end,
            len(remote_bytes),
            remote_bytes[start : bounded_end + 1],
        )

    reader = bluray_iso.RemoteRangeReader(
        "http://media.example/disc.iso",
        {},
        get=fake_get,
        range_cache=bluray_iso.create_iso_stream_range_cache(
            window_size=128,
            startup_window_size=128,
            startup_request_threshold=128,
            max_windows=2,
        ),
    )

    reader.seek(32)
    assert reader.read(8) == remote_bytes[32:40]
    reader.seek(100)
    assert reader.read(8) == remote_bytes[100:108]
    reader.seek(160)
    assert reader.read(8) == remote_bytes[160:168]

    assert requests == [
        "bytes=0-0",
        "bytes=32-159",
        "bytes=160-287",
    ]


def test_create_iso_parse_range_cache_uses_half_mebibyte_windows() -> None:
    cache = bluray_iso.create_iso_parse_range_cache()

    assert isinstance(cache, bluray_iso._RemoteRangeWindowCache)
    assert cache.window_size == 512 * 1024
    assert cache.startup_window_size == 512 * 1024
    assert cache.startup_request_threshold == 512 * 1024
    assert cache.max_windows == 16


def _build_test_mpls(play_items: list[tuple[str, int, int]]) -> bytes:
    playlist_body = bytearray(b"\x00\x00")
    playlist_body.extend(len(play_items).to_bytes(2, "big"))
    playlist_body.extend((0).to_bytes(2, "big"))
    for clip_name, in_time, out_time in play_items:
        item = bytearray()
        item.extend(clip_name.encode("ascii"))
        item.extend(b"M2TS")
        item.extend(b"\x00\x00")
        item.extend(b"\x00")
        item.extend(int(in_time).to_bytes(4, "big"))
        item.extend(int(out_time).to_bytes(4, "big"))
        item.extend(b"\x00" * 8)
        item.extend(b"\x00")
        item.extend(b"\x00")
        item.extend(b"\x00\x00")
        item.extend((0).to_bytes(2, "big"))
        playlist_body.extend(len(item).to_bytes(2, "big"))
        playlist_body.extend(item)
    playlist_section = len(playlist_body).to_bytes(4, "big") + playlist_body
    playlist_start = 20
    header = bytearray(b"MPLS0200")
    header.extend(playlist_start.to_bytes(4, "big"))
    header.extend((0).to_bytes(4, "big"))
    header.extend((0).to_bytes(4, "big"))
    return bytes(header + playlist_section)


_REAL_CLPI_00004_HEX = """
48444d5630333030000000dc000000f600000134000001b400000000000000000000000000000000
000000b0000001010000000000f3f32c000702800000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000001e8048444d560000000000
0000000000000000000000000000000000000000000000160001000000000100100100000000019b
fcc001a4aa350000003a000100000000010002001011152481301200303030303030303030303030
000000001100158361656e67303030303030303030303030000000000000007c0001000110110004
0018000e0000000e00000034000000660000000400004067000003140001c0680001c93800020068
00029e3f000280680004450d0003406900065d8e17f80004195803141ab80a321ae40c741c4444f8
1da49cf51f0516621065c93811c49e3f132578ee1484450d15e5095a1745f5a818025d8e00000000
""".strip().replace("\n", "")


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


def test_parse_clpi_extracts_entry_points() -> None:
    parsed = bluray_iso._parse_clpi_entry_points(
        "00004",
        bytes.fromhex(_REAL_CLPI_00004_HEX),
    )

    assert parsed.clip_id == "00004"
    assert len(parsed.entry_points) == 14
    assert parsed.entry_points[:5] == (
        bluray_iso._ClpiEntryPoint(time_45k=26999808, byte_offset=768),
        bluray_iso._ClpiEntryPoint(time_45k=27044864, byte_offset=151296),
        bluray_iso._ClpiEntryPoint(time_45k=27089920, byte_offset=501120),
        bluray_iso._ClpiEntryPoint(time_45k=27095552, byte_offset=612096),
        bluray_iso._ClpiEntryPoint(time_45k=27140608, byte_offset=3389952),
    )
    assert parsed.entry_points[-1] == bluray_iso._ClpiEntryPoint(
        time_45k=27525376,
        byte_offset=80095872,
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

    assert bluray_iso._compute_trimmed_clip_range(parsed_clpi, 1, 179999, 2000) == (192, 1536)


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


def test_compose_cached_iso_stream_source_rebases_segments_for_virtual_playlist() -> None:
    composed = bluray_iso._compose_cached_iso_stream_sources(
        [
            bluray_iso._CachedIsoStreamSource(
                size=6,
                segments=(
                    bluray_iso._CachedIsoSegment(logical_offset=0, length=4, physical_start=100),
                    bluray_iso._CachedIsoSegment(logical_offset=4, length=2, physical_start=500),
                ),
            ),
            bluray_iso._CachedIsoStreamSource(
                size=3,
                segments=(
                    bluray_iso._CachedIsoSegment(logical_offset=0, length=3, physical_start=900),
                ),
            ),
        ]
    )

    assert composed.size == 9
    assert composed.segments == (
        bluray_iso._CachedIsoSegment(logical_offset=0, length=4, physical_start=100),
        bluray_iso._CachedIsoSegment(logical_offset=4, length=2, physical_start=500),
        bluray_iso._CachedIsoSegment(logical_offset=6, length=3, physical_start=900),
    )


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
                    bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=1152),
                ),
            ),
            "00002": bluray_iso._ParsedClpi(
                clip_id="00002",
                entry_points=(
                    bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=192),
                    bluray_iso._ClpiEntryPoint(time_45k=180000, byte_offset=576),
                    bluray_iso._ClpiEntryPoint(time_45k=270000, byte_offset=960),
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
    assert plan.stream.size == 1536
    assert plan.source == bluray_iso._CachedIsoStreamSource(
        size=1536,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=768, physical_start=1384),
            bluray_iso._CachedIsoSegment(logical_offset=768, length=768, physical_start=4192),
        ),
    )


def test_prepare_iso_playback_skips_short_leading_intro_clips_before_main_feature(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    sources = {
        "/BDMV/STREAM/00001.M2TS": bluray_iso._CachedIsoStreamSource(
            size=1024,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1024, physical_start=1000),),
        ),
        "/BDMV/STREAM/00002.M2TS": bluray_iso._CachedIsoStreamSource(
            size=1024,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=1024, physical_start=3000),),
        ),
        "/BDMV/STREAM/00003.M2TS": bluray_iso._CachedIsoStreamSource(
            size=4096,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=4096, physical_start=5000),),
        ),
        "/BDMV/STREAM/00004.M2TS": bluray_iso._CachedIsoStreamSource(
            size=2048,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=2048, physical_start=10000),),
        ),
    }

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            (
                "/BDMV/PLAYLIST/00002.MPLS",
                _build_test_mpls(
                        [
                            ("00001", 0, 45000),
                            ("00002", 0, 90000),
                            ("00003", 0, 54000000),
                            ("00004", 0, 27000000),
                        ]
                    ),
                ),
            ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(bluray_iso, "_build_cached_iso_stream_source", lambda iso, entry_ref: sources[entry_ref.path])
    monkeypatch.setattr(
        bluray_iso,
        "_read_remote_udf_clipinfo",
        lambda iso, clip_id: bluray_iso._ParsedClpi(
            clip_id=clip_id,
            entry_points=(
                bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=0),
                bluray_iso._ClpiEntryPoint(time_45k=72000000, byte_offset=sources[f"/BDMV/STREAM/{clip_id}.M2TS"].size),
            ),
        ),
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00003.M2TS"
    assert plan.source == bluray_iso._CachedIsoStreamSource(
        size=6144,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=4096, physical_start=5000),
            bluray_iso._CachedIsoSegment(logical_offset=4096, length=2048, physical_start=10000),
        ),
    )
    assert plan.playlist_segments == (
        bluray_iso.IsoPlaybackSegment(
            stream_path="/BDMV/STREAM/00003.M2TS",
            stream_size=4096,
            duration_seconds=1200.0,
            source=sources["/BDMV/STREAM/00003.M2TS"],
        ),
        bluray_iso.IsoPlaybackSegment(
            stream_path="/BDMV/STREAM/00004.M2TS",
            stream_size=2048,
            duration_seconds=600.0,
            source=sources["/BDMV/STREAM/00004.M2TS"],
        ),
    )


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
            (
                "/BDMV/PLAYLIST/00001.MPLS",
                _build_test_mpls([("00080", 0, 90000)]),
            ),
            (
                "/BDMV/PLAYLIST/00002.MPLS",
                _build_test_mpls([("00001", 0, 90000), ("00002", 0, 180000)]),
            ),
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
                bluray_iso._ClpiEntryPoint(time_45k=270000, byte_offset=960),
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
            ("/BDMV/PLAYLIST/00003.MPLS", _build_test_mpls([("00080", 0, 360000)])),
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
                bluray_iso._ClpiEntryPoint(time_45k=270000, byte_offset=960),
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
    assert plan.stream.size == 1152


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
    monkeypatch.setattr(
        bluray_iso,
        "_read_remote_udf_clipinfo",
        lambda iso, clip_id: (_ for _ in ()).throw(ValueError("bad clpi")),
    )
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [
            BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=20),
            BluRayIsoStream(path="/BDMV/STREAM/00010.M2TS", size=10),
        ],
    )

    def fake_find_remote_udf_entry(iso, path):
        return SimpleNamespace(path=path, record=SimpleNamespace())

    def fake_build_cached_iso_stream_source(iso, entry_ref):
        size = 20 if entry_ref.path.endswith("00080.M2TS") else 10
        return bluray_iso._CachedIsoStreamSource(
            size=size,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=size, physical_start=300),),
        )

    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", fake_find_remote_udf_entry)
    monkeypatch.setattr(bluray_iso, "_build_cached_iso_stream_source", fake_build_cached_iso_stream_source)

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream == BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=20)


def test_prepare_iso_playback_ignores_looping_playlist_that_repeats_same_clip_window(monkeypatch) -> None:
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
            (
                "/BDMV/PLAYLIST/00000.MPLS",
                _build_test_mpls([("00000", 27000000, 29702700)] * 249),
            ),
            (
                "/BDMV/PLAYLIST/00020.MPLS",
                _build_test_mpls([("00011", 27000000, 359537205)]),
            ),
        ],
    )

    monkeypatch.setattr(
        bluray_iso,
        "_build_trimmed_playlist_clip_source",
        lambda iso, play_item: bluray_iso._CachedIsoStreamSource(
            size=play_item.duration,
            segments=(
                bluray_iso._CachedIsoSegment(
                    logical_offset=0,
                    length=play_item.duration,
                    physical_start=1000,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00011.M2TS", size=359537205)],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: bluray_iso._CachedIsoStreamSource(
            size=359537205,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=359537205, physical_start=1000),),
        ),
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00011.M2TS"
    assert plan.playlist_segments == ()


def test_prepare_iso_playback_ignores_small_looping_playlist_that_repeats_same_clip_window(monkeypatch) -> None:
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
            (
                "/BDMV/PLAYLIST/00001.MPLS",
                _build_test_mpls([("00001", 0, 313648335)] * 5),
            ),
            (
                "/BDMV/PLAYLIST/00080.MPLS",
                _build_test_mpls([("00080", 0, 496800000)]),
            ),
        ],
    )
    monkeypatch.setattr(
        bluray_iso,
        "_build_trimmed_playlist_clip_source",
        lambda iso, play_item: bluray_iso._CachedIsoStreamSource(
            size=play_item.duration,
            segments=(
                bluray_iso._CachedIsoSegment(
                    logical_offset=0,
                    length=play_item.duration,
                    physical_start=1000,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=496800000)],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: bluray_iso._CachedIsoStreamSource(
            size=496800000,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=496800000, physical_start=1000),),
        ),
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00080.M2TS"
    assert plan.playlist_segments == ()


def test_prepare_iso_playback_prefers_larger_feature_payload_over_slightly_longer_bonus_playlist(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    sources = {
        "/BDMV/STREAM/00010.M2TS": bluray_iso._CachedIsoStreamSource(
            size=800 * 1024 * 1024,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=800 * 1024 * 1024, physical_start=1000),),
        ),
        "/BDMV/STREAM/00080.M2TS": bluray_iso._CachedIsoStreamSource(
            size=30 * 1024 * 1024 * 1024,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=30 * 1024 * 1024 * 1024, physical_start=5000),),
        ),
    }

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: remote_iso)
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_iter_remote_udf_playlists",
        lambda iso: [
            ("/BDMV/PLAYLIST/00090.MPLS", _build_test_mpls([("00010", 0, 95 * 60 * 45000)])),
            ("/BDMV/PLAYLIST/00080.MPLS", _build_test_mpls([("00080", 0, 92 * 60 * 45000)])),
        ],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(bluray_iso, "_build_cached_iso_stream_source", lambda iso, entry_ref: sources[entry_ref.path])
    monkeypatch.setattr(
        bluray_iso,
        "_read_remote_udf_clipinfo",
        lambda iso, clip_id: bluray_iso._ParsedClpi(
            clip_id=clip_id,
            entry_points=(
                bluray_iso._ClpiEntryPoint(time_45k=0, byte_offset=0),
                bluray_iso._ClpiEntryPoint(
                    time_45k=100 * 60 * 45000,
                    byte_offset=sources[f"/BDMV/STREAM/{clip_id}.M2TS"].size,
                ),
            ),
        ),
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00080.M2TS"
    assert plan.stream.size == 30 * 1024 * 1024 * 1024


def test_prepare_iso_playback_resolves_plain_udf_paths_case_insensitively(monkeypatch) -> None:
    class FakeIsoFile:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def seek(self, offset: int) -> None:
            assert offset == 0

        def read(self, length: int) -> bytes:
            assert length == 4
            return b"data"

    class FakeRecord:
        def get_data_length(self) -> int:
            return 4

    class FakeIso:
        def walk(self, **kwargs):
            assert kwargs == {"udf_path": "/"}
            return [
                ("/", ["bdmv"], []),
                ("/bdmv", ["stream"], ["index.bdmv"]),
                ("/bdmv/stream", [], ["00080.m2ts"]),
            ]

        def get_record(self, *, udf_path: str):
            if udf_path != "/bdmv/stream/00080.m2ts":
                raise ValueError("Could not find path")
            return FakeRecord()

        def open_file_from_iso(self, *, udf_path: str):
            if udf_path != "/bdmv/stream/00080.m2ts":
                raise ValueError("Could not find path")
            return FakeIsoFile()

        def close(self) -> None:
            return None

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: FakeIso())
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})
    payload, total_size = bluray_iso.read_iso_stream_range(
        "http://media.example/disc.iso",
        {},
        "/BDMV/STREAM/00080.M2TS",
        0,
        None,
    )

    assert plan.stream == BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=4)
    assert payload == b"data"
    assert total_size == 4


def test_prepare_iso_playback_promotes_plain_udf_iso_to_cached_remote_source(monkeypatch) -> None:
    class FakeIso:
        _has_udf = True
        udf_main_descs = object()
        udf_file_set = object()

        def close(self) -> None:
            return None

    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    cached_source = bluray_iso._CachedIsoStreamSource(
        size=4096,
        segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=4096, physical_start=8192),),
    )

    monkeypatch.setattr(bluray_iso, "_open_pycdlib_iso", lambda reader: FakeIso())
    monkeypatch.setattr(bluray_iso, "_safe_close_iso", lambda iso: None)
    monkeypatch.setattr(bluray_iso, "_build_remote_udf_iso", lambda reader, iso: remote_iso)
    monkeypatch.setattr(bluray_iso, "_prepare_remote_udf_playlist_playback", lambda iso: None)
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=4096)],
    )
    monkeypatch.setattr(bluray_iso, "_find_remote_udf_entry", lambda iso, path: SimpleNamespace(path=path))
    monkeypatch.setattr(bluray_iso, "_build_cached_iso_stream_source", lambda iso, entry_ref: cached_source)

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream == BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=4096)
    assert plan.source == cached_source
