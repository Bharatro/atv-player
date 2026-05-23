import logging

from atv_player.controllers.player_controller import PlayerController
from atv_player.models import (
    HistoryRecord,
    PlaybackDetailField,
    PlaybackSource,
    PlaybackSourceGroup,
    PlayItem,
    PlaybackDetailAction,
    VodItem,
)


class FakeApiClient:
    def __init__(self) -> None:
        self.saved_payloads: list[dict] = []
        self.history: HistoryRecord | None = None
        self.history_calls: list[str] = []

    def get_history(self, key: str):
        self.history_calls.append(key)
        return self.history

    def save_history(self, payload: dict) -> None:
        self.saved_payloads.append(payload)


def test_player_controller_restores_resume_state() -> None:
    api = FakeApiClient()
    api.history = HistoryRecord(
        id=1,
        key="movie-1",
        vod_name="Movie",
        vod_pic="pic",
        vod_remarks="Episode 2",
        episode=1,
        episode_url="2.m3u8",
        position=45000,
        opening=12000,
        ending=24000,
        speed=1.5,
        create_time=1,
    )
    controller = PlayerController(api)
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=0)

    assert session.start_index == 1
    assert session.start_position_seconds == 45
    assert session.speed == 1.5
    assert session.opening_seconds == 12
    assert session.ending_seconds == 24


def test_player_controller_builds_history_payload() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]
    session = controller.create_session(vod, playlist, clicked_index=1)

    controller.report_progress(
        session,
        current_index=1,
        position_seconds=90,
        speed=1.25,
        opening_seconds=15,
        ending_seconds=30,
        paused=False,
    )

    payload = api.saved_payloads[0]
    assert payload["key"] == "movie-1"
    assert payload["vodName"] == "Movie"
    assert payload["episode"] == 1
    assert payload["episodeUrl"] == "2.m3u8"
    assert payload["position"] == 90000
    assert payload["opening"] == 15000
    assert payload["ending"] == 30000
    assert payload["speed"] == 1.25


def test_player_controller_preserves_ytdlp_collection_title_in_history_payload() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="youtube-channel", vod_name="OpenAI", vod_pic="channel-pic")
    playlist = [
        PlayItem(
            title="Upcoming video",
            url="https://www.youtube.com/watch?v=test123",
            original_url="https://www.youtube.com/watch?v=test123",
            media_title="OpenAI",
        )
    ]
    session = controller.create_session(vod, playlist, clicked_index=0)
    session.vod.vod_name = "Resolved YouTube Video"
    session.playlist[0].title = "Resolved YouTube Video"
    session.playlist[0].media_title = "Resolved YouTube Video"
    session.playlist[0].selected_playback_quality_id = "ytdlp_1080"

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    payload = api.saved_payloads[0]
    assert payload["vodName"] == "OpenAI"
    assert payload["vodRemarks"] == "Resolved YouTube Video"


def test_player_controller_uses_ytdlp_channel_name_when_initial_title_is_channel_id() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="UC_x5XG1OV2P6uZZ5FSM9Ttw", vod_name="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    playlist = [
        PlayItem(
            title="Upcoming video",
            url="https://www.youtube.com/watch?v=test123",
            original_url="https://www.youtube.com/watch?v=test123",
            media_title="UC_x5XG1OV2P6uZZ5FSM9Ttw",
        )
    ]
    session = controller.create_session(vod, playlist, clicked_index=0)
    session.vod.vod_name = "Resolved YouTube Video"
    session.vod.detail_fields = [PlaybackDetailField("频道", "OpenAI")]
    session.playlist[0].title = "Resolved YouTube Video"
    session.playlist[0].media_title = "Resolved YouTube Video"
    session.playlist[0].selected_playback_quality_id = "ytdlp_1080"

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    payload = api.saved_payloads[0]
    assert payload["vodName"] == "OpenAI"
    assert payload["vodRemarks"] == "Resolved YouTube Video"


