from pathlib import Path

from atv_player.controllers.player_controller import PlayerSession
from atv_player.models import PlayItem, VodItem
from atv_player.subtitles.models import (
    SubtitleContent,
    SubtitleProviderGroup,
    SubtitleSearchItem,
    SubtitleSearchResult,
)
from atv_player.ui.player_window import PlayerWindow


class FakePlayerController:
    def report_progress(self, *args, **kwargs) -> None:
        return None

    def resolve_play_item_detail(self, session, play_item):
        return None

    def stop_playback(self, session, current_index: int) -> None:
        return None


class FakeVideo:
    """最小视频桩，避免测试里真的拉起 mpv 去加载网络地址。"""

    def __init__(self) -> None:
        self.load_calls: list[tuple[str, bool, int]] = []

    def load(
        self,
        url: str,
        pause: bool = False,
        start_seconds: int = 0,
        headers: dict[str, str] | None = None,
        poster_image_path: str | None = None,
    ) -> None:
        del headers, poster_image_path
        self.load_calls.append((url, pause, start_seconds))

    def set_speed(self, speed: float) -> None:
        return None

    def set_volume(self, value: int) -> None:
        return None

    def position_seconds(self) -> int:
        return 0


class FakeSubtitleService:
    def __init__(self, result: SubtitleSearchResult) -> None:
        self._result = result
        self.searched_queries: list[object] = []
        self.downloaded: list[SubtitleSearchItem] = []

    @property
    def provider_order(self) -> list[str]:
        return ["subdl", "subhd"]

    def provider_label(self, provider_id: str) -> str:
        return {"subdl": "SubDL", "subhd": "SubHD"}.get(provider_id, provider_id)

    def search(self, query, *, provider_filter: str = "") -> SubtitleSearchResult:
        self.searched_queries.append(query)
        return self._result

    def download(self, item: SubtitleSearchItem) -> SubtitleContent:
        self.downloaded.append(item)
        return SubtitleContent(
            text="1\n00:00:01,000 --> 00:00:02,000\n你好\n",
            suffix=".srt",
            name="hello.srt",
        )


def _item(
    subtitle_id: str, *, language: str, percent: int, name: str
) -> SubtitleSearchItem:
    labels = {"chs_eng": "简英双语", "eng": "English"}
    return SubtitleSearchItem(
        provider="subdl",
        provider_label="SubDL",
        subtitle_id=subtitle_id,
        name=name,
        language=language,
        language_label=labels.get(language, language),
        format="srt",
        match_percent=percent,
        score=percent,
    )


def _result() -> SubtitleSearchResult:
    return SubtitleSearchResult(
        groups=[
            SubtitleProviderGroup(
                provider="subdl",
                provider_label="SubDL",
                items=[
                    _item(
                        "1",
                        language="chs_eng",
                        percent=96,
                        name="Show.S01E02.chs&eng",
                    ),
                    _item("2", language="eng", percent=70, name="Show.S01E02.eng"),
                ],
            )
        ],
        errors={"zimuku": "触发了验证码"},
        skipped=["assrt"],
    )


def _session(service: FakeSubtitleService | None) -> PlayerSession:
    return PlayerSession(
        vod=VodItem(vod_id="s1", vod_name="Show"),
        playlist=[
            PlayItem(
                title="第2集",
                original_title="Show.S01E02.1080p.WEB-DL.x265-GRP.mkv",
                url="http://example.com/2.mkv",
            )
        ],
        start_index=0,
        start_position_seconds=0,
        speed=1.0,
        subtitle_search_service=service,
    )


def _make_window(qtbot, service: FakeSubtitleService | None) -> PlayerWindow:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    window.open_session(_session(service))
    return window


def _open_dialog(qtbot) -> tuple[PlayerWindow, FakeSubtitleService]:
    service = FakeSubtitleService(_result())
    window = _make_window(qtbot, service)
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: bool(window._subtitle_search_items), timeout=3000)
    return window, service


def test_dialog_autosearches_with_parsed_release_context(qtbot) -> None:
    _window, service = _open_dialog(qtbot)

    assert len(service.searched_queries) == 1
    query = service.searched_queries[0]
    assert query.title == "Show"
    assert query.episode == 2
    # 画质/编码/压制组来自文件名解析，只参与打分，不进搜索关键词
    assert query.resolution == "1080p"
    assert query.codec == "H.265"
    assert query.release_group == "GRP"


def test_switching_playback_resets_stale_search_context(qtbot) -> None:
    """换片/换集后重新打开对话框，应显示新片名并按新片名搜，而不是沿用旧的。"""
    window, service = _open_dialog(qtbot)
    assert service.searched_queries[0].title == "Show"

    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="m1", vod_name="Movie"),
            playlist=[
                PlayItem(
                    title="正片",
                    original_title="Movie.2024.1080p.WEB-DL.x265-GRP.mkv",
                    url="http://example.com/m.mkv",
                )
            ],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
            subtitle_search_service=service,
        )
    )
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: len(service.searched_queries) >= 2, timeout=3000)

    assert window._subtitle_search_title_edit.text() == "Movie"
    assert service.searched_queries[-1].title == "Movie"
    # 旧片的搜索结果不该留在表里误导下载
    rows = window._subtitle_search_table.rowCount()
    assert rows == len(
        [
            item
            for item in window._subtitle_search_items
            if not window._subtitle_search_language_filter()
            or item.language == window._subtitle_search_language_filter()
        ]
    )


