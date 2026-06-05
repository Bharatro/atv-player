from __future__ import annotations

from atv_player.following_models import FollowingRecord
from atv_player.heat.identity import heat_identity_from_following, heat_identity_from_vod
from atv_player.models import PlaybackDetailField, PlayItem, VodItem


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
