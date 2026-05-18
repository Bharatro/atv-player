from atv_player.metadata.matching import is_confident_match, score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery
import pytest


def test_score_match_boosts_synonymous_category_match() -> None:
    query = MetadataQuery(title="仙剑奇侠传3", year="2025", category_name="动漫")

    animation_match = MetadataMatch(
        provider="tmdb",
        provider_id="tv:1",
        title="仙剑奇侠传叁",
        year="2025",
        raw={"genres": ["动画", "动作冒险"]},
    )
    drama_match = MetadataMatch(
        provider="tmdb",
        provider_id="tv:2",
        title="仙剑奇侠传叁",
        year="2025",
        raw={"genres": ["剧情"]},
    )

    assert score_match(query, animation_match) > score_match(query, drama_match)


def test_score_match_bilibili_exact_match_bonus_is_point_three() -> None:
    query = MetadataQuery(title="牧神记")

    bilibili_score = score_match(
        query,
        MetadataMatch(provider="bilibili", provider_id="bili:1", title="牧神记"),
    )
    iqiyi_score = score_match(
        query,
        MetadataMatch(provider="iqiyi", provider_id="iqiyi:1", title="牧神记"),
    )

    assert bilibili_score == pytest.approx(iqiyi_score + 0.15)


def test_score_match_uses_query_type_name_for_animation_bias() -> None:
    query = MetadataQuery(title="牧神记", year="2024", type_name="动画")

    animation_match = MetadataMatch(
        provider="tmdb",
        provider_id="tv:1",
        title="牧神记",
        year="2024",
        raw={"genres": ["动漫", "奇幻"]},
    )
    drama_match = MetadataMatch(
        provider="tmdb",
        provider_id="tv:2",
        title="牧神记",
        year="2024",
        raw={"genres": ["剧情"]},
    )

    assert score_match(query, animation_match) > score_match(query, drama_match)


def test_score_match_prefers_same_year_for_same_title() -> None:
    query = MetadataQuery(title="主角", year="2026")

    matched_year = MetadataMatch(
        provider="tmdb",
        provider_id="tv:1",
        title="主角",
        year="2026",
    )
    mismatched_year = MetadataMatch(
        provider="tmdb",
        provider_id="tv:2",
        title="主角",
        year="2024",
    )

    assert score_match(query, matched_year) > score_match(query, mismatched_year)


def test_score_match_rejects_large_year_conflict_even_for_exact_title() -> None:
    query = MetadataQuery(title="西游记", year="1986")

    mismatched_year = MetadataMatch(
        provider="local_douban",
        provider_id="1890547",
        title="西游记",
        year="1978",
    )

    assert is_confident_match(score_match(query, mismatched_year)) is False