def test_player_controller_uses_resolved_ytdlp_title_when_initial_title_is_url_placeholder() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    url = "https://www.youtube.com/watch?v=test123"
    vod = VodItem(vod_id=url, vod_name=url)
    playlist = [PlayItem(title=url, url=url, original_url=url, media_title=url)]
    session = controller.create_session(vod, playlist, clicked_index=0)
    session.vod.vod_name = "Resolved YouTube Video"
    session.playlist[0].title = "Resolved YouTube Video"
    session.playlist[0].media_title = "Resolved YouTube Video"
    session.playlist[0].selected_playback_quality_id = "ytdlp_1080"

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    payload = api.saved_payloads[0]
    assert payload["vodName"] == "Resolved YouTube Video"
    assert payload["vodRemarks"] == "Resolved YouTube Video"


def test_player_controller_create_session_defaults_video_cover_override_to_empty() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="poster-detail")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=0)

    assert session.video_cover_override == ""


def test_player_controller_create_session_defaults_detail_action_runner_to_none() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=0)

    assert session.detail_action_runner is None


def test_player_controller_create_session_preserves_detail_action_runner() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    def detail_action_runner(item: PlayItem, action_id: str) -> list[PlaybackDetailAction]:
        return [PlaybackDetailAction(id=action_id, label="已执行")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        detail_action_runner=detail_action_runner,
    )

    assert session.detail_action_runner is detail_action_runner


def test_player_controller_binds_session_aware_playback_loader_without_changing_history_poster() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-detail")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="/play/1")]

    def load_item(session, item: PlayItem) -> None:
        session.video_cover_override = "https://img.example/video-cover.jpg"
        item.url = "http://m/1.m3u8"
        return None

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        playback_loader=load_item,
    )

    assert session.playback_loader is not None
    session.playback_loader(session.playlist[0])

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=30,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        force_remote_report=True,
    )

    assert session.video_cover_override == "https://img.example/video-cover.jpg"
    assert session.vod.vod_pic == "poster-detail"
    assert api.saved_payloads[0]["vodPic"] == "poster-detail"


def test_player_controller_create_session_preserves_detail_resolver_and_seed_cache() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="1$91483$1")]
    resolved_vod = VodItem(
        vod_id="1$91483$1",
        vod_name="Resolved Episode",
        vod_play_url="http://m/1.m3u8",
        items=[PlayItem(title="Episode 1", url="http://m/1.m3u8", vod_id="1$91483$1")],
    )

    def detail_resolver(item: PlayItem) -> VodItem:
        raise AssertionError("resolver should not be called when the cache is pre-seeded")

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        detail_resolver=detail_resolver,
        resolved_vod_by_id={"1$91483$1": resolved_vod},
    )

    assert session.detail_resolver is detail_resolver
    assert session.resolved_vod_by_id["1$91483$1"].vod_name == "Resolved Episode"


def test_player_controller_resolve_play_item_detail_uses_session_cache() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="1$91483$1")]
    calls: list[str] = []

    def detail_resolver(item: PlayItem) -> VodItem:
        calls.append(item.vod_id)
        return VodItem(
            vod_id=item.vod_id,
            vod_name="Resolved Episode",
            vod_play_url="http://m/1.m3u8",
            items=[PlayItem(title="Episode 1", url="http://m/1.m3u8", vod_id=item.vod_id)],
        )

    session = controller.create_session(vod, playlist, clicked_index=0, detail_resolver=detail_resolver)

    first = controller.resolve_play_item_detail(session, playlist[0])
    second = controller.resolve_play_item_detail(session, playlist[0])

    assert calls == ["1$91483$1"]
    assert first.vod_name == "Resolved Episode"
    assert second.vod_name == "Resolved Episode"
    assert playlist[0].url == "http://m/1.m3u8"