def test_manually_entered_title_survives_context_switch(qtbot) -> None:
    """用户手改过片名时，切集后不应被重置覆盖。"""
    window, service = _open_dialog(qtbot)
    window._subtitle_search_title_edit.setText("My.Custom.Title")
    window.open_session(
        PlayerSession(
            vod=VodItem(vod_id="m2", vod_name="Another"),
            playlist=[
                PlayItem(
                    title="正片",
                    original_title="Another.2024.1080p.WEB-DL.x265-GRP.mkv",
                    url="http://example.com/a.mkv",
                )
            ],
            start_index=0,
            start_position_seconds=0,
            speed=1.0,
            subtitle_search_service=service,
        )
    )

    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: len(service.searched_queries) >= 2, timeout=3000)

    assert window._subtitle_search_title_edit.text() == "My.Custom.Title"
    assert service.searched_queries[-1].title == "My.Custom.Title"


def test_manually_entered_media_ids_are_sent_to_providers(qtbot) -> None:
    """中文片名在英文站搜不到时，用户填 TMDB/IMDb id 后应按 id 搜。"""
    _window, service = _open_dialog(qtbot)
    window = _make_window(qtbot, service)
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: bool(window._subtitle_search_items), timeout=3000)

    window._subtitle_search_tmdb_id_edit.setText("105923")
    window._subtitle_search_imdb_id_edit.setText("tt1234567")
    service.searched_queries.clear()
    window._start_subtitle_search()
    qtbot.waitUntil(lambda: len(service.searched_queries) >= 1, timeout=3000)

    query = service.searched_queries[-1]
    assert query.tmdb_id == "105923"
    assert query.imdb_id == "tt1234567"


def test_tmdb_id_auto_filled_from_scrape_binding(qtbot) -> None:
    """刮削绑定到 TMDB 后，打开对话框应自动带上 TMDB id。"""
    service = FakeSubtitleService(_result())

    class FakeBindings:
        def load_by_title(self, title):
            from atv_player.metadata.bindings import MetadataBinding

            return MetadataBinding(
                normalized_title="show",
                normalized_year="",
                provider="tmdb",
                provider_id="105923",
            )

    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    window.video = FakeVideo()
    session = _session(service)
    session.metadata_binding_repository = FakeBindings()
    window.open_session(session)
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: bool(window._subtitle_search_items), timeout=3000)

    assert window._subtitle_search_tmdb_id_edit.text() == "105923"
    assert service.searched_queries[0].tmdb_id == "105923"


def test_no_token_configured_guides_user_to_set_up_assrt(qtbot) -> None:
    """没配任何 Token、免 Token 站又都不可用时，应明确提示去配 ASSRT Token。"""
    empty = SubtitleSearchResult(
        groups=[], skipped=["subdl", "assrt", "opensubtitles"]
    )
    service = FakeSubtitleService(empty)
    window = _make_window(qtbot, service)
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(
        lambda: window._subtitle_search_result is not None, timeout=3000
    )

    status = window._subtitle_search_status_label.text()
    assert "射手网" in status or "ASSRT" in status
    assert "Token" in status



def test_table_lists_results_with_match_percentage(qtbot) -> None:
    window, _service = _open_dialog(qtbot)
    table = window._subtitle_search_table

    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "SubDL"
    assert table.item(0, 2).text() == "简英双语"
    assert table.item(0, 4).text() == "96%"


def test_status_reports_failed_and_skipped_sites(qtbot) -> None:
    window, _service = _open_dialog(qtbot)
    status = window._subtitle_search_status_label.text()

    assert "共 2 条" in status
    assert "触发了验证码" in status
    assert "未配置 Token 已跳过" in status


def test_language_filter_narrows_rows(qtbot) -> None:
    window, _service = _open_dialog(qtbot)
    combo = window._subtitle_search_language_combo
    combo.setCurrentIndex(combo.findData("eng"))

    table = window._subtitle_search_table
    assert table.rowCount() == 1
    assert table.item(0, 2).text() == "English"


def test_download_attaches_external_subtitle_and_selects_it(
    qtbot, tmp_path, monkeypatch
) -> None:
    import atv_player.ui.player_window as player_window_module

    saved = tmp_path / "hello.srt"

    def fake_save(content, *, title=""):
        saved.write_text(content.text, encoding="utf-8")
        return saved

    monkeypatch.setattr(player_window_module, "save_subtitle_file", fake_save)

    window, service = _open_dialog(qtbot)
    applied: list[tuple[str, str]] = []
    # 只验证挂载逻辑本身，mpv 侧的刷新在别处已有覆盖
    window._refresh_subtitle_state = lambda *args, **kwargs: None
    window._set_primary_subtitle_from_menu = lambda mode, url: applied.append(
        (mode, url)
    )

    window._subtitle_search_table.selectRow(0)
    window._download_selected_subtitle()
    qtbot.waitUntil(lambda: bool(service.downloaded), timeout=3000)
    qtbot.waitUntil(lambda: bool(applied), timeout=3000)

    subtitles = window._current_play_item().external_subtitles
    assert len(subtitles) == 1
    assert subtitles[0].source == "subtitle-site"
    assert subtitles[0].url == str(saved)
    assert "简英双语" in subtitles[0].name
    # 走的是既有的 external 通道，而不是另起一套加载逻辑
    assert applied == [("external", str(saved))]
    assert saved.read_text(encoding="utf-8").startswith("1\n")


