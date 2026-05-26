from types import SimpleNamespace

from atv_player.ui.following_search_result_card import (
    FollowingSearchResultCard,
    following_search_candidate_media_type,
)


def test_following_search_candidate_media_type_prefers_tv_and_movie_prefixes() -> None:
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="tv:76479:season:1")) == "电视"
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="movie:550")) == "电影"
    assert following_search_candidate_media_type(SimpleNamespace(provider_id="subject:1")) == ""


def test_following_search_result_card_renders_rating_title_year_and_overview(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="tv:76479:season:1",
        title="The Boys",
        year="2019",
        raw={
            "poster": "https://img.test/poster.jpg",
            "rating": "8.7",
            "overview": "A long overview for the TV result.",
        },
    )

    card = FollowingSearchResultCard(candidate)
    qtbot.addWidget(card)

    assert card.title_label.text() == "The Boys"
    assert card.meta_label.text() == "2019 · 电视"
    assert card.rating_label.text() == "8.7"
    assert card.overview_label.text().replace("\n", "") == "A long overview for the TV result."


def test_following_search_result_card_uses_fallback_overview_and_hides_empty_rating(qtbot) -> None:
    candidate = SimpleNamespace(
        provider_id="movie:12",
        title="Movie",
        year="2024",
        raw={},
    )

    card = FollowingSearchResultCard(candidate)
    qtbot.addWidget(card)

    assert card.overview_label.text() == "暂无简介"
    assert card.rating_label.isHidden() is True