def test_player_controller_resolve_play_item_detail_handles_missing_detail() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="http://m/existing.m3u8", vod_id="1$91483$1")]
    calls: list[str] = []

    def detail_resolver(item: PlayItem) -> None:
        calls.append(item.vod_id)
        return None

    session = controller.create_session(vod, playlist, clicked_index=0, detail_resolver=detail_resolver)

    resolved = controller.resolve_play_item_detail(session, playlist[0])

    assert calls == ["1$91483$1"]
    assert resolved is None
    assert playlist[0].url == "http://m/existing.m3u8"
    assert session.resolved_vod_by_id == {"1$91483$1": None}


def test_player_controller_skips_local_history_when_session_disables_it() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="1-3458")]

    session = controller.create_session(vod, playlist, clicked_index=0, use_local_history=False)

    assert api.history_calls == []
    assert session.start_index == 0
    assert session.start_position_seconds == 0
    assert session.speed == 1.0


def test_player_controller_can_restore_history_without_saving_local_history() -> None:
    api = FakeApiClient()
    api.history = HistoryRecord(
        id=1,
        key="emby-1",
        vod_name="Emby Movie",
        vod_pic="pic",
        vod_remarks="Episode 2",
        episode=1,
        episode_url="2.m3u8",
        position=45000,
        opening=5000,
        ending=10000,
        speed=1.25,
        create_time=1,
    )
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        restore_history=True,
    )

    assert api.history_calls == ["emby-1"]
    assert session.start_index == 1
    assert session.start_position_seconds == 45
    assert session.speed == 1.25


def test_player_controller_prefills_unexpired_youtube_history_url_for_async_loader() -> None:
    controller = PlayerController(FakeApiClient())
    history_url = "https://manifest.googlevideo.com/api/manifest/hls_playlist/expire/4102444800/playlist/index.m3u8"
    vod = VodItem(vod_id="yt:video:abc123", vod_name="YouTube")
    playlist = [
        PlayItem(
            title="YouTube",
            url="",
            original_url="https://www.youtube.com/watch?v=abc123",
            vod_id="yt:video:abc123",
        )
    ]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_loader=lambda item: None,
        async_playback_loader=True,
        playback_history_loader=lambda: HistoryRecord(
            id=1,
            key="yt:video:abc123",
            vod_name="YouTube",
            vod_pic="",
            vod_remarks="YouTube",
            episode=0,
            episode_url=history_url,
            position=22000,
            opening=0,
            ending=0,
            speed=1.0,
            create_time=1,
        ),
    )

    assert session.start_index == 0
    assert session.start_position_seconds == 22
    assert session.playlist[0].url == history_url
    assert session.playlist[0].original_url == "https://www.youtube.com/watch?v=abc123"


def test_player_controller_prefers_plugin_local_history_loader() -> None:
    api = FakeApiClient()
    api.history = HistoryRecord(
        id=1,
        key="movie-1",
        vod_name="API Movie",
        vod_pic="api-pic",
        vod_remarks="Episode 1",
        episode=0,
        episode_url="1.m3u8",
        position=1000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )
    controller = PlayerController(api)
    vod = VodItem(vod_id="movie-1", vod_name="Plugin Movie", vod_pic="plugin-pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="plugin:movie-1",
            vod_name="Plugin Movie",
            vod_pic="plugin-pic",
            vod_remarks="Episode 2",
            episode=1,
            episode_url="2.m3u8",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
        ),
    )

    assert api.history_calls == []
    assert session.start_index == 1
    assert session.start_position_seconds == 45
    assert session.speed == 1.25
    assert session.opening_seconds == 5
    assert session.ending_seconds == 10


def test_player_controller_preserves_history_progress_for_plugin_placeholder_playlist() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="/detail/drive", vod_name="Plugin Movie", vod_pic="plugin-pic")
    playlist = [PlayItem(title="查看", url="", vod_id="https://pan.baidu.com/s/demo")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="/detail/drive",
            vod_name="Plugin Movie",
            vod_pic="plugin-pic",
            vod_remarks="第2集",
            episode=1,
            episode_url="http://m/2.mp4",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
        ),
    )

    assert session.start_index == 0
    assert session.start_position_seconds == 45
    assert session.speed == 1.25
    assert session.opening_seconds == 5
    assert session.ending_seconds == 10


