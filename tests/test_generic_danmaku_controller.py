from pathlib import Path

import atv_player.danmaku.cache as danmaku_cache_module
import atv_player.danmaku.generic as generic_danmaku_module
from atv_player.danmaku.generic import GenericDanmakuController
from atv_player.danmaku.models import DanmakuSourceGroup, DanmakuSourceOption, DanmakuSourceSearchResult
from atv_player.models import PlayItem


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
