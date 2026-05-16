from atv_player.metadata.matching import score_match
from atv_player.metadata.models import MetadataMatch, MetadataQuery


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
