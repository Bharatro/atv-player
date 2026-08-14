from atv_player.subtitles.languages import CHS, CHS_ENG, CHT, ENG
from atv_player.subtitles.matcher import (
    DEFAULT_MATCH_WEIGHTS,
    apply_scores,
    score_subtitle,
)
from atv_player.subtitles.models import SubtitleQuery, SubtitleSearchItem


def _item(**kwargs) -> SubtitleSearchItem:
    base = {
        "provider": "subdl",
        "provider_label": "SubDL",
        "subtitle_id": "1",
        "name": "Show",
    }
    base.update(kwargs)
    return SubtitleSearchItem(**base)


def test_media_id_match_dominates_score() -> None:
    query = SubtitleQuery(title="Show", imdb_id="tt1234567")
    with_id = _item(name="Show tt1234567 1080p")
    without_id = _item(name="Show 1080p")

    assert score_subtitle(with_id, query)[0] > score_subtitle(without_id, query)[0]


def test_season_and_episode_match_add_expected_weight() -> None:
    query = SubtitleQuery(title="Show", season=2, episode=6)
    matched = _item(season=2, episode=6)
    mismatched = _item(season=1, episode=1)

    matched_score = score_subtitle(matched, query)[0]
    mismatched_score = score_subtitle(mismatched, query)[0]
    expected_gap = DEFAULT_MATCH_WEIGHTS.season + DEFAULT_MATCH_WEIGHTS.episode
    assert matched_score - mismatched_score == expected_gap


def test_episode_can_be_detected_from_release_text() -> None:
    query = SubtitleQuery(title="Show", season=2, episode=6)
    from_text = _item(name="Show.S02E06.1080p")
    structured = _item(name="Show.S02E06.1080p", season=2, episode=6)
    assert from_text.episode is None
    # 条目本身没有结构化集数，但发布名里有 S02E06，应与结构化字段等价
    assert score_subtitle(from_text, query)[0] == score_subtitle(structured, query)[0]


def test_bilingual_simplified_scores_highest_among_languages() -> None:
    query = SubtitleQuery(title="Show")
    scores = {
        code: score_subtitle(_item(language=code), query)[0]
        for code in (CHS_ENG, CHS, CHT, ENG)
    }
    assert scores[CHS_ENG] == max(scores.values())
    assert scores[CHS_ENG] > scores[CHS] > scores[CHT] > scores[ENG]


def test_release_attributes_contribute_to_score() -> None:
    query = SubtitleQuery(
        title="Show",
        resolution="2160p",
        source="WEB-DL",
        codec="H.265",
        release_group="GROUP",
    )
    same_release = _item(name="Show.2160p.WEB-DL.H.265-GROUP")
    other_release = _item(name="Show.720p.HDTV.x264-OTHER")

    assert score_subtitle(same_release, query)[0] > score_subtitle(
        other_release, query
    )[0]


def test_codec_token_matches_across_punctuation_variants() -> None:
    query = SubtitleQuery(title="Show", codec="H.265")
    assert score_subtitle(_item(name="Show x265"), query)[0] == score_subtitle(
        _item(name="Show H265"), query
    )[0]


def test_percentage_is_bounded_and_reflects_quality() -> None:
    query = SubtitleQuery(title="Show", season=1, episode=1)
    perfect = _item(name="Show", language="chs_eng", season=1, episode=1)
    poor = _item(name="Totally Different", language="other", season=9, episode=9)

    _, perfect_percent = score_subtitle(perfect, query)
    _, poor_percent = score_subtitle(poor, query)
    assert perfect_percent == 100
    assert 0 <= poor_percent < perfect_percent


def test_apply_scores_sorts_descending_and_fills_fields() -> None:
    query = SubtitleQuery(title="Show", episode=6)
    items = [
        _item(subtitle_id="a", name="Show E01", language=ENG, episode=1),
        _item(subtitle_id="b", name="Show E06", language=CHS_ENG, episode=6),
    ]

    scored = apply_scores(items, query)

    assert [row.subtitle_id for row in scored] == ["b", "a"]
    assert scored[0].score > 0
    assert scored[0].match_percent > scored[1].match_percent
