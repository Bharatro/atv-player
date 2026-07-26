from pathlib import Path

import pytest

import atv_player.danmaku.cache as danmaku_cache_module
import atv_player.danmaku.generic as generic_danmaku_module
from atv_player.danmaku.generic import GenericDanmakuController
from atv_player.danmaku.models import (
    DanmakuSourceGroup,
    DanmakuSourceOption,
    DanmakuSourceSearchResult,
)
from atv_player.danmaku.preferences import DanmakuSeriesPreferenceStore
from atv_player.models import PlayItem


@pytest.mark.parametrize(
    "value",
    ["", "v.qq.com/x/1", "ftp://v.qq.com/x/1", "https:///x/1"],
)
def test_normalize_danmaku_episode_url_rejects_incomplete_urls(value: str) -> None:
    with pytest.raises(ValueError, match=r"完整的 http\(s\) 单集链接"):
        generic_danmaku_module.normalize_danmaku_episode_url(value)


def test_normalize_danmaku_episode_url_strips_surrounding_whitespace() -> None:
    assert (
        generic_danmaku_module.normalize_danmaku_episode_url(
            "  https://v.qq.com/x/cover/demo/ep1.html  "
        )
        == "https://v.qq.com/x/cover/demo/ep1.html"
    )


def test_generic_controller_downloads_episode_url_without_replacing_candidates(
    monkeypatch,
) -> None:
    class RecordingService:
        def __init__(self) -> None:
            self.resolve_calls: list[str] = []

        def provider_key_for_url(self, page_url: str) -> str:
            assert page_url == "https://v.qq.com/x/cover/demo/ep1.html"
            return "tencent"

        def resolve_danmu(self, page_url: str) -> str:
            self.resolve_calls.append(page_url)
            return '<i><d p="1,1,25,16777215">manual</d></i>'

    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_xml",
        lambda _name, _url: "",
    )
    monkeypatch.setattr(
        generic_danmaku_module,
        "save_cached_danmaku_xml",
        lambda name, url, xml: saved.append((name, url, xml)),
    )
    candidates = [
        DanmakuSourceGroup(
            provider="youku",
            provider_label="优酷",
            options=[
                DanmakuSourceOption(
                    provider="youku",
                    name="旧候选",
                    url="https://youku/old",
                )
            ],
        )
    ]
    service = RecordingService()
    controller = GenericDanmakuController(service)
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        vod_id="item-1",
        media_title="成何体统",
        danmaku_search_query="成何体统 1集",
        danmaku_candidates=candidates,
    )

    xml = controller.download_danmaku_from_url(
        item,
        "  https://v.qq.com/x/cover/demo/ep1.html  ",
    )

    assert "manual" in xml
    assert service.resolve_calls == ["https://v.qq.com/x/cover/demo/ep1.html"]
    assert item.danmaku_candidates is candidates
    assert item.selected_danmaku_provider == "tencent"
    assert item.selected_danmaku_url == "https://v.qq.com/x/cover/demo/ep1.html"
    assert item.selected_danmaku_title == "第1集"
    assert [(name, url) for name, url, _xml in saved] == [
        ("成何体统 1集", "https://v.qq.com/x/cover/demo/ep1.html"),
        ("成何体统 1集", "item-1"),
    ]


def test_generic_controller_episode_url_failure_preserves_loaded_source(
    monkeypatch,
) -> None:
    class FailingService:
        def provider_key_for_url(self, _page_url: str) -> str:
            return "tencent"

        def resolve_danmu(self, _page_url: str) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_xml",
        lambda _name, _url: "",
    )
    controller = GenericDanmakuController(FailingService())
    candidates = [
        DanmakuSourceGroup(provider="youku", provider_label="优酷", options=[])
    ]
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        media_title="成何体统",
        danmaku_search_query="成何体统 1集",
        danmaku_candidates=candidates,
        danmaku_xml="<i>old</i>",
        selected_danmaku_provider="youku",
        selected_danmaku_url="https://youku/old",
        selected_danmaku_title="旧来源",
    )

    with pytest.raises(RuntimeError, match="boom"):
        controller.download_danmaku_from_url(
            item,
            "https://v.qq.com/x/cover/demo/ep1.html",
        )

    assert item.danmaku_candidates is candidates
    assert item.danmaku_xml == "<i>old</i>"
    assert item.selected_danmaku_provider == "youku"
    assert item.selected_danmaku_url == "https://youku/old"
    assert item.selected_danmaku_title == "旧来源"