def test_player_controller_prefers_emby_local_history_loader() -> None:
    api = FakeApiClient()
    api.history = HistoryRecord(
        id=1,
        key="emby-1",
        vod_name="API Emby Movie",
        vod_pic="api-pic",
        vod_remarks="Episode 1",
        episode=0,
        episode_url="1.m3u8",
        position=1000,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=1,
    )
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie", vod_pic="emby-pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="emby-1",
            vod_name="Emby Movie",
            vod_pic="emby-pic",
            vod_remarks="Episode 2",
            episode=1,
            episode_url="2.m3u8",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
        ),
    )

    assert api.history_calls == []
    assert session.start_index == 1
    assert session.start_position_seconds == 45
    assert session.speed == 1.25


def test_player_controller_reports_progress_to_plugin_local_saver_without_backend_history() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-1", vod_name="Plugin Movie", vod_pic="poster")
    playlist = [PlayItem(title="第1集", url="https://media.example/1.m3u8")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=45,
        speed=1.25,
        opening_seconds=5,
        ending_seconds=10,
        paused=False,
    )

    assert len(saved_payloads) == 1
    assert saved_payloads[0]["key"] == "plugin-1"
    assert api.saved_payloads == []


def test_player_controller_reports_progress_to_jellyfin_local_saver_without_backend_history() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="jf-1", vod_name="Jellyfin Movie", vod_pic="poster")
    playlist = [PlayItem(title="Episode 1", url="https://media.example/1.m3u8")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=45,
        speed=1.25,
        opening_seconds=5,
        ending_seconds=10,
        paused=False,
    )

    assert len(saved_payloads) == 1
    assert saved_payloads[0]["key"] == "jf-1"
    assert api.saved_payloads == []


def test_player_controller_logs_session_creation(caplog) -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]

    with caplog.at_level(logging.INFO):
        controller.create_session(vod, playlist, clicked_index=0)

    assert "Create player session" in caplog.text
    assert "movie-1" in caplog.text


def test_player_controller_logs_progress_reporting(caplog) -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie", vod_pic="pic")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8")]
    session = controller.create_session(vod, playlist, clicked_index=0)

    with caplog.at_level(logging.INFO):
        controller.report_progress(
            session,
            current_index=0,
            position_seconds=12,
            speed=1.0,
            opening_seconds=0,
            ending_seconds=0,
            paused=False,
        )

    assert "Report playback progress" in caplog.text
    assert "movie-1" in caplog.text


def test_player_controller_restores_selected_playlist_group_from_history_loader() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-plugin")
    first_group = [
        PlayItem(title="第1集", url="https://backup.example/1.m3u8", play_source="备用线"),
        PlayItem(title="第2集", url="https://backup.example/2.m3u8", play_source="备用线"),
    ]
    second_group = [
        PlayItem(title="第1集", url="https://fast.example/1.m3u8", play_source="极速线"),
        PlayItem(title="第2集", url="https://fast.example/2.m3u8", play_source="极速线"),
    ]

    session = controller.create_session(
        vod,
        playlist=first_group,
        clicked_index=0,
        playlists=[first_group, second_group],
        playlist_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="plugin:plugin-vod-1",
            vod_name="Plugin Movie",
            vod_pic="poster-plugin",
            vod_remarks="第2集",
            episode=1,
            episode_url="https://fast.example/2.m3u8",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
            playlist_index=1,
        ),
    )

    assert session.playlist_index == 1
    assert session.playlist is second_group
    assert session.start_index == 1
    assert session.start_position_seconds == 45
    assert session.speed == 1.25


