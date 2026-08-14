import pytest

from atv_player.subtitles.errors import (
    SubtitleBlockedError,
    SubtitleProviderError,
)
from atv_player.subtitles.languages import CHS, CHS_ENG, ENG
from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleQuery,
    SubtitleSearchItem,
)
from atv_player.subtitles.service import (
    SubtitleSearchService,
    build_subtitle_query,
    episode_of,
)


class FakeProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        label: str = "",
        items: list[SubtitleSearchItem] | None = None,
        error: Exception | None = None,
        available: bool = True,
        requires_token: bool = False,
        notice: str = "",
    ) -> None:
        self.provider_id = provider_id
        self.label = label or provider_id
        self.requires_token = requires_token
        self.notice = notice
        self._items = items or []
        self._error = error
        self._available = available
        self.searched = 0

    def available(self) -> bool:
        return self._available

    def search(self, query: SubtitleQuery) -> list[SubtitleSearchItem]:
        self.searched += 1
        if self._error is not None:
            raise self._error
        return list(self._items)

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        return SubtitleContent(
            text="1\n00:00:01,000 --> 00:00:02,000\nhi\n", suffix=".srt"
        )


def _item(provider: str, subtitle_id: str, **kwargs) -> SubtitleSearchItem:
    base = {
        "provider": provider,
        "provider_label": provider,
        "subtitle_id": subtitle_id,
        "name": "Show",
    }
    base.update(kwargs)
    return SubtitleSearchItem(**base)


def _service(providers: dict[str, FakeProvider], **kwargs) -> SubtitleSearchService:
    return SubtitleSearchService(providers, provider_order=list(providers), **kwargs)


def test_providers_without_token_are_skipped_not_errored() -> None:
    providers = {
        "free": FakeProvider("free", items=[_item("free", "1")]),
        "paid": FakeProvider("paid", available=False, requires_token=True),
    }
    result = _service(providers).search(SubtitleQuery(title="Show"))

    assert result.skipped == ["paid"]
    assert result.errors == {}
    assert providers["paid"].searched == 0
    assert result.total == 1


def test_one_failing_provider_does_not_break_others() -> None:
    providers = {
        "good": FakeProvider("good", items=[_item("good", "1")]),
        "bad": FakeProvider("bad", error=SubtitleBlockedError("触发了验证码")),
    }
    result = _service(providers).search(SubtitleQuery(title="Show"))

    assert result.total == 1
    assert "触发了验证码" in result.errors["bad"]


def test_results_are_grouped_and_deduped_per_provider() -> None:
    providers = {
        "a": FakeProvider(
            "a",
            items=[_item("a", "1"), _item("a", "1"), _item("a", "2")],
        )
    }
    result = _service(providers).search(SubtitleQuery(title="Show"))

    assert len(result.groups) == 1
    assert [row.subtitle_id for row in result.groups[0].items] == ["1", "2"]


def test_bilingual_simplified_ranks_first_across_providers() -> None:
    providers = {
        "a": FakeProvider("a", items=[_item("a", "1", language=ENG)]),
        "b": FakeProvider("b", items=[_item("b", "2", language=CHS_ENG)]),
        "c": FakeProvider("c", items=[_item("c", "3", language=CHS)]),
    }
    result = _service(providers).search(SubtitleQuery(title="Show"))

    assert result.groups[0].provider == "b"
    best = result.best_item()
    assert best is not None
    assert best.language == CHS_ENG


def test_provider_filter_limits_search() -> None:
    providers = {
        "a": FakeProvider("a", items=[_item("a", "1")]),
        "b": FakeProvider("b", items=[_item("b", "2")]),
    }
    result = _service(providers).search(
        SubtitleQuery(title="Show"), provider_filter="b"
    )

    assert providers["a"].searched == 0
    assert [group.provider for group in result.groups] == ["b"]


def test_disabled_providers_are_excluded_from_order() -> None:
    providers = {
        "a": FakeProvider("a", items=[_item("a", "1")]),
        "b": FakeProvider("b", items=[_item("b", "2")]),
    }
    service = _service(providers, disabled_provider_ids_loader=lambda: ["b"])

    assert service.provider_order == ["a"]
    result = service.search(SubtitleQuery(title="Show"))
    assert providers["b"].searched == 0
    assert [group.provider for group in result.groups] == ["a"]


def test_notice_is_carried_into_group() -> None:
    providers = {
        "assrt": FakeProvider(
            "assrt", items=[_item("assrt", "1")], notice="字幕服务由 assrt.net 提供"
        )
    }
    result = _service(providers).search(SubtitleQuery(title="Show"))
    assert result.groups[0].notice == "字幕服务由 assrt.net 提供"


def test_download_rejects_unknown_provider() -> None:
    service = _service({"a": FakeProvider("a")})
    with pytest.raises(SubtitleProviderError):
        service.download(_item("nope", "1"))


def test_download_rejects_blank_subtitle_text() -> None:
    class BlankProvider(FakeProvider):
        def download(self, item):
            return SubtitleContent(text="   \n", suffix=".srt")

    service = _service({"a": BlankProvider("a")})
    with pytest.raises(SubtitleProviderError, match="为空"):
        service.download(_item("a", "1"))


def test_build_query_prefers_explicit_fields_over_filename() -> None:
    query = build_subtitle_query(
        title="庆余年",
        episode=3,
        file_name="Joy.of.Life.S02E06.1080p.WEB-DL.x265-GRP.mkv",
        imdb_id="tt9999999",
    )
    assert query.title == "庆余年"
    assert query.episode == 3
    assert query.season == 2
    assert query.imdb_id == "tt9999999"
    # 画质等只用于打分，不进搜索关键词
    assert query.resolution == "1080p"
    assert query.codec == "H.265"


def test_build_query_falls_back_to_filename_parsing() -> None:
    query = build_subtitle_query(
        file_name="The.Last.of.Us.S02E06.2160p.WEB-DL.H.265-GROUP.mkv"
    )
    assert query.title == "The Last of Us"
    assert query.season == 2
    assert query.episode == 6


def test_build_query_strips_episode_suffix_from_title() -> None:
    query = build_subtitle_query(title="某剧 第12集")
    assert "第12集" not in query.title
    assert query.episode == 12


def test_episode_of_supports_common_forms() -> None:
    assert episode_of("Show.S01E05.1080p") == 5
    assert episode_of("Show EP07") == 7
    assert episode_of("某剧 第12集") == 12
    assert episode_of("") is None
