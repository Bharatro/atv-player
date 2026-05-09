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