def test_generic_danmaku_controller_delegates_episode_offset(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")
    controller = GenericDanmakuController(object(), danmaku_preference_store=store)
    item = PlayItem(
        title="第12集",
        url="",
        media_title="剑来",
        selected_danmaku_provider="tencent",
    )

    controller.save_danmaku_offset(item, -2.5, playlist=[item])

    assert controller.load_danmaku_offset(item, playlist=[item]) == -2.5
    assert item.danmaku_offset_seconds == -2.5


def test_generic_danmaku_controller_refreshes_sources_with_media_title_and_episode(monkeypatch, tmp_path: Path) -> None:
    class RecordingDanmakuService:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str, str]] = []

        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
            provider_filter: str = "",
        ) -> DanmakuSourceSearchResult:
            del preferred_provider, preferred_page_url, media_duration_seconds
            self.search_calls.append((name, reg_src, provider_filter))
            return DanmakuSourceSearchResult(
                groups=[
                    DanmakuSourceGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        options=[DanmakuSourceOption(provider="tencent", name="成何体统 第1集", url="https://v.qq.com/demo")],
                    )
                ],
                default_option_url="https://v.qq.com/demo",
                default_provider="tencent",
            )

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_source_search_result",
        danmaku_cache_module.load_cached_danmaku_source_search_result,
    )
    monkeypatch.setattr(
        generic_danmaku_module,
        "save_cached_danmaku_source_search_result",
        danmaku_cache_module.save_cached_danmaku_source_search_result,
    )
    service = RecordingDanmakuService()
    controller = GenericDanmakuController(service)
    item = PlayItem(title="第1集", url="https://media.example/1.m3u8", vod_id="item-1", media_title="成何体统 (2026)", index=0)

    controller.refresh_danmaku_sources(item, playlist=[item], force_refresh=True, provider_filter="tencent")

    assert service.search_calls == [("成何体统 (2026) 1集", "item-1", "tencent")]
    assert item.danmaku_search_title == "成何体统 (2026)"
    assert item.danmaku_search_episode == "1集"
    assert item.danmaku_search_query == "成何体统 (2026) 1集"
    assert item.selected_danmaku_provider == "tencent"
    assert item.selected_danmaku_url == "https://v.qq.com/demo"
    assert item.selected_danmaku_title == "成何体统 第1集"


def test_generic_danmaku_controller_refresh_emits_log_events(monkeypatch, tmp_path: Path) -> None:
    class RecordingDanmakuService:
        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
            provider_filter: str = "",
        ) -> DanmakuSourceSearchResult:
            del reg_src, preferred_provider, preferred_page_url, media_duration_seconds, provider_filter
            assert name == "成何体统 1集"
            return DanmakuSourceSearchResult(
                groups=[
                    DanmakuSourceGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        options=[DanmakuSourceOption(provider="tencent", name="成何体统 第1集", url="https://v.qq.com/demo")],
                    )
                ],
                default_option_url="https://v.qq.com/demo",
                default_provider="tencent",
            )

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_source_search_result",
        danmaku_cache_module.load_cached_danmaku_source_search_result,
    )
    monkeypatch.setattr(
        generic_danmaku_module,
        "save_cached_danmaku_source_search_result",
        danmaku_cache_module.save_cached_danmaku_source_search_result,
    )
    controller = GenericDanmakuController(RecordingDanmakuService())
    logs: list[str] = []
    controller.set_danmaku_log_handler(logs.append)
    item = PlayItem(title="第1集", url="https://media.example/1.m3u8", vod_id="item-1", media_title="成何体统")

    controller.refresh_danmaku_sources(item, playlist=[item], force_refresh=True)

    assert logs == [
        "弹幕搜索中: 成何体统 1集",
        "弹幕搜索成功: 找到 1 个候选",
    ]


def test_generic_danmaku_controller_refresh_emits_all_actual_search_queries(monkeypatch, tmp_path: Path) -> None:
    class RecordingDanmakuService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
            provider_filter: str = "",
        ) -> DanmakuSourceSearchResult:
            del reg_src, preferred_provider, preferred_page_url, media_duration_seconds, provider_filter
            self.calls.append(name)
            if name == "成何体统 1集":
                return DanmakuSourceSearchResult(groups=[], default_option_url="", default_provider="")
            if name == "成何体统":
                return DanmakuSourceSearchResult(
                    groups=[
                        DanmakuSourceGroup(
                            provider="iqiyi",
                            provider_label="爱奇艺",
                            options=[DanmakuSourceOption(provider="iqiyi", name="成何体统 第1集", url="https://www.iqiyi.com/v_ep1.html")],
                        )
                    ],
                    default_option_url="https://www.iqiyi.com/v_ep1.html",
                    default_provider="iqiyi",
                )
            raise AssertionError(name)

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_source_search_result",
        danmaku_cache_module.load_cached_danmaku_source_search_result,
    )
    monkeypatch.setattr(
        generic_danmaku_module,
        "save_cached_danmaku_source_search_result",
        danmaku_cache_module.save_cached_danmaku_source_search_result,
    )
    service = RecordingDanmakuService()
    controller = GenericDanmakuController(service)
    logs: list[str] = []
    controller.set_danmaku_log_handler(logs.append)
    item = PlayItem(title="第1集", url="https://media.example/1.m3u8", vod_id="item-1", media_title="成何体统")

    controller.refresh_danmaku_sources(item, playlist=[item], force_refresh=True)

    assert service.calls == ["成何体统 1集", "成何体统"]
    assert logs == [
        "弹幕搜索中: 成何体统 1集",
        "弹幕搜索中: 成何体统",
        "弹幕搜索成功: 找到 1 个候选",
    ]


