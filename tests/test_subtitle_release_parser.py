from atv_player.subtitles.release_parser import parse_release_name


def test_parses_full_scene_release_name() -> None:
    info = parse_release_name(
        "The.Last.of.Us.S02E06.2160p.WEB-DL.DDP5.1.DV.HDR.H.265-GROUP.mkv"
    )
    assert info.title == "The Last of Us"
    assert info.season == 2
    assert info.episode == 6
    assert info.resolution == "2160p"
    assert info.source == "WEB-DL"
    assert info.codec == "H.265"
    assert info.release_group == "GROUP"


def test_parses_movie_with_year() -> None:
    info = parse_release_name("Inception.2010.1080p.BluRay.x264-AMIABLE.mkv")
    assert info.title == "Inception"
    assert info.year == 2010
    assert info.resolution == "1080p"
    assert info.source == "BluRay"
    assert info.codec == "H.264"
    assert info.release_group == "AMIABLE"
    assert info.season is None
    assert info.episode is None


def test_parses_chinese_season_and_episode() -> None:
    info = parse_release_name("庆余年 第2季 第06集 1080p.mp4")
    assert info.season == 2
    assert info.episode == 6
    assert "庆余年" in info.title


def test_parses_separated_season_episode_form() -> None:
    info = parse_release_name("Show.Name.S01.E12.720p.HDTV.x265.mkv")
    assert info.season == 1
    assert info.episode == 12
    assert info.codec == "H.265"
    assert info.source == "HDTV"


def test_strips_container_suffix_and_keeps_plain_title() -> None:
    info = parse_release_name("流浪地球.mkv")
    assert info.title == "流浪地球"
    assert info.resolution == ""


def test_numeric_trailing_segment_is_not_a_release_group() -> None:
    info = parse_release_name("Movie.Name.2019.1080p-1080")
    assert info.release_group == ""


def test_empty_input_returns_blank_info() -> None:
    info = parse_release_name("")
    assert info.title == ""
    assert info.season is None
    assert info.raw == ""