def test_player_controller_reports_progress_to_plugin_local_saver_without_api_history() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-plugin")
    playlist = [PlayItem(title="Episode 1", url="https://media.example/1.m3u8", vod_id="ep-1")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.5,
        opening_seconds=15,
        ending_seconds=30,
        paused=False,
    )

    assert api.saved_payloads == []
    assert len(saved_payloads) == 1
    assert saved_payloads[0]["key"] == "plugin-vod-1"
    assert saved_payloads[0]["vodName"] == "Plugin Movie"
    assert saved_payloads[0]["vodPic"] == "poster-plugin"
    assert saved_payloads[0]["vodRemarks"] == "Episode 1"
    assert saved_payloads[0]["episode"] == 0
    assert saved_payloads[0]["episodeUrl"] == "https://media.example/1.m3u8"
    assert saved_payloads[0]["position"] == 90000
    assert saved_payloads[0]["opening"] == 15000
    assert saved_payloads[0]["ending"] == 30000
    assert saved_payloads[0]["speed"] == 1.5
    assert saved_payloads[0]["playlistIndex"] == 0
    assert isinstance(saved_payloads[0]["createTime"], int)


def test_player_controller_reports_rewritten_episode_title_in_history_payload() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-plugin")
    playlist = [
        PlayItem(
            title="Episode 1",
            episode_display_title="第1集 星门初启",
            url="https://media.example/1.m3u8",
            vod_id="ep-1",
        )
    ]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.5,
        opening_seconds=15,
        ending_seconds=30,
        paused=False,
    )

    assert saved_payloads[0]["vodRemarks"] == "第1集 星门初启"


def test_player_controller_skips_remote_progress_reporter_for_paused_periodic_updates() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie", vod_pic="poster")
    playlist = [PlayItem(title="Episode 1", url="https://media.example/1.m3u8", vod_id="1-3458")]
    remote_calls: list[tuple[str, int, bool]] = []
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_progress_reporter=lambda item, position_ms, paused: remote_calls.append(
            (item.vod_id, position_ms, paused)
        ),
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=45,
        speed=1.0,
        opening_seconds=5,
        ending_seconds=10,
        paused=True,
    )

    assert remote_calls == []
    assert saved_payloads[0]["position"] == 45000
    assert saved_payloads[0]["opening"] == 5000
    assert saved_payloads[0]["ending"] == 10000


def test_player_controller_forces_remote_progress_reporter_for_paused_final_update() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie", vod_pic="poster")
    playlist = [PlayItem(title="Episode 1", url="https://media.example/1.m3u8", vod_id="1-3458")]
    remote_calls: list[tuple[str, int, bool]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_progress_reporter=lambda item, position_ms, paused: remote_calls.append(
            (item.vod_id, position_ms, paused)
        ),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=45,
        speed=1.0,
        opening_seconds=5,
        ending_seconds=10,
        paused=True,
        force_remote_report=True,
    )

    assert remote_calls == [("1-3458", 45000, True)]


def test_player_controller_reports_selected_playlist_index_to_plugin_local_saver() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie", vod_pic="poster-plugin")
    first_group = [PlayItem(title="第1集", url="https://backup.example/1.m3u8", play_source="备用线")]
    second_group = [PlayItem(title="第1集", url="https://fast.example/1.m3u8", play_source="极速线")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist=second_group,
        clicked_index=0,
        playlists=[first_group, second_group],
        playlist_index=1,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=30,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    assert api.saved_payloads == []
    assert saved_payloads[0]["playlistIndex"] == 1


def test_player_controller_reports_grouped_source_indexes_to_history_saver() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie")
    first = [PlayItem(title="第1集", url="https://q1/1.m3u8", play_source="夸克1")]
    second = [PlayItem(title="第1集", url="https://q2/1.m3u8", play_source="夸克2")]
    saved_payloads: list[dict[str, object]] = []

    session = controller.create_session(
        vod,
        playlist=second,
        clicked_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="夸克",
                sources=[
                    PlaybackSource(label="夸克1", playlist=first),
                    PlaybackSource(label="夸克2", playlist=second),
                ],
            )
        ],
        source_group_index=0,
        source_index=1,
        use_local_history=False,
        playback_history_saver=lambda payload: saved_payloads.append(payload),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=30,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    assert saved_payloads[0]["playlistIndex"] == 1
    assert saved_payloads[0]["sourceGroupIndex"] == 0
    assert saved_payloads[0]["sourceIndex"] == 1


