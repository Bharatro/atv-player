import sqlite3
from pathlib import Path

import pytest

from atv_player.models import AppConfig
from atv_player.plugins.repository import SpiderPluginRepository
from atv_player.storage import SettingsRepository


def test_local_playback_history_repository_round_trip_emby_source_metadata(tmp_path: Path) -> None:
    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(tmp_path / "app.db")
    repo.save_history(
        "emby",
        "emby-1",
        {
            "vodName": "Emby Movie",
            "vodPic": "poster",
            "vodRemarks": "Episode 2",
            "episode": 1,
            "episodeUrl": "2.m3u8",
            "position": 45000,
            "opening": 0,
            "ending": 0,
            "speed": 1.25,
            "playlistIndex": 1,
            "createTime": 1713206400000,
        },
        source_name="Emby",
    )

    history = repo.get_history("emby", "emby-1")

    assert history is not None
    assert history.source_kind == "emby"
    assert history.source_key == ""
    assert history.source_name == "Emby"


def test_local_playback_history_repository_lists_and_deletes_jellyfin_records(tmp_path: Path) -> None:
    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(tmp_path / "app.db")
    repo.save_history(
        "jellyfin",
        "jf-1",
        {
            "vodName": "Jellyfin Movie",
            "vodPic": "poster",
            "vodRemarks": "Episode 1",
            "episode": 0,
            "episodeUrl": "1.m3u8",
            "position": 10000,
            "opening": 0,
            "ending": 0,
            "speed": 1.0,
            "playlistIndex": 0,
            "createTime": 1713206400001,
        },
        source_name="Jellyfin",
    )

    records = repo.list_histories()
    repo.delete_history("jellyfin", "jf-1")

    assert [record.source_kind for record in records] == ["jellyfin"]
    assert repo.get_history("jellyfin", "jf-1") is None


def test_local_playback_history_repository_round_trip_feiniu_source_metadata(tmp_path: Path) -> None:
    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(tmp_path / "app.db")
    repo.save_history(
        "feiniu",
        "fn-1",
        {
            "vodName": "Feiniu Movie",
            "vodPic": "poster",
            "vodRemarks": "Episode 2",
            "episode": 1,
            "episodeUrl": "2.m3u8",
            "position": 45000,
            "opening": 0,
            "ending": 0,
            "speed": 1.25,
            "playlistIndex": 1,
            "createTime": 1713206400000,
        },
        source_name="飞牛影视",
    )

    history = repo.get_history("feiniu", "fn-1")

    assert history is not None
    assert history.source_kind == "feiniu"
    assert history.source_name == "飞牛影视"


def test_local_playback_history_round_trip_persists_grouped_source_indexes(tmp_path: Path) -> None:
    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(tmp_path / "app.db")
    repo.save_history(
        "spider_plugin",
        "detail-1",
        {
            "vodName": "红果短剧",
            "vodPic": "",
            "vodRemarks": "第2集",
            "episode": 1,
            "episodeUrl": "https://b2/2.m3u8",
            "position": 90000,
            "opening": 5000,
            "ending": 10000,
            "speed": 1.25,
            "playlistIndex": 3,
            "sourceGroupIndex": 1,
            "sourceIndex": 1,
            "createTime": 42,
        },
        source_key="7",
        source_name="红果短剧",
    )

    history = repo.get_history("spider_plugin", "detail-1", source_key="7")

    assert history is not None
    assert history.playlist_index == 3
    assert history.source_group_index == 1
    assert history.source_index == 1


