from types import SimpleNamespace

import atv_player.player.bluray_iso as bluray_iso
from atv_player.player.bluray_iso import (
    BluRayIsoStream,
    BlurayIsoInspector,
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