def test_player_controller_reports_progress_via_session_hook_without_saving_history() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="1-3458")]
    progress_calls: list[tuple[str, int, bool]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        use_local_history=False,
        playback_progress_reporter=lambda item, position_ms, paused: progress_calls.append(
            (item.vod_id, position_ms, paused)
        ),
        playback_stopper=lambda item: progress_calls.append((item.vod_id, -1, False)),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=90,
        speed=1.25,
        opening_seconds=15,
        ending_seconds=30,
        paused=False,
    )
    controller.stop_playback(session, current_index=0)

    assert progress_calls == [("1-3458", 90000, False), ("1-3458", -1, False)]
    assert api.saved_payloads == []


def test_player_controller_forwards_paused_state_to_progress_reporter_when_forced() -> None:
    api = FakeApiClient()
    controller = PlayerController(api)
    vod = VodItem(vod_id="emby-1", vod_name="Emby Movie")
    playlist = [PlayItem(title="Episode 1", url="", vod_id="1-3458")]
    progress_calls: list[tuple[str, int, bool]] = []

    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        playback_progress_reporter=lambda item, position_ms, paused: progress_calls.append(
            (item.vod_id, position_ms, paused)
        ),
    )

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=45,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=True,
        force_remote_report=True,
    )

    assert progress_calls == [("1-3458", 45000, True)]


def test_player_controller_normalizes_single_playlist_into_one_group() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    playlist = [PlayItem(title="Episode 1", url="1.m3u8"), PlayItem(title="Episode 2", url="2.m3u8")]

    session = controller.create_session(vod, playlist, clicked_index=1)

    assert len(session.playlists) == 1
    assert session.playlist_index == 0
    assert [item.title for item in session.playlists[0]] == ["Episode 1", "Episode 2"]
    assert session.playlist is session.playlists[0]
    assert session.start_index == 1


def test_player_controller_normalizes_legacy_playlists_into_grouped_sources() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="movie-1", vod_name="Movie")
    first_group = [PlayItem(title="第1集", url="http://a/1.m3u8", play_source="备用线")]
    second_group = [PlayItem(title="第1集", url="http://b/1.m3u8", play_source="极速线")]

    session = controller.create_session(
        vod,
        playlist=second_group,
        clicked_index=0,
        playlists=[first_group, second_group],
        playlist_index=1,
    )

    assert [group.label for group in session.source_groups] == ["备用线", "极速线"]
    assert [source.label for source in session.source_groups[0].sources] == ["备用线"]
    assert [source.label for source in session.source_groups[1].sources] == ["极速线"]
    assert session.source_group_index == 1
    assert session.source_index == 0
    assert session.playlist is second_group


def test_player_controller_uses_selected_group_as_active_playlist() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="plugin-1", vod_name="Plugin Movie")
    first_group = [PlayItem(title="第1集", url="http://m/1.m3u8", play_source="备用线")]
    second_group = [
        PlayItem(title="第1集", url="http://b/1.m3u8", play_source="极速线"),
        PlayItem(title="第2集", url="http://b/2.m3u8", play_source="极速线"),
    ]

    session = controller.create_session(
        vod,
        playlist=second_group,
        clicked_index=1,
        playlists=[first_group, second_group],
        playlist_index=1,
    )

    assert len(session.playlists) == 2
    assert session.playlist_index == 1
    assert session.playlist is second_group
    assert [item.title for item in session.playlist] == ["第1集", "第2集"]
    assert session.start_index == 1


