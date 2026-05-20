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


def test_score_match_prefers_matching_area_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_area="中国大陆")

    matched_area = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"country": "中国大陆"},
    )
    mismatched_area = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"country": "日本"},
    )

    assert score_match(query, matched_area) > score_match(query, mismatched_area)


def test_score_match_prefers_matching_language_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_lang="汉语普通话")

    matched_language = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:1",
        title="深空彼岸",
        year="2026",
        raw={"language": {"value": "汉语普通话"}},
    )
    mismatched_language = MetadataMatch(
        provider="iqiyi",
        provider_id="iqiyi:2",
        title="深空彼岸",
        year="2026",
        raw={"language": {"value": "日语"}},
    )

    assert score_match(query, matched_language) > score_match(query, mismatched_language)


def test_score_match_prefers_matching_director_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_director="周琛,赵禹晴")

    matched_director = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"directors": ["周琛", "其他导演"]},
    )
    mismatched_director = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"directors": ["无关导演"]},
    )

    assert score_match(query, matched_director) > score_match(query, mismatched_director)


def test_score_match_prefers_matching_actor_when_title_and_year_are_same() -> None:
    query = MetadataQuery(title="深空彼岸", year="2026", vod_actor="梁达伟,唐雅菁")

    matched_actor = MetadataMatch(
        provider="tencent",
        provider_id="tx:1",
        title="深空彼岸",
        year="2026",
        raw={"actors": ["梁达伟", "其他演员"]},
    )
    mismatched_actor = MetadataMatch(
        provider="tencent",
        provider_id="tx:2",
        title="深空彼岸",
        year="2026",
        raw={"actors": ["无关演员"]},
    )

    assert score_match(query, matched_actor) > score_match(query, mismatched_actor)


def test_score_match_rejects_large_year_conflict_even_for_exact_title() -> None:
    query = MetadataQuery(title="西游记", year="1986")

    mismatched_year = MetadataMatch(
        provider="local_douban",
        provider_id="1890547",
        title="西游记",
        year="1978",
    )

    assert is_confident_match(score_match(query, mismatched_year)) is False
