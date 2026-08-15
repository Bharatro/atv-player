from atv_player.models import HistoryRecord, PlayItem
from atv_player.player.resume import resolve_resume_index


def test_resolve_resume_index_prefers_episode() -> None:
    playlist = [PlayItem(title="1", url="http://m/1.m3u8"), PlayItem(title="2", url="http://m/2.m3u8")]
    history = HistoryRecord(
        id=1,
        key="abc",
        vod_name="Movie",
        vod_pic="",
        vod_remarks="Ep2",
        episode=1,
        episode_url="2.m3u8",
        position=12000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )

    assert resolve_resume_index(history, playlist, clicked_index=0) == 1


def test_resolve_resume_index_falls_back_to_episode_url_filename() -> None:
    playlist = [PlayItem(title="1", url="http://m/1.m3u8?token=a"), PlayItem(title="2", url="http://m/2.m3u8?token=b")]
    history = HistoryRecord(
        id=1,
        key="abc",
        vod_name="Movie",
        vod_pic="",
        vod_remarks="Ep2",
        episode=-1,
        episode_url="2.m3u8",
        position=12000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )

    assert resolve_resume_index(history, playlist, clicked_index=0) == 1


def test_resolve_resume_index_prefers_matching_episode_url_over_stale_episode_number() -> None:
    playlist = [
        PlayItem(title="1", url="http://m/1.m3u8?token=a"),
        PlayItem(title="2", url="http://m/2.m3u8?token=b"),
    ]
    history = HistoryRecord(
        id=1,
        key="abc",
        vod_name="Movie",
        vod_pic="",
        vod_remarks="Ep1",
        episode=1,
        episode_url="1.m3u8",
        position=12000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )

    assert resolve_resume_index(history, playlist, clicked_index=0) == 0


def test_resolve_resume_index_ignores_empty_basename_and_falls_back_to_episode() -> None:
    playlist = [PlayItem(title=f"{index + 1}", url="") for index in range(77)]
    history = HistoryRecord(
        id=1,
        key="abc",
        vod_name="Movie",
        vod_pic="",
        vod_remarks="Ep18",
        episode=17,
        episode_url="https://media.example/segment/?token=a",
        position=12000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )

    assert resolve_resume_index(history, playlist, clicked_index=0) == 17


def _history_with_drive_path(drive_path: str, episode: int = 0) -> HistoryRecord:
    return HistoryRecord(
        id=1,
        key="gy_tv_58kD",
        vod_name="菜鸟老警",
        vod_pic="",
        vod_remarks="S02E03.mp4",
        episode=episode,
        episode_url="",
        position=12000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
        drive_share_key="baidu@1fFDWZTTtXy8aTPjKJ2F0uA@f1z9",
        drive_path=drive_path,
    )


def test_resolve_resume_index_prefers_drive_path_over_episode_number() -> None:
    # 列表重排后集数(episode=0)指向了别的文件,规范路径仍能定位到同一集
    playlist = [
        PlayItem(title="S02E01", url="http://m/1", path="/我的百度分享/temp/baidu@1fFDWZTTtXy8aTPjKJ2F0uA@f1z9/C 菜鸟老警/S02/S02E01.mp4"),
        PlayItem(title="S02E03", url="http://m/3", path="/我的百度分享/temp/baidu@1fFDWZTTtXy8aTPjKJ2F0uA@f1z9/C 菜鸟老警/S02/S02E03.mp4"),
    ]
    history = _history_with_drive_path("/C 菜鸟老警/S02/S02E03.mp4", episode=0)

    assert resolve_resume_index(history, playlist, clicked_index=0) == 1


def test_resolve_resume_index_drive_path_matches_across_reordered_directories() -> None:
    # 子目录改名/重排:相对路径不变即可命中;不匹配则退回集数
    playlist = [
        PlayItem(title="01", url="http://m/1", path="/我的百度分享/temp/baidu@1fFDWZTTtXy8aTPjKJ2F0uA@f1z9/改过的目录/S01/S01E01.mp4"),
        PlayItem(title="S02E03", url="http://m/3", path="/我的百度分享/temp/baidu@1fFDWZTTtXy8aTPjKJ2F0uA@f1z9/C 菜鸟老警/S02/S02E03.mp4"),
    ]
    history = _history_with_drive_path("/C 菜鸟老警/S02/S02E03.mp4", episode=0)

    assert resolve_resume_index(history, playlist, clicked_index=0) == 1


def test_resolve_resume_index_falls_back_when_drive_path_not_found() -> None:
    playlist = [
        PlayItem(title="1", url="http://m/1.m3u8"),
        PlayItem(title="2", url="http://m/2.m3u8"),
    ]
    history = _history_with_drive_path("/C 菜鸟老警/S02/S02E03.mp4", episode=1)

    # 播放列表没有网盘路径(如普通站点源),退回集数
    assert resolve_resume_index(history, playlist, clicked_index=0) == 1