def test_player_controller_restores_selected_grouped_source_from_history_loader() -> None:
    controller = PlayerController(FakeApiClient())
    vod = VodItem(vod_id="plugin-vod-1", vod_name="Plugin Movie")
    baidu1 = [PlayItem(title="第1集", url="https://b1/1.m3u8", play_source="百度1")]
    baidu2 = [
        PlayItem(title="第1集", url="https://b2/1.m3u8", play_source="百度2"),
        PlayItem(title="第2集", url="https://b2/2.m3u8", play_source="百度2"),
    ]

    session = controller.create_session(
        vod,
        playlist=baidu1,
        clicked_index=0,
        source_groups=[
            PlaybackSourceGroup(
                label="百度",
                sources=[
                    PlaybackSource(label="百度1", playlist=baidu1),
                    PlaybackSource(label="百度2", playlist=baidu2),
                ],
            )
        ],
        source_group_index=0,
        source_index=0,
        use_local_history=False,
        playback_history_loader=lambda: HistoryRecord(
            id=0,
            key="plugin:plugin-vod-1",
            vod_name="Plugin Movie",
            vod_pic="",
            vod_remarks="第2集",
            episode=1,
            episode_url="https://b2/2.m3u8",
            position=45000,
            opening=5000,
            ending=10000,
            speed=1.25,
            create_time=2,
            playlist_index=1,
            source_group_index=0,
            source_index=1,
        ),
    )

    assert session.source_group_index == 0
    assert session.source_index == 1
    assert session.playlist is baidu2
    assert session.playlist_index == 1
    assert session.start_index == 1


class FakeDanmakuController:
    def __init__(self) -> None:
        self.calls: list[tuple[PlayItem, list[PlayItem]]] = []
        self.raise_on_call: Exception | None = None
        self.invalidate_calls = 0

    def prefetch_next_episode_danmaku(self, item: PlayItem, playlist: list[PlayItem]) -> None:
        self.calls.append((item, playlist))
        if self.raise_on_call is not None:
            raise self.raise_on_call

    def invalidate_running_danmaku_prefetches(self) -> None:
        self.invalidate_calls += 1


class FakeTimer:
    def __init__(self, delay_seconds: float, callback) -> None:
        self.delay_seconds = delay_seconds
        self.callback = callback
        self.started = False

    def start(self) -> None:
        self.started = True


class FakeTimerFactory:
    def __init__(self) -> None:
        self.timers: list[FakeTimer] = []

    def __call__(self, delay_seconds: float, callback):
        timer = FakeTimer(delay_seconds, callback)
        self.timers.append(timer)
        return timer


def _make_session_for_prefetch(
    controller: PlayerController,
    danmaku_controller: object | None,
):
    vod = VodItem(vod_id="series-1", vod_name="Series", vod_pic="pic")
    playlist = [
        PlayItem(title="第1集", url="1.mp4"),
        PlayItem(title="第2集", url="2.mp4"),
        PlayItem(title="第3集", url="3.mp4"),
    ]
    session = controller.create_session(
        vod,
        playlist,
        clicked_index=0,
        danmaku_controller=danmaku_controller,
    )
    return session, playlist


def test_on_item_started_schedules_delayed_prefetch_instead_of_running_immediately() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)

    assert danmaku_controller.calls == []
    assert len(timer_factory.timers) == 1
    assert timer_factory.timers[0].delay_seconds == 10.0
    assert timer_factory.timers[0].started is True


def test_delayed_prefetch_callback_runs_prefetch_after_timer_fires() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    timer_factory.timers[0].callback()

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[1]
    assert danmaku_controller.calls[0][1] is session.playlist
    assert 1 in session.prefetched_next_danmaku_indices