def test_local_playback_history_repository_migrates_spider_plugin_legacy_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                display_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL,
                cached_file_path TEXT NOT NULL DEFAULT '',
                last_loaded_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                config_text TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE spider_plugin_playback_history (
                plugin_id INTEGER NOT NULL,
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                playlist_index INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (plugin_id, vod_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugins (
                id, source_type, source_value, display_name, enabled, sort_order,
                cached_file_path, last_loaded_at, last_error, config_text
            )
            VALUES (1, 'local', '/plugins/demo.py', '红果短剧', 1, 0, '', 0, '', '')
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugin_playback_history (
                plugin_id, vod_id, vod_name, vod_pic, vod_remarks, episode,
                episode_url, position, opening, ending, speed, playlist_index, updated_at
            )
            VALUES (1, 'detail-1', '红果短剧', 'poster', '第2集', 1, '2.m3u8', 45000, 0, 0, 1.0, 0, 1713206400000)
            """
        )

    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(db_path)
    records = repo.list_histories()

    assert len(records) == 1
    assert records[0].source_kind == "spider_plugin"
    assert records[0].source_key == "1"
    assert records[0].source_name == "红果短剧"
    assert records[0].key == "detail-1"


def test_local_playback_history_repository_reads_legacy_spider_plugin_rows_without_source_key(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE media_playback_history (
                source_kind TEXT NOT NULL,
                source_key TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                playlist_index INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (source_kind, source_key, vod_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO media_playback_history (
                source_kind, source_key, source_name, vod_id, vod_name, vod_pic,
                vod_remarks, episode, episode_url, position, opening, ending,
                speed, playlist_index, updated_at
            )
            VALUES ('spider_plugin', '', '红果短剧', 'detail-1', '红果短剧', 'poster', '第2集', 1, '2.m3u8', 45000, 0, 0, 1.0, 0, 1713206400000)
            """
        )

    from atv_player.local_playback_history import LocalPlaybackHistoryRepository

    repo = LocalPlaybackHistoryRepository(db_path)
    history = repo.get_history("spider_plugin", "detail-1", source_key="7")

    assert history is not None
    assert history.key == "detail-1"
    assert history.source_key == ""
    assert history.episode == 1


def test_settings_repository_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        last_path="/Movies",
        last_selected_tab="history",
        last_selected_category_tab="telegram",
        last_selected_category_id="movie",
        last_active_window="player",
        last_playback_mode="folder",
        last_playback_path="/Movies",
        last_playback_vod_id="vod-1",
        last_playback_clicked_vod_id="vod-2",
        last_player_paused=True,
        player_volume=35,
        player_muted=True,
        main_window_geometry=None,
        player_window_geometry=None,
        player_main_splitter_state=b"split-main",
        browse_content_splitter_state=b"split-browse",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved == config


def test_settings_repository_round_trip_persists_preferred_parse_key(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        preferred_parse_key="jx2",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.preferred_parse_key == "jx2"
    assert saved == config


def test_settings_repository_round_trip_persists_global_search_history(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        global_search_history=["庆余年", "琅琊榜", "藏海传"],
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.global_search_history == ["庆余年", "琅琊榜", "藏海传"]
    assert saved == config


def test_settings_repository_round_trip_persists_global_search_hot_source(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        global_search_hot_source="iqiyi",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.global_search_hot_source == "iqiyi"
    assert saved == config


def test_settings_repository_round_trip_persists_playback_settings(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        youtube_cookie_browser="edge",
        mpv_cache_size_mb=768,
        mpv_hwdec_mode="no",
        mpv_network_timeout_seconds=25,
        mpv_default_readahead_secs=45,
        mpv_extra_options="demuxer-max-back-bytes=256M\ncache-pause-wait=8",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.youtube_cookie_browser == "edge"
    assert saved.mpv_cache_size_mb == 768
    assert saved.mpv_hwdec_mode == "no"
    assert saved.mpv_network_timeout_seconds == 25
    assert saved.mpv_default_readahead_secs == 45
    assert saved.mpv_extra_options == "demuxer-max-back-bytes=256M\ncache-pause-wait=8"
    assert saved == config


def test_settings_repository_round_trip_persists_playback_auto_switch_source_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        playback_auto_switch_source_on_failure=True,
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.playback_auto_switch_source_on_failure is True
    assert saved == config


def test_settings_repository_migrates_missing_playback_settings_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO app_config (id, base_url, username, token, vod_token, last_path) VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')"
        )

    config = SettingsRepository(db_path).load_config()

    assert config.youtube_cookie_browser == ""
    assert config.mpv_cache_size_mb == 512
    assert config.mpv_hwdec_mode == "auto-safe"
    assert config.mpv_network_timeout_seconds == 15
    assert config.mpv_default_readahead_secs == 20
    assert config.mpv_extra_options == ""


def test_settings_repository_migrates_missing_playback_auto_switch_source_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO app_config (id, base_url, username, token, vod_token, last_path) VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')"
        )

    config = SettingsRepository(db_path).load_config()

    assert config.playback_auto_switch_source_on_failure is False


def test_settings_repository_round_trip_persists_metadata_credentials(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        metadata_douban_cookie="bid=demo; ll=118282",
        metadata_tmdb_api_key="tmdb-demo-key",
        metadata_bangumi_access_token="bgm-demo-token",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.metadata_douban_cookie == "bid=demo; ll=118282"
    assert saved.metadata_tmdb_api_key == "tmdb-demo-key"
    assert saved.metadata_bangumi_access_token == "bgm-demo-token"
    assert saved == config


def test_settings_repository_round_trip_persists_metadata_enhancement_toggle(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        metadata_enhancement_enabled=False,
        metadata_douban_cookie="bid=demo; ll=118282",
        metadata_tmdb_api_key="tmdb-demo-key",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.metadata_enhancement_enabled is False
    assert saved.metadata_douban_cookie == "bid=demo; ll=118282"
    assert saved.metadata_tmdb_api_key == "tmdb-demo-key"
    assert saved == config


def test_settings_repository_round_trip_persists_network_proxy_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        network_proxy_mode="socks5",
        network_proxy_url="socks5://user:pass@127.0.0.1:1080",
        network_proxy_bypass_rules=["localhost", "127.0.0.1", "10.0.0.0/8"],
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.network_proxy_mode == "socks5"
    assert saved.network_proxy_url == "socks5://user:pass@127.0.0.1:1080"
    assert saved.network_proxy_bypass_rules == ["localhost", "127.0.0.1", "10.0.0.0/8"]


def test_settings_repository_round_trip_persists_episode_title_enhancement_toggle(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        episode_title_enhancement_enabled=False,
        metadata_tmdb_api_key="tmdb-demo-key",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.episode_title_enhancement_enabled is False
    assert saved.metadata_tmdb_api_key == "tmdb-demo-key"
    assert saved == config


def test_settings_repository_migrates_missing_metadata_credential_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]',
                global_search_hot_source TEXT NOT NULL DEFAULT '360'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, player_log_visible, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode,
                preferred_danmaku_uniform_color, preferred_danmaku_position_preset,
                preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history, global_search_hot_source
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', '/', 'main', 'browse', '', '', '', '', '',
                0, 100, 0, 0, 1, '', 1, 1, 'static', 'source', '#FFFFFF', 'top', 1.0, 32,
                NULL, NULL, NULL, NULL, 'douban', '', '', '[]', '360'
            )
            """
        )

    repo = SettingsRepository(db_path)
    config = repo.load_config()

    assert config.metadata_douban_cookie == ""
    assert config.metadata_tmdb_api_key == ""
    assert config.metadata_bangumi_access_token == ""


def test_settings_repository_migrates_missing_metadata_enhancement_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]',
                global_search_hot_source TEXT NOT NULL DEFAULT '360'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, metadata_douban_cookie,
                metadata_tmdb_api_key, last_path, last_active_window, last_playback_source,
                last_playback_source_key, last_playback_mode, last_playback_path,
                last_playback_vod_id, last_playback_clicked_vod_id, last_player_paused,
                player_volume, player_muted, player_wide_mode, player_log_visible,
                preferred_parse_key, preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode,
                preferred_danmaku_uniform_color, preferred_danmaku_position_preset,
                preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history, global_search_hot_source
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', '', '', '/', 'main', 'browse', '', '', '', '', '',
                0, 100, 0, 0, 1, '', 1, 1, 'static', 'source', '#FFFFFF', 'top', 1.0, 32,
                NULL, NULL, NULL, NULL, 'douban', '', '', '[]', '360'
            )
            """
        )

    repo = SettingsRepository(db_path)
    config = repo.load_config()

    assert config.metadata_enhancement_enabled is True


def test_settings_repository_migrates_missing_episode_title_enhancement_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]',
                global_search_hot_source TEXT NOT NULL DEFAULT '360'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, metadata_enhancement_enabled,
                metadata_douban_cookie, metadata_tmdb_api_key, last_path, last_active_window,
                last_playback_source, last_playback_source_key, last_playback_mode, last_playback_path,
                last_playback_vod_id, last_playback_clicked_vod_id, last_player_paused,
                player_volume, player_muted, player_wide_mode, player_log_visible,
                preferred_parse_key, preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode,
                preferred_danmaku_uniform_color, preferred_danmaku_position_preset,
                preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history, global_search_hot_source
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', 1, '', '', '/', 'main', 'browse', '', '', '', '', '',
                0, 100, 0, 0, 1, '', 1, 1, 'static', 'source', '#FFFFFF', 'top', 1.0, 32,
                NULL, NULL, NULL, NULL, 'douban', '', '', '[]', '360'
            )
            """
        )

    repo = SettingsRepository(db_path)
    config = repo.load_config()

    assert config.episode_title_enhancement_enabled is True


def test_settings_repository_migrates_missing_network_proxy_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                metadata_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                episode_title_enhancement_enabled INTEGER NOT NULL DEFAULT 1,
                metadata_douban_cookie TEXT NOT NULL DEFAULT '',
                metadata_tmdb_api_key TEXT NOT NULL DEFAULT '',
                metadata_bangumi_access_token TEXT NOT NULL DEFAULT '',
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, metadata_enhancement_enabled,
                episode_title_enhancement_enabled, metadata_douban_cookie,
                metadata_tmdb_api_key, metadata_bangumi_access_token, last_path
            )
            VALUES (1, 'http://127.0.0.1:4567', '', '', '', 1, 1, '', '', '', '/')
            """
        )

    config = SettingsRepository(db_path).load_config()

    assert config.network_proxy_mode == "direct"
    assert config.network_proxy_url == ""
    assert config.network_proxy_bypass_rules == [
        "localhost",
        "127.0.0.1",
        "::1",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        ".local",
    ]