def test_generic_danmaku_controller_switches_to_cached_xml_without_refetch(monkeypatch, tmp_path: Path) -> None:
    class FailingResolveDanmakuService:
        def search_danmu_sources(
            self,
            name: str,
            reg_src: str = "",
            preferred_provider: str = "",
            preferred_page_url: str = "",
            media_duration_seconds: int = 0,
            provider_filter: str = "",
        ) -> DanmakuSourceSearchResult:
            del name, reg_src, preferred_provider, preferred_page_url, media_duration_seconds, provider_filter
            return DanmakuSourceSearchResult(
                groups=[
                    DanmakuSourceGroup(
                        provider="tencent",
                        provider_label="腾讯",
                        options=[DanmakuSourceOption(provider="tencent", name="成何体统", url="https://v.qq.com/demo")],
                    )
                ],
                default_option_url="https://v.qq.com/demo",
                default_provider="tencent",
            )

        def resolve_danmu(self, page_url: str, option=None) -> str:
            raise AssertionError(f"should use cached xml instead of resolving {page_url!r} with {option!r}")

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    monkeypatch.setattr(
        generic_danmaku_module,
        "load_cached_danmaku_source_search_result",
        danmaku_cache_module.load_cached_danmaku_source_search_result,
    )
    monkeypatch.setattr(
        generic_danmaku_module,
        "save_cached_danmaku_source_search_result",
        danmaku_cache_module.save_cached_danmaku_source_search_result,
    )
    controller = GenericDanmakuController(FailingResolveDanmakuService())
    item = PlayItem(title="正片", url="https://media.example/movie.m3u8", vod_id="item-1", media_title="成何体统 (2026)")
    xml_text = '<?xml version="1.0" encoding="UTF-8"?><i><d p="0,1,25,16777215">第一条</d></i>'

    controller.refresh_danmaku_sources(item, playlist=[item], force_refresh=True)
    danmaku_cache_module.save_cached_danmaku_xml(item.danmaku_search_query, "https://v.qq.com/demo", xml_text)

    resolved = controller.switch_danmaku_source(item, "https://v.qq.com/demo")

    assert resolved == xml_text
    assert item.danmaku_xml == xml_text


def test_generic_danmaku_controller_switch_emits_log_events(monkeypatch, tmp_path: Path) -> None:
    class ResolveDanmakuService:
        def resolve_danmu(self, page_url: str, option=None) -> str:
            del option
            assert page_url == "https://v.qq.com/demo"
            return '<?xml version="1.0" encoding="UTF-8"?><i><d p="0,1,25,16777215">第一条</d></i>'

    monkeypatch.setattr(danmaku_cache_module, "app_cache_dir", lambda: tmp_path / "app-cache")
    monkeypatch.setattr(generic_danmaku_module, "load_cached_danmaku_xml", danmaku_cache_module.load_cached_danmaku_xml)
    monkeypatch.setattr(generic_danmaku_module, "save_cached_danmaku_xml", danmaku_cache_module.save_cached_danmaku_xml)
    controller = GenericDanmakuController(ResolveDanmakuService())
    logs: list[str] = []
    controller.set_danmaku_log_handler(logs.append)
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        vod_id="item-1",
        media_title="成何体统",
        danmaku_search_query="成何体统 1集",
        danmaku_candidates=[
            DanmakuSourceGroup(
                provider="tencent",
                provider_label="腾讯",
                options=[DanmakuSourceOption(provider="tencent", name="成何体统 第1集", url="https://v.qq.com/demo")],
            )
        ],
    )

    controller.switch_danmaku_source(item, "https://v.qq.com/demo")

    assert logs == [
        "弹幕下载中: 腾讯 - 成何体统 第1集",
        "弹幕下载成功: 1 条弹幕",
    ]