def test_latest_on_item_started_invalidates_older_delayed_prefetch_callback() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    first_callback = timer_factory.timers[0].callback
    controller.on_item_started(session, current_index=1)
    second_callback = timer_factory.timers[1].callback

    first_callback()
    second_callback()

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[2]
    assert 1 not in session.prefetched_next_danmaku_indices
    assert 2 in session.prefetched_next_danmaku_indices


def test_on_item_started_noop_when_next_index_out_of_range() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=len(session.playlist) - 1)

    assert timer_factory.timers == []
    assert danmaku_controller.calls == []
    assert session.prefetched_next_danmaku_indices == set()


def test_delayed_prefetch_discards_index_when_prefetcher_raises() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    danmaku_controller.raise_on_call = RuntimeError("boom")
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    timer_factory.timers[0].callback()

    assert session.prefetched_next_danmaku_indices == set()
    assert len(danmaku_controller.calls) == 1


def test_on_item_started_skips_when_controller_lacks_prefetch() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory

    class NoPrefetchController:
        pass

    session, _ = _make_session_for_prefetch(controller, NoPrefetchController())
    controller.on_item_started(session, current_index=0)
    assert timer_factory.timers == []
    assert session.prefetched_next_danmaku_indices == set()
    assert session.pending_next_danmaku_prefetch_token == 0


def test_on_item_started_skips_when_danmaku_controller_is_none() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    session, _ = _make_session_for_prefetch(controller, None)

    controller.on_item_started(session, current_index=0)

    assert timer_factory.timers == []
    assert session.prefetched_next_danmaku_indices == set()


def test_stop_playback_invalidates_pending_delayed_prefetch() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.stop_playback(session, current_index=0)
    timer_factory.timers[0].callback()

    assert danmaku_controller.calls == []
    assert session.prefetched_next_danmaku_indices == set()


def test_reset_next_episode_danmaku_prefetch_state_clears_indices_and_invalidates_token() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)
    session.prefetched_next_danmaku_indices.add(1)
    session.pending_next_danmaku_prefetch_token = 7

    controller.reset_next_episode_danmaku_prefetch_state(session)

    assert session.prefetched_next_danmaku_indices == set()
    assert session.pending_next_danmaku_prefetch_token == 8
    assert danmaku_controller.invalidate_calls == 1


def test_report_progress_tail_prefetch_triggers_when_remaining_under_150s() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )

    assert len(danmaku_controller.calls) == 1
    assert 1 in session.prefetched_next_danmaku_indices


def test_report_progress_tail_prefetch_skipped_when_duration_too_short() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 13,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 14,
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_remaining_too_long() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 10,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_paused() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=True,
        duration_seconds=60 * 20,
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_skipped_when_duration_unknown() -> None:
    controller = PlayerController(FakeApiClient())
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
    )

    assert danmaku_controller.calls == []


def test_report_progress_tail_prefetch_deduplicates_with_on_item_started() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )

    assert len(danmaku_controller.calls) == 1
    assert timer_factory.timers[0].started is True


def test_report_progress_tail_prefetch_triggers_immediately_even_with_startup_delay() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )

    assert len(danmaku_controller.calls) == 1
    assert danmaku_controller.calls[0][0] is session.playlist[1]
    assert 1 in session.prefetched_next_danmaku_indices


def test_delayed_prefetch_callback_noops_after_tail_prefetch_already_succeeded() -> None:
    controller = PlayerController(FakeApiClient())
    timer_factory = FakeTimerFactory()
    controller._prefetch_timer_factory = timer_factory
    danmaku_controller = FakeDanmakuController()
    session, _ = _make_session_for_prefetch(controller, danmaku_controller)

    controller.on_item_started(session, current_index=0)
    delayed_callback = timer_factory.timers[0].callback
    controller.report_progress(
        session,
        current_index=0,
        position_seconds=60 * 18,
        speed=1.0,
        opening_seconds=0,
        ending_seconds=0,
        paused=False,
        duration_seconds=60 * 20,
    )
    delayed_callback()

    assert len(danmaku_controller.calls) == 1