def test_settings_repository_migrates_missing_global_search_hot_source_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                player_log_visible INTEGER NOT NULL DEFAULT 1,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static',
                preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source',
                preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF',
                preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top',
                preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0,
                preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT '',
                global_search_history TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, player_log_visible, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                preferred_danmaku_render_mode, preferred_danmaku_color_mode,
                preferred_danmaku_uniform_color, preferred_danmaku_position_preset,
                preferred_danmaku_scroll_speed, preferred_danmaku_font_size,
                main_window_geometry, player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state, last_selected_tab, last_selected_category_tab,
                last_selected_category_id, global_search_history
            )
            VALUES (
                1, 'http://127.0.0.1:4567', '', '', '', '/', 'main', 'browse', '', '', '', '', '',
                0, 100, 0, 0, 1, '', 1, 1, 'static', 'source', '#FFFFFF', 'top', 1.0, 32,
                NULL, NULL, NULL, NULL, 'douban', '', '', '[]'
            )
            """
        )

    repo = SettingsRepository(db_path)

    assert repo.load_config().global_search_hot_source == "360"


def test_settings_repository_round_trip_persists_preferred_danmaku_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        preferred_danmaku_enabled=False,
        preferred_danmaku_line_count=4,
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.preferred_danmaku_enabled is False
    assert saved.preferred_danmaku_line_count == 4
    assert saved == config


def test_settings_repository_loads_new_danmaku_render_defaults(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")

    config = repo.load_config()

    assert config.preferred_danmaku_render_mode == "static"
    assert config.preferred_danmaku_color_mode == "source"
    assert config.preferred_danmaku_uniform_color == "#FFFFFF"
    assert config.preferred_danmaku_position_preset == "top"
    assert config.preferred_danmaku_scroll_speed == 1.0
    assert config.preferred_danmaku_font_size == 32


def test_settings_repository_persists_new_danmaku_render_settings(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "app.db")
    config = repo.load_config()
    config.preferred_danmaku_render_mode = "mixed"
    config.preferred_danmaku_color_mode = "source"
    config.preferred_danmaku_uniform_color = "#00FF00"
    config.preferred_danmaku_position_preset = "mid_upper"
    config.preferred_danmaku_scroll_speed = 0.8
    config.preferred_danmaku_font_size = 40
    config.preferred_danmaku_line_count = 8

    repo.save_config(config)

    reloaded = repo.load_config()

    assert reloaded.preferred_danmaku_render_mode == "mixed"
    assert reloaded.preferred_danmaku_color_mode == "source"
    assert reloaded.preferred_danmaku_uniform_color == "#00FF00"
    assert reloaded.preferred_danmaku_position_preset == "mid_upper"
    assert reloaded.preferred_danmaku_scroll_speed == 0.8
    assert reloaded.preferred_danmaku_font_size == 40
    assert reloaded.preferred_danmaku_line_count == 8


def test_settings_repository_round_trip_persists_player_wide_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        player_wide_mode=True,
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.player_wide_mode is True
    assert saved == config


def test_settings_repository_round_trip_persists_player_window_geometry_and_log_visibility(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)

    config = AppConfig(
        base_url="http://127.0.0.1:4567",
        username="alice",
        token="token-123",
        vod_token="vod-123",
        player_log_visible=False,
        player_window_geometry=b"player-geometry",
        player_main_splitter_state=b"split-main",
    )

    repo.save_config(config)
    saved = repo.load_config()

    assert saved.player_log_visible is False
    assert saved.player_window_geometry == b"player-geometry"
    assert saved.player_main_splitter_state == b"split-main"
    assert saved == config


def test_settings_repository_migrates_missing_preferred_parse_key_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, main_window_geometry, player_window_geometry,
                player_main_splitter_state, browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/', 'main', 'browse', '', '', '', '', '', 0, 100, 0, NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)

    assert repo.load_config().preferred_parse_key == ""


def test_settings_repository_migrates_missing_preferred_danmaku_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, preferred_parse_key, main_window_geometry,
                player_window_geometry, player_main_splitter_state, browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/', 'main', 'browse', '', '', '', '', '', 0, 100, 0, '', NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.preferred_danmaku_enabled is True
    assert saved.preferred_danmaku_line_count == 1


def test_settings_repository_migrates_missing_last_player_paused_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id,
                base_url,
                username,
                token,
                vod_token,
                last_path,
                last_active_window,
                last_playback_mode,
                last_playback_path,
                last_playback_vod_id,
                last_playback_clicked_vod_id,
                main_window_geometry,
                player_window_geometry,
                player_main_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/TV', 'player', 'detail', '/TV', 'vod-1', 'vod-1', NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.last_player_paused is False


def test_settings_repository_migrates_missing_player_volume_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id,
                base_url,
                username,
                token,
                vod_token,
                last_path,
                last_active_window,
                last_playback_mode,
                last_playback_path,
                last_playback_vod_id,
                last_playback_clicked_vod_id,
                last_player_paused,
                main_window_geometry,
                player_window_geometry,
                player_main_splitter_state,
                browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/TV', 'player', 'detail', '/TV', 'vod-1', 'vod-1', 0, NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.player_volume == 100


def test_settings_repository_migrates_missing_player_muted_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id,
                base_url,
                username,
                token,
                vod_token,
                last_path,
                last_active_window,
                last_playback_mode,
                last_playback_path,
                last_playback_vod_id,
                last_playback_clicked_vod_id,
                last_player_paused,
                player_volume,
                main_window_geometry,
                player_window_geometry,
                player_main_splitter_state,
                browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/TV', 'player', 'detail', '/TV', 'vod-1', 'vod-1', 0, 100, NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.player_muted is False


def test_settings_repository_migrates_missing_player_wide_mode_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_mode, last_playback_path,
                last_playback_vod_id, last_playback_clicked_vod_id,
                last_player_paused, player_volume, player_muted,
                preferred_parse_key, preferred_danmaku_enabled,
                preferred_danmaku_line_count, main_window_geometry,
                player_window_geometry, player_main_splitter_state,
                browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/TV', 'player', 'detail', '/TV', 'vod-1', 'vod-1', 0, 100, 0, '', 1, 1, NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.player_wide_mode is False


def test_settings_repository_migrates_missing_last_selected_tab_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                main_window_geometry, player_window_geometry,
                player_main_splitter_state, browse_content_splitter_state
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/', 'main', 'browse', '', '', '', '', '', 0, 100, 0, 0, '', 1, 1, NULL, NULL, NULL, NULL)
            """
        )

    repo = SettingsRepository(db_path)

    assert repo.load_config().last_selected_tab == "douban"


