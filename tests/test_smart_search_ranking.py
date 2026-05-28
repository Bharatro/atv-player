from __future__ import annotations

from atv_player.ai.search_intent import SmartSearchIntent
from atv_player.search.models import SmartSearchCandidate
from atv_player.search.ranking import rank_candidates


def test_rank_candidates_rewards_keywords_rating_and_source() -> None:
    intent = SmartSearchIntent(
        query_text="类似黑镜的高分科幻",
        mode="smart_discovery",
        genres=["科幻"],
        keywords=["科幻"],
        rating_min=8.0,
        reference_titles=["黑镜"],
        sort_preference="rating",
    )
    candidates = [
        SmartSearchCandidate(
            source_kind="history",
            source_label="播放记录",
            vod_id="1",
            title="普通喜剧",
            overview="轻松喜剧",
            rating=6.5,
        ),
        SmartSearchCandidate(
            source_kind="following",
            source_label="我的追更",
            vod_id="2",
            title="黑镜",
            overview="近未来科幻寓言",
            genres=["科幻", "悬疑"],
            rating=8.8,
        ),
    ]

    ranked = rank_candidates(candidates, intent)

    assert ranked[0].candidate.vod_id == "2"
    assert ranked[0].score > ranked[1].score
    assert "科幻匹配" in ranked[0].reasons
    assert "评分 8.8" in ranked[0].reasons
    assert "来自我的追更" in ranked[0].reasons


def test_rank_candidates_filters_negative_keywords() -> None:
    intent = SmartSearchIntent(
        query_text="轻松电影不要恐怖",
        keywords=["轻松"],
        negative_keywords=["恐怖"],
    )
    candidates = [
        SmartSearchCandidate(
            source_kind="favorite",
            source_label="我的收藏",
            vod_id="1",
            title="轻松恐怖片",
        ),
        SmartSearchCandidate(
            source_kind="favorite",
            source_label="我的收藏",
            vod_id="2",
            title="轻松喜剧",
        ),
    ]

    ranked = rank_candidates(candidates, intent)

    assert [item.candidate.vod_id for item in ranked] == ["2"]
