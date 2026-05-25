# ruff: noqa: E501
from atv_player.following_metadata import (
    FollowingMetadataGateway,
    build_following_from_candidate,
    build_following_from_metadata_candidate,
    build_snapshot_from_record,
    compute_episode_counts,
    following_provider_priority,
)
from atv_player.following_models import FollowingRecord
from atv_player.metadata.models import MetadataRecord
from atv_player.metadata.scrape import MetadataScrapeCandidate, MetadataScrapeGroup


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


def test_build_following_from_selected_iqiyi_candidate_enriches_with_tmdb_metadata() -> None:
    selected = MetadataScrapeCandidate(
        provider="iqiyi",
        provider_label="爱奇艺",
        provider_id="iqiyi:album:1",
        title="盗妖行",
        year="2026",
        subtitle="动漫",
        raw={"channel": "动漫,4"},
    )

    class SearchService:
        def __init__(self) -> None:
            self.detail_provider_ids: list[tuple[str, str]] = []

        def search(self, query, provider_filter=""):
            assert query.title == "盗妖行"
            assert provider_filter == ""
            return [
                MetadataScrapeGroup(
                    provider="iqiyi",
                    provider_label="爱奇艺",
                    items=[selected],
                ),
                MetadataScrapeGroup(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:315088:season:1",
                            title="盗妖行",
                            year="2026",
                            subtitle="剧集",
                        )
                    ],
                ),
            ]

        def detail_record(self, candidate):
            self.detail_provider_ids.append((candidate.provider, candidate.provider_id))
            if candidate.provider == "iqiyi":
                return MetadataRecord(
                    provider="iqiyi",
                    provider_id="iqiyi:album:1",
                    title="盗妖行",
                    overview="爱奇艺简介",
                )
            return MetadataRecord(
                provider="tmdb",
                provider_id="tv:315088:season:1",
                title="盗妖行",
                poster="tmdb-poster",
                backdrop="tmdb-backdrop",
                rating="7.5",
                tmdb_id="315088",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集", "still_url": "still"}],
                    }
                ],
            )

    service = SearchService()

    record, snapshot = build_following_from_metadata_candidate(
        selected,
        metadata_search_service=service,
        now=100,
    )

    assert service.detail_provider_ids == [
        ("iqiyi", "iqiyi:album:1"),
        ("tmdb", "tv:315088:season:1"),
    ]
    assert record.provider == "iqiyi"
    assert record.provider_id == "iqiyi:album:1"
    assert record.external_ids == {"iqiyi": "iqiyi:album:1", "tmdb": "315088"}
    assert record.media_kind == "anime"
    assert record.poster == "tmdb-poster"
    assert record.backdrop == "tmdb-backdrop"
    assert record.rating == "7.5"
    assert record.latest_episode == 1
    assert record.total_episodes == 1
    assert snapshot.overview == "爱奇艺简介"
    assert snapshot.episodes[0].title == "第一集"


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


def test_compute_episode_counts_uses_air_date_for_latest_and_all_episodes_for_total() -> None:
    latest, total = compute_episode_counts(
        [
            {"episode_number": 23, "air_date": "2026-05-19"},
            {"episode_number": 24, "air_date": "2026-05-26"},
            {"episode_number": 25, "air_date": "2026-06-02"},
        ],
        now=1779638400,
    )

    assert latest == 23
    assert total == 3


def test_following_metadata_gateway_refreshes_tmdb_tv_as_first_season_detail() -> None:
    class SearchService:
        def __init__(self) -> None:
            self.detail_provider_ids: list[str] = []

        def search(self, query, provider_filter=""):
            del query
            assert provider_filter == "tmdb"
            return [
                MetadataScrapeGroup(
                    provider="tmdb",
                    provider_label="TMDB",
                    items=[
                        MetadataScrapeCandidate(
                            provider="tmdb",
                            provider_label="TMDB",
                            provider_id="tv:315088",
                            title="盗妖行",
                        )
                    ],
                )
            ]

        def detail_record(self, candidate):
            self.detail_provider_ids.append(candidate.provider_id)
            return MetadataRecord(
                provider="tmdb",
                provider_id=candidate.provider_id,
                title="盗妖行",
                poster="poster",
                detail_fields=[
                    {
                        "label": "episodes",
                        "value": [{"episode_number": 1, "name": "第一集"}],
                    }
                ],
            )

    service = SearchService()
    record, snapshot = FollowingMetadataGateway(service).refresh(
        FollowingRecord(
            id=2,
            title="盗妖行",
            provider="tmdb",
            provider_id="tv:315088",
        ),
        "tmdb",
    )

    assert service.detail_provider_ids == ["tv:315088:season:1"]
    assert record.provider_id == "tv:315088:season:1"
    assert record.poster == "poster"
    assert record.latest_episode == 1
    assert snapshot.episodes[0].title == "第一集"