def test_download_can_target_secondary_slot(qtbot, tmp_path, monkeypatch) -> None:
    import atv_player.ui.player_window as player_window_module

    saved = tmp_path / "second.srt"
    monkeypatch.setattr(
        player_window_module,
        "save_subtitle_file",
        lambda content, *, title="": (saved.write_text(content.text), saved)[1],
    )

    window, service = _open_dialog(qtbot)
    applied: list[tuple[str, str]] = []
    window._refresh_subtitle_state = lambda *args, **kwargs: None
    window._set_secondary_subtitle_from_menu = lambda mode, url: applied.append(
        (mode, url)
    )

    window._subtitle_search_table.selectRow(0)
    window._download_selected_subtitle(secondary=True)
    qtbot.waitUntil(lambda: bool(applied), timeout=3000)

    assert applied == [("external", str(saved))]


class SubtitleCapableVideo(FakeVideo):
    """带字幕能力的视频桩，用于验证下载的字幕真的进了字幕下拉框。"""

    def __init__(self) -> None:
        super().__init__()
        self.external_loads: list[tuple[str, bool]] = []
        self.applied_modes: list[tuple[str, object]] = []
        self._next_track_id = 100

    def subtitle_tracks(self) -> list:
        return []

    def audio_tracks(self) -> list:
        return []

    def apply_subtitle_mode(self, mode: str, track_id: object = None) -> None:
        self.applied_modes.append((mode, track_id))

    def apply_secondary_subtitle_mode(self, mode: str, track_id: object = None) -> None:
        self.applied_modes.append((f"secondary:{mode}", track_id))

    def current_subtitle_track_id(self) -> int | None:
        return None

    def load_external_subtitle(
        self, path: str, *, select_for_secondary: bool = False
    ) -> int:
        self.external_loads.append((path, select_for_secondary))
        self._next_track_id += 1
        return self._next_track_id


def test_downloaded_subtitle_enters_subtitle_combo_and_gets_selected(
    qtbot, tmp_path, monkeypatch
) -> None:
    """端到端验证复用的是既有外挂字幕通道，而不是另起一套加载逻辑。"""
    import atv_player.ui.player_window as player_window_module

    saved = tmp_path / "combo.srt"
    monkeypatch.setattr(
        player_window_module,
        "save_subtitle_file",
        lambda content, *, title="": (
            saved.write_text(content.text, encoding="utf-8"),
            saved,
        )[1],
    )

    service = FakeSubtitleService(_result())
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    video = SubtitleCapableVideo()
    window.video = video
    window.open_session(_session(service))
    window._open_subtitle_search_dialog()
    qtbot.waitUntil(lambda: bool(window._subtitle_search_items), timeout=3000)

    window._subtitle_search_table.selectRow(0)
    window._download_selected_subtitle()
    qtbot.waitUntil(lambda: bool(service.downloaded), timeout=3000)
    qtbot.waitUntil(
        lambda: bool(window._current_play_item().external_subtitles), timeout=3000
    )

    # 下拉框里应该出现这条外挂字幕（说明走通了 _refresh_subtitle_state 的重建）
    entries = [
        window.subtitle_combo.itemData(index)
        for index in range(window.subtitle_combo.count())
    ]
    external_urls = [
        getattr(data[2], "url", None)
        for data in entries
        if isinstance(data, tuple) and len(data) == 3 and data[0] == "external"
    ]
    assert str(saved) in external_urls
    # 并且确实被送进了 mpv 的外挂字幕通道。注意既有实现会把内容另写一份临时文件
    # 再交给 mpv，所以这里比对的是内容而不是路径。
    qtbot.waitUntil(lambda: bool(video.external_loads), timeout=3000)
    loaded_path = Path(video.external_loads[0][0])
    assert loaded_path.exists()
    assert "你好" in loaded_path.read_text(encoding="utf-8")
    assert video.external_loads[0][1] is False


def test_context_menu_and_shortcut_expose_subtitle_search(qtbot) -> None:
    window = PlayerWindow(FakePlayerController())
    qtbot.addWidget(window)
    menu = window._build_video_context_menu()

    assert any(action.text() == "搜索字幕" for action in menu.actions())
    sequences = {shortcut.key().toString() for shortcut in window._shortcut_bindings}
    assert "C" in sequences


def test_dialog_is_not_built_without_service(qtbot) -> None:
    window = _make_window(qtbot, None)
    window._open_subtitle_search_dialog()

    assert window._subtitle_search_dialog is None
