# ruff: noqa: E501
from atv_player.following_metadata import (
    build_following_from_candidate,
    build_snapshot_from_record,
    compute_episode_counts,
    following_provider_priority,
)
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate


def test_following_provider_priority_prefers_bangumi_for_anime() -> None:
    assert following_provider_priority("anime") == ["bangumi", "tmdb", "douban"]
    assert following_provider_priority("live_action") == ["tmdb", "douban", "bangumi"]


def test_build_following_from_bangumi_candidate_preserves_ids_and_counts() -> None:
    candidate = MetadataScrapeCandidate(
        provider="bangumi",
        provider_label="Bangumi",
        provider_id="subject:123",
        title="凡人修仙传",
        year="2026",
        subtitle="动漫",
        raw={"episodes": [{"sort": 1, "name_cn": "第一话", "desc": "剧情"}, {"sort": 2, "name": "Episode 2"}]},
    )

    record, snapshot = build_following_from_candidate(candidate, now=100)

    assert record.provider == "bangumi"
    assert record.provider_id == "subject:123"
    assert record.external_ids["bangumi"] == "123"
    assert record.latest_episode == 2
    assert record.total_episodes == 2
    assert snapshot.episodes[0].title == "第一话"


def test_build_snapshot_from_tmdb_record_includes_backdrops_cast_and_episode_stills() -> None:
    record = MetadataRecord(
        provider="tmdb",
        provider_id="tv:456:season:1",
        title="庆余年",
        poster="poster",
        backdrop="backdrop",
        rating="8.0",
        tmdb_id="456",
        douban_id=129,
        actors=["张若昀"],
        directors=["孙皓"],
        detail_fields=[
            {
                "label": "episodes",
                "value": [
                    {"episode_number": 1, "name": "第一集", "overview": "剧情", "still_url": "still"}
                ],
            }
        ],
    )

    following, snapshot = build_snapshot_from_record(record, now=200, media_kind="live_action")

    assert following.external_ids == {"tmdb": "456", "douban": "129"}
    assert following.backdrop == "backdrop"
    assert snapshot.cast[0]["name"] == "张若昀"
    assert snapshot.crew[0]["name"] == "孙皓"
    assert snapshot.episodes[0].still == "still"


def test_compute_episode_counts_ignores_specials_and_zero_episode_numbers() -> None:
    latest, total = compute_episode_counts(
        [
            {"episode_number": 0, "name": "SP"},
            {"episode_number": 1, "name": "第一集"},
            {"sort": 3, "type": 1, "name": "特别篇"},
            {"sort": 2, "type": 0, "name": "第二集"},
        ]
    )

    assert latest == 2
    assert total == 2
