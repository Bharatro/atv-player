from atv_player.metadata.cache_key import provider_search_cache_key
from atv_player.metadata.models import MetadataQuery


class _ProviderWithoutOverride:
    pass


class _ProviderWithOverride:
    def search_cache_key(self, query: MetadataQuery) -> tuple[str, str] | None:
        del query
        return ("normalized title", "")


def test_provider_search_cache_key_falls_back_to_query_title_and_year() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026")

    assert provider_search_cache_key(_ProviderWithoutOverride(), query) == ("深空彼岸", "2026")


def test_provider_search_cache_key_uses_provider_override_when_present() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026")

    assert provider_search_cache_key(_ProviderWithOverride(), query) == ("normalized title", "")


def test_provider_search_cache_key_prefers_tmdb_external_id_anchor() -> None:
    query = MetadataQuery(
        title="权力的游戏",
        year="2011",
        source_kind="tmdb",
        vod_id="tv:1399",
    )

    assert provider_search_cache_key(_ProviderWithoutOverride(), query) == ("tmdb:tv:1399", "")