def test_settings_repository_migrates_missing_last_selected_category_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                main_window_geometry, player_window_geometry,
                player_main_splitter_state, browse_content_splitter_state,
                last_selected_tab
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/', 'main', 'browse', '', '', '', '', '', 0, 100, 0, 0, '', 1, 1, NULL, NULL, NULL, NULL, 'telegram')
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.last_selected_category_tab == ""
    assert saved.last_selected_category_id == ""


def test_settings_repository_migrates_missing_global_search_history_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL,
                last_active_window TEXT NOT NULL DEFAULT 'main',
                last_playback_source TEXT NOT NULL DEFAULT 'browse',
                last_playback_source_key TEXT NOT NULL DEFAULT '',
                last_playback_mode TEXT NOT NULL DEFAULT '',
                last_playback_path TEXT NOT NULL DEFAULT '',
                last_playback_vod_id TEXT NOT NULL DEFAULT '',
                last_playback_clicked_vod_id TEXT NOT NULL DEFAULT '',
                last_player_paused INTEGER NOT NULL DEFAULT 0,
                player_volume INTEGER NOT NULL DEFAULT 100,
                player_muted INTEGER NOT NULL DEFAULT 0,
                player_wide_mode INTEGER NOT NULL DEFAULT 0,
                preferred_parse_key TEXT NOT NULL DEFAULT '',
                preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1,
                main_window_geometry BLOB,
                player_window_geometry BLOB,
                player_main_splitter_state BLOB,
                browse_content_splitter_state BLOB,
                last_selected_tab TEXT NOT NULL DEFAULT 'douban',
                last_selected_category_tab TEXT NOT NULL DEFAULT '',
                last_selected_category_id TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (
                id, base_url, username, token, vod_token, last_path,
                last_active_window, last_playback_source, last_playback_source_key,
                last_playback_mode, last_playback_path, last_playback_vod_id,
                last_playback_clicked_vod_id, last_player_paused, player_volume,
                player_muted, player_wide_mode, preferred_parse_key,
                preferred_danmaku_enabled, preferred_danmaku_line_count,
                main_window_geometry, player_window_geometry,
                player_main_splitter_state, browse_content_splitter_state,
                last_selected_tab, last_selected_category_tab, last_selected_category_id
            )
            VALUES (1, 'http://127.0.0.1:4567', 'alice', '', '', '/', 'main', 'browse', '', '', '', '', '', 0, 100, 0, 0, '', 1, 1, NULL, NULL, NULL, NULL, 'douban', '', '')
            """
        )

    repo = SettingsRepository(db_path)
    saved = repo.load_config()

    assert saved.global_search_history == []


def test_settings_repository_clear_token_preserves_other_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SettingsRepository(db_path)
    repo.save_config(
        AppConfig(
            base_url="http://127.0.0.1:4567",
            username="alice",
            token="token-123",
            vod_token="vod-123",
            last_path="/TV",
            last_active_window="player",
            last_playback_mode="detail",
            last_playback_path="/TV",
            last_playback_vod_id="vod-1",
            last_playback_clicked_vod_id="vod-1",
            last_player_paused=True,
            player_volume=35,
            player_muted=True,
            main_window_geometry=None,
            player_window_geometry=None,
            player_main_splitter_state=b"split-main",
            browse_content_splitter_state=b"split-browse",
        )
    )

    repo.clear_token()
    saved = repo.load_config()

    assert saved.base_url == "http://127.0.0.1:4567"
    assert saved.username == "alice"
    assert saved.token == ""
    assert saved.vod_token == ""
    assert saved.last_path == "/TV"
    assert saved.last_active_window == "player"
    assert saved.last_player_paused is True
    assert saved.player_volume == 35
    assert saved.player_muted is True
    assert saved.player_main_splitter_state == b"split-main"
    assert saved.browse_content_splitter_state == b"split-browse"


def test_spider_plugin_repository_round_trip_and_logs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SpiderPluginRepository(db_path)

    local_plugin = repo.add_plugin(
        source_type="local",
        source_value="/plugins/红果短剧.py",
        display_name="红果短剧",
    )
    remote_plugin = repo.add_plugin(
        source_type="remote",
        source_value="https://example.com/spiders/hg.py",
        display_name="红果短剧远程",
    )

    assert local_plugin.config_text == ""
    assert remote_plugin.config_text == ""

    repo.update_plugin(
        local_plugin.id,
        display_name="红果短剧本地",
        enabled=False,
        cached_file_path="",
        last_loaded_at=1713206400,
        last_error="缺少依赖: pyquery",
        config_text="site=https://example.com\ncookie=abc",
    )
    repo.append_log(local_plugin.id, "error", "缺少依赖: pyquery", created_at=1713206401)
    repo.move_plugin(remote_plugin.id, direction=-1)

    plugins = repo.list_plugins()
    logs = repo.list_logs(local_plugin.id)

    assert [(item.display_name, item.sort_order, item.enabled) for item in plugins] == [
        ("红果短剧远程", 0, True),
        ("红果短剧本地", 1, False),
    ]
    assert plugins[1].last_error == "缺少依赖: pyquery"
    assert plugins[1].config_text == "site=https://example.com\ncookie=abc"
    assert logs[0].message == "缺少依赖: pyquery"

    repo.delete_plugin(remote_plugin.id)

    assert [item.display_name for item in repo.list_plugins()] == ["红果短剧本地"]


def test_spider_plugin_repository_reorder_plugins_rewrites_final_order(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin1 = repo.add_plugin("local", "/plugins/1.py", "插件1")
    plugin2 = repo.add_plugin("local", "/plugins/2.py", "插件2")
    plugin3 = repo.add_plugin("local", "/plugins/3.py", "插件3")

    repo.reorder_plugins([plugin3.id, plugin1.id, plugin2.id])

    plugins = repo.list_plugins()

    assert [(plugin.id, plugin.sort_order) for plugin in plugins] == [
        (plugin3.id, 0),
        (plugin1.id, 1),
        (plugin2.id, 2),
    ]


def test_spider_plugin_repository_reorder_plugins_rejects_stale_plugin_ids(tmp_path: Path) -> None:
    repo = SpiderPluginRepository(tmp_path / "app.db")
    plugin1 = repo.add_plugin("local", "/plugins/1.py", "插件1")
    plugin2 = repo.add_plugin("local", "/plugins/2.py", "插件2")
    plugin3 = repo.add_plugin("local", "/plugins/3.py", "插件3")

    with pytest.raises(ValueError, match="插件列表已变化"):
        repo.reorder_plugins([plugin3.id, plugin1.id])

    assert [plugin.id for plugin in repo.list_plugins()] == [plugin1.id, plugin2.id, plugin3.id]


def test_spider_plugin_repository_round_trip_playback_history(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SpiderPluginRepository(db_path)
    plugin = repo.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")

    repo.save_playback_history(
        plugin.id,
        "detail-1",
        {
            "vodName": "红果短剧",
            "vodPic": "poster-1",
            "vodRemarks": "第2集",
            "episode": 1,
            "episodeUrl": "https://media.example/2.m3u8",
            "position": 45000,
            "opening": 5000,
            "ending": 10000,
            "speed": 1.25,
            "playlistIndex": 1,
            "createTime": 1713206400000,
        },
    )

    history = repo.get_playback_history(plugin.id, "detail-1")

    assert history is not None
    assert history.key == "detail-1"
    assert history.vod_name == "红果短剧"
    assert history.episode == 1
    assert history.position == 45000
    assert history.speed == 1.25
    assert history.playlist_index == 1


def test_spider_plugin_repository_updates_existing_playback_history_and_deletes_with_plugin(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    repo = SpiderPluginRepository(db_path)
    plugin = repo.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")

    repo.save_playback_history(
        plugin.id,
        "detail-1",
        {
            "vodName": "旧标题",
            "vodPic": "poster-old",
            "vodRemarks": "第1集",
            "episode": 0,
            "episodeUrl": "https://media.example/1.m3u8",
            "position": 15000,
            "opening": 0,
            "ending": 0,
            "speed": 1.0,
            "playlistIndex": 0,
            "createTime": 1713206400000,
        },
    )
    repo.save_playback_history(
        plugin.id,
        "detail-1",
        {
            "vodName": "新标题",
            "vodPic": "poster-new",
            "vodRemarks": "第3集",
            "episode": 2,
            "episodeUrl": "https://media.example/3.m3u8",
            "position": 90000,
            "opening": 8000,
            "ending": 16000,
            "speed": 1.5,
            "playlistIndex": 1,
            "createTime": 1713206500000,
        },
    )

    updated = repo.get_playback_history(plugin.id, "detail-1")

    assert updated is not None
    assert updated.vod_name == "新标题"
    assert updated.episode == 2
    assert updated.position == 90000
    assert updated.speed == 1.5
    assert updated.playlist_index == 1

    repo.delete_plugin(plugin.id)

    assert repo.get_playback_history(plugin.id, "detail-1") is None


def test_spider_plugin_repository_lists_playback_histories_with_plugin_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SpiderPluginRepository(db_path)
    plugin = repo.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")

    repo.save_playback_history(
        plugin.id,
        "detail-1",
        {
            "vodName": "红果短剧",
            "vodPic": "poster-1",
            "vodRemarks": "第2集",
            "episode": 1,
            "episodeUrl": "https://media.example/2.m3u8",
            "position": 45000,
            "opening": 5000,
            "ending": 10000,
            "speed": 1.25,
            "playlistIndex": 1,
            "createTime": 1713206400000,
        },
    )

    records = repo.list_playback_histories()

    assert len(records) == 1
    assert records[0].key == "detail-1"
    assert records[0].source_kind == "spider_plugin"
    assert records[0].source_plugin_id == plugin.id
    assert records[0].source_plugin_name == "红果短剧"


def test_spider_plugin_repository_deletes_single_playback_history(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    repo = SpiderPluginRepository(db_path)
    plugin = repo.add_plugin("local", "/plugins/红果短剧.py", "红果短剧")

    repo.save_playback_history(
        plugin.id,
        "detail-1",
        {
            "vodName": "红果短剧",
            "vodPic": "poster-1",
            "vodRemarks": "第1集",
            "episode": 0,
            "episodeUrl": "https://media.example/1.m3u8",
            "position": 15000,
            "opening": 0,
            "ending": 0,
            "speed": 1.0,
            "playlistIndex": 0,
            "createTime": 1713206400000,
        },
    )

    repo.delete_playback_history(plugin.id, "detail-1")

    assert repo.get_playback_history(plugin.id, "detail-1") is None


def test_spider_plugin_repository_migrates_tables_into_existing_settings_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                token TEXT NOT NULL,
                vod_token TEXT NOT NULL,
                last_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_config (id, base_url, username, token, vod_token, last_path)
            VALUES (1, 'http://127.0.0.1:4567', '', '', '', '/')
            """
        )

    repo = SpiderPluginRepository(db_path)
    created = repo.add_plugin(
        source_type="local",
        source_value="/plugins/红果短剧.py",
        display_name="红果短剧",
    )

    assert created.id > 0
    assert repo.list_plugins()[0].source_value == "/plugins/红果短剧.py"


