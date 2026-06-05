from __future__ import annotations

from atv_player.following_models import FollowingRecord
from atv_player.heat.identity import (
    has_required_heat_external_id,
    heat_identity_from_following,
    heat_identity_from_vod,
)
from atv_player.models import (
    PlaybackDetailField,
    PlaybackDetailFieldAction,
    PlaybackDetailValuePart,
    PlayItem,
    VodItem,
)


def test_heat_identity_prefers_tmdb_detail_field() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="权力的游戏",
            vod_pic="https://image.example/p.jpg",
            vod_year="2011",
            type_name="剧集",
            detail_fields=[PlaybackDetailField("TMDB ID", "1399")],
        )
    )

    assert identity is not None
    assert identity.media_key == "tmdb:tv:1399"
    assert identity.external_ids["tmdb"] == "tv:1399"


def test_heat_identity_includes_all_scraped_external_ids() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="黑袍纠察队",
            type_name="剧集",
            detail_fields=[
                PlaybackDetailField("TMDB ID", "76479"),
                PlaybackDetailField("豆瓣ID", "30318230"),
                PlaybackDetailField("Bangumi ID", "526975"),
            ],
        )
    )

    assert identity is not None
    assert identity.media_key == "tmdb:tv:76479"
    assert identity.external_ids == {
        "tmdb": "tv:76479",
        "douban": "30318230",
        "bangumi": "526975",
    }


def test_heat_identity_uses_tmdb_action_target_for_stable_media_key() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="不带类型的条目",
            detail_fields=[
                PlaybackDetailField(
                    "TMDB ID",
                    value_parts=[
                        PlaybackDetailValuePart(
                            label="289271",
                            action=PlaybackDetailFieldAction(
                                type="link",
                                value="289271",
                                target="tv",
                            ),
                        )
                    ],
                )
            ],
        )
    )

    assert identity is not None
    assert identity.media_key == "tmdb:tv:289271"
    assert identity.media_type == "tv"
    assert identity.external_ids["tmdb"] == "tv:289271"


def test_heat_identity_uses_vod_dbid_as_douban_external_id() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="豆瓣条目",
            type_name="电影",
            detail_fields=[PlaybackDetailField("TMDB ID", "34541")],
            dbid=19971621,
        )
    )

    assert identity is not None
    assert identity.media_key == "tmdb:movie:34541"
    assert identity.external_ids["tmdb"] == "movie:34541"
    assert identity.external_ids["douban"] == "19971621"


def test_heat_identity_extracts_douban_when_tmdb_missing() -> None:
    identity = heat_identity_from_vod(
        VodItem(
            vod_id="plugin-id",
            vod_name="测试电影",
            type_name="电影",
            detail_fields=[PlaybackDetailField("豆瓣ID", "3016187")],
        )
    )

    assert identity is not None
    assert identity.media_key == "douban:3016187"
    assert identity.external_ids["douban"] == "3016187"


def test_heat_identity_falls_back_to_normalized_title() -> None:
    identity = heat_identity_from_vod(VodItem(vod_id="x", vod_name="测试：电影 第一季"))

    assert identity is not None
    assert identity.media_key == "title:测试电影"
    assert has_required_heat_external_id(identity) is False


def test_heat_identity_merges_play_item_fields() -> None:
    vod = VodItem(vod_id="x", vod_name="集合名", type_name="剧集")
    item = PlayItem(
        title="第1集",
        url="https://media.example/1.m3u8",
        media_title="单集名",
        detail_fields=[PlaybackDetailField("Bangumi ID", "526975")],
    )

    identity = heat_identity_from_vod(vod, item)

    assert identity is not None
    assert identity.media_key == "bangumi:526975"
    assert identity.title == "单集名"
    assert has_required_heat_external_id(identity) is True


def test_heat_identity_from_following_uses_provider_identity() -> None:
    record = FollowingRecord(
        id=1,
        title="追更剧",
        provider="tmdb",
        provider_id="tv:1399",
        poster="https://image.example/p.jpg",
        media_kind="tv",
    )

    identity = heat_identity_from_following(record)

    assert identity is not None
    assert identity.media_key == "tmdb:tv:1399"
    assert identity.external_ids["tmdb"] == "tv:1399"


def test_heat_identity_from_following_normalizes_tmdb_external_id() -> None:
    record = FollowingRecord(
        id=1,
        title="旧追更剧",
        media_kind="anime",
        external_ids={"tmdb": "289271"},
    )

    identity = heat_identity_from_following(record)

    assert identity is not None
    assert identity.media_key == "tmdb:tv:289271"
    assert identity.external_ids["tmdb"] == "tv:289271"
