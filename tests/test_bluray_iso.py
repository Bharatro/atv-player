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


def test_parse_mpls_playlist_extracts_clip_sequence_and_duration() -> None:
    parsed = bluray_iso._parse_mpls_playlist(
        _build_test_mpls(
            [
                ("00003", 90000, 180000),
                ("00004", 0, 270000),
            ]
        )
    )

    assert parsed.clip_paths == (
        "/BDMV/STREAM/00003.M2TS",
        "/BDMV/STREAM/00004.M2TS",
    )
    assert parsed.duration == 360000


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


def test_prepare_iso_playback_prefers_largest_clip_from_longest_playlist_for_remote_udf(monkeypatch) -> None:
    remote_iso = bluray_iso._RemoteUdfIso(
        reader=SimpleNamespace(),
        logical_block_size=2048,
        main_descs=None,
        file_set=None,
        partition_resolvers=(),
    )
    sources = {
        "/BDMV/STREAM/00001.M2TS": bluray_iso._CachedIsoStreamSource(
            size=5,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=5, physical_start=100),),
        ),
        "/BDMV/STREAM/00002.M2TS": bluray_iso._CachedIsoStreamSource(
            size=7,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=7, physical_start=200),),
        ),
        "/BDMV/STREAM/00080.M2TS": bluray_iso._CachedIsoStreamSource(
            size=20,
            segments=(bluray_iso._CachedIsoSegment(logical_offset=0, length=20, physical_start=300),),
        ),
    }

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
    monkeypatch.setattr(
        bluray_iso,
        "_find_remote_udf_entry",
        lambda iso, path: SimpleNamespace(path=path),
    )
    monkeypatch.setattr(
        bluray_iso,
        "_build_cached_iso_stream_source",
        lambda iso, entry_ref: sources[entry_ref.path],
    )
    monkeypatch.setattr(
        bluray_iso,
        "_stat_remote_udf_streams",
        lambda iso: [
            BluRayIsoStream(path="/BDMV/STREAM/00080.M2TS", size=20),
            BluRayIsoStream(path="/BDMV/STREAM/00001.M2TS", size=5),
            BluRayIsoStream(path="/BDMV/STREAM/00002.M2TS", size=7),
        ],
    )

    plan = bluray_iso.prepare_iso_playback("http://media.example/disc.iso", {})

    assert plan.stream.path == "/BDMV/STREAM/00002.M2TS"
    assert plan.stream.size == 7
    assert plan.source == bluray_iso._CachedIsoStreamSource(
        size=7,
        segments=(
            bluray_iso._CachedIsoSegment(logical_offset=0, length=7, physical_start=200),
        ),
    )