def test_spider_plugin_repository_migrates_missing_playlist_index_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugin_playback_history (
                plugin_id INTEGER NOT NULL,
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (plugin_id, vod_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugin_playback_history (
                plugin_id, vod_id, vod_name, vod_pic, vod_remarks,
                episode, episode_url, position, opening, ending, speed, updated_at
            )
            VALUES (1, 'detail-1', '红果短剧', 'poster', '第1集', 0, 'https://media.example/1.m3u8', 45000, 0, 0, 1.0, 1713206400000)
            """
        )

    repo = SpiderPluginRepository(db_path)
    history = repo.get_playback_history(1, "detail-1")

    assert history is not None
    assert history.playlist_index == 0


def test_spider_plugin_repository_migrates_missing_grouped_source_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugin_playback_history (
                plugin_id INTEGER NOT NULL,
                vod_id TEXT NOT NULL,
                vod_name TEXT NOT NULL DEFAULT '',
                vod_pic TEXT NOT NULL DEFAULT '',
                vod_remarks TEXT NOT NULL DEFAULT '',
                episode INTEGER NOT NULL DEFAULT 0,
                episode_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                opening INTEGER NOT NULL DEFAULT 0,
                ending INTEGER NOT NULL DEFAULT 0,
                speed REAL NOT NULL DEFAULT 1.0,
                playlist_index INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (plugin_id, vod_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugin_playback_history (
                plugin_id, vod_id, vod_name, vod_pic, vod_remarks,
                episode, episode_url, position, opening, ending,
                speed, playlist_index, updated_at
            )
            VALUES (7, 'detail-1', '红果短剧', '', '第1集', 0, 'https://a/1.m3u8', 0, 0, 0, 1.0, 0, 99)
            """
        )

    repo = SpiderPluginRepository(db_path)
    history = repo.get_playback_history(7, "detail-1")

    assert history is not None
    assert history.source_group_index == 0
    assert history.source_index == 0


def test_spider_plugin_repository_migrates_missing_config_text_column(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE spider_plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_value TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL,
                cached_file_path TEXT NOT NULL DEFAULT '',
                last_loaded_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spider_plugins (
                source_type, source_value, display_name, enabled, sort_order,
                cached_file_path, last_loaded_at, last_error
            )
            VALUES ('local', '/plugins/红果短剧.py', '红果短剧', 1, 0, '', 0, '')
            """
        )

    repo = SpiderPluginRepository(db_path)
    plugin = repo.get_plugin(1)

    assert plugin.display_name == "红果短剧"
    assert plugin.config_text == ""
    repo.update_plugin(
        plugin.id,
        display_name=plugin.display_name,
        enabled=plugin.enabled,
        cached_file_path=plugin.cached_file_path,
        last_loaded_at=plugin.last_loaded_at,
        last_error=plugin.last_error,
        config_text="token=updated",
    )

    assert repo.get_plugin(1).config_text == "token=updated"
