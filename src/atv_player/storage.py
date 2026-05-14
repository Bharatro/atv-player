import json
from pathlib import Path

from atv_player.models import AppConfig
from atv_player.sqlite_utils import managed_connection

_VALID_DANMAKU_RENDER_MODES = {"static", "scroll_only", "mixed"}
_VALID_DANMAKU_COLOR_MODES = {"uniform", "source"}
_VALID_DANMAKU_POSITION_PRESETS = {"top", "upper", "mid_upper", "bottom"}


def _normalize_danmaku_line_count(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(normalized, 10))


def _normalize_danmaku_render_mode(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_RENDER_MODES else "static"


def _normalize_danmaku_color_mode(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_COLOR_MODES else "source"


def _normalize_danmaku_uniform_color(value: object) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 7 and text.startswith("#"):
        return text
    return "#FFFFFF"


def _normalize_danmaku_position_preset(value: object) -> str:
    text = str(value or "").strip()
    return text if text in _VALID_DANMAKU_POSITION_PRESETS else "top"


def _normalize_danmaku_scroll_speed(value: object) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.5, min(round(normalized, 2), 2.0))


def _normalize_danmaku_font_size(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 32
    return max(16, min(normalized, 72))


def _normalize_global_search_history(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    history: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        history.append(text)
        seen.add(text)
    return history[:10]


class SettingsRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return managed_connection(self._db_path)

    @property
    def database_path(self) -> Path:
        return self._db_path

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config (
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
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(app_config)").fetchall()
            }
            if "vod_token" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN vod_token TEXT NOT NULL DEFAULT ''"
                )
            if "last_active_window" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_active_window TEXT NOT NULL DEFAULT 'main'"
                )
            if "last_playback_source" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_source TEXT NOT NULL DEFAULT 'browse'"
                )
            if "last_playback_source_key" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_source_key TEXT NOT NULL DEFAULT ''"
                )
            if "last_playback_mode" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_mode TEXT NOT NULL DEFAULT ''"
                )
            if "last_playback_path" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_path TEXT NOT NULL DEFAULT ''"
                )
            if "last_playback_vod_id" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_vod_id TEXT NOT NULL DEFAULT ''"
                )
            if "last_playback_clicked_vod_id" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_playback_clicked_vod_id TEXT NOT NULL DEFAULT ''"
                )
            if "last_player_paused" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_player_paused INTEGER NOT NULL DEFAULT 0"
                )
            if "player_volume" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN player_volume INTEGER NOT NULL DEFAULT 100"
                )
            if "player_muted" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN player_muted INTEGER NOT NULL DEFAULT 0"
                )
            if "player_wide_mode" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN player_wide_mode INTEGER NOT NULL DEFAULT 0"
                )
            if "player_log_visible" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN player_log_visible INTEGER NOT NULL DEFAULT 1"
                )
            if "preferred_parse_key" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_parse_key TEXT NOT NULL DEFAULT ''"
                )
            if "preferred_danmaku_enabled" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_enabled INTEGER NOT NULL DEFAULT 1"
                )
            if "preferred_danmaku_line_count" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_line_count INTEGER NOT NULL DEFAULT 1"
                )
            if "preferred_danmaku_render_mode" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_render_mode TEXT NOT NULL DEFAULT 'static'"
                )
            if "preferred_danmaku_color_mode" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_color_mode TEXT NOT NULL DEFAULT 'source'"
                )
            if "preferred_danmaku_uniform_color" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_uniform_color TEXT NOT NULL DEFAULT '#FFFFFF'"
                )
            if "preferred_danmaku_position_preset" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_position_preset TEXT NOT NULL DEFAULT 'top'"
                )
            if "preferred_danmaku_scroll_speed" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_scroll_speed REAL NOT NULL DEFAULT 1.0"
                )
            if "preferred_danmaku_font_size" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN preferred_danmaku_font_size INTEGER NOT NULL DEFAULT 32"
                )
            if "player_main_splitter_state" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN player_main_splitter_state BLOB"
                )
            if "browse_content_splitter_state" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN browse_content_splitter_state BLOB"
                )
            if "last_selected_tab" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_selected_tab TEXT NOT NULL DEFAULT 'douban'"
                )
            if "last_selected_category_tab" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_selected_category_tab TEXT NOT NULL DEFAULT ''"
                )
            if "last_selected_category_id" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN last_selected_category_id TEXT NOT NULL DEFAULT ''"
                )
            if "global_search_history" not in columns:
                conn.execute(
                    "ALTER TABLE app_config ADD COLUMN global_search_history TEXT NOT NULL DEFAULT '[]'"
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
                    last_playback_source,
                    last_playback_source_key,
                    last_playback_mode,
                    last_playback_path,
                    last_playback_vod_id,
                    last_playback_clicked_vod_id,
                    last_player_paused,
                    player_volume,
                    player_muted,
                    player_wide_mode,
                    player_log_visible,
                    preferred_parse_key,
                    preferred_danmaku_enabled,
                    preferred_danmaku_line_count,
                    preferred_danmaku_render_mode,
                    preferred_danmaku_color_mode,
                    preferred_danmaku_uniform_color,
                    preferred_danmaku_position_preset,
                    preferred_danmaku_scroll_speed,
                    preferred_danmaku_font_size,
                    main_window_geometry,
                    player_window_geometry,
                    player_main_splitter_state,
                    browse_content_splitter_state,
                    last_selected_tab,
                    last_selected_category_tab,
                    last_selected_category_id,
                    global_search_history
                )
                VALUES (
                    1, 'http://127.0.0.1:4567', '', '', '', '/', 'main', 'browse', '', '', '', '', '',
                    0, 100, 0, 0, 1, '', 1, 1, 'static', 'source', '#FFFFFF', 'top', 1.0, 32,
                    NULL, NULL, NULL, NULL, 'douban', '', '', '[]'
                )
                ON CONFLICT(id) DO NOTHING
                """
            )

    def load_config(self) -> AppConfig:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    base_url,
                    username,
                    token,
                    vod_token,
                    last_path,
                    last_active_window,
                    last_playback_source,
                    last_playback_source_key,
                    last_playback_mode,
                    last_playback_path,
                    last_playback_vod_id,
                    last_playback_clicked_vod_id,
                    last_player_paused,
                    player_volume,
                    player_muted,
                    player_wide_mode,
                    player_log_visible,
                    preferred_parse_key,
                    preferred_danmaku_enabled,
                    preferred_danmaku_line_count,
                    preferred_danmaku_render_mode,
                    preferred_danmaku_color_mode,
                    preferred_danmaku_uniform_color,
                    preferred_danmaku_position_preset,
                    preferred_danmaku_scroll_speed,
                    preferred_danmaku_font_size,
                    main_window_geometry,
                    player_window_geometry,
                    player_main_splitter_state,
                    browse_content_splitter_state,
                    last_selected_tab,
                    last_selected_category_tab,
                    last_selected_category_id,
                    global_search_history
                FROM app_config
                WHERE id = 1
                """
            ).fetchone()
        assert row is not None
        (
            base_url,
            username,
            token,
            vod_token,
            last_path,
            last_active_window,
            last_playback_source,
            last_playback_source_key,
            last_playback_mode,
            last_playback_path,
            last_playback_vod_id,
            last_playback_clicked_vod_id,
            last_player_paused,
            player_volume,
            player_muted,
            player_wide_mode,
            player_log_visible,
            preferred_parse_key,
            preferred_danmaku_enabled,
            preferred_danmaku_line_count,
            preferred_danmaku_render_mode,
            preferred_danmaku_color_mode,
            preferred_danmaku_uniform_color,
            preferred_danmaku_position_preset,
            preferred_danmaku_scroll_speed,
            preferred_danmaku_font_size,
            main_window_geometry,
            player_window_geometry,
            player_main_splitter_state,
            browse_content_splitter_state,
            last_selected_tab,
            last_selected_category_tab,
            last_selected_category_id,
            global_search_history,
        ) = row
        return AppConfig(
            base_url=base_url,
            username=username,
            token=token,
            vod_token=vod_token,
            last_path=last_path,
            last_active_window=last_active_window,
            last_playback_source=last_playback_source,
            last_playback_source_key=last_playback_source_key,
            last_playback_mode=last_playback_mode,
            last_playback_path=last_playback_path,
            last_playback_vod_id=last_playback_vod_id,
            last_playback_clicked_vod_id=last_playback_clicked_vod_id,
            last_player_paused=bool(last_player_paused),
            player_volume=player_volume,
            player_muted=bool(player_muted),
            player_wide_mode=bool(player_wide_mode),
            player_log_visible=bool(player_log_visible),
            preferred_parse_key=preferred_parse_key,
            preferred_danmaku_enabled=bool(preferred_danmaku_enabled),
            preferred_danmaku_line_count=_normalize_danmaku_line_count(preferred_danmaku_line_count),
            preferred_danmaku_render_mode=_normalize_danmaku_render_mode(preferred_danmaku_render_mode),
            preferred_danmaku_color_mode=_normalize_danmaku_color_mode(preferred_danmaku_color_mode),
            preferred_danmaku_uniform_color=_normalize_danmaku_uniform_color(preferred_danmaku_uniform_color),
            preferred_danmaku_position_preset=_normalize_danmaku_position_preset(preferred_danmaku_position_preset),
            preferred_danmaku_scroll_speed=_normalize_danmaku_scroll_speed(preferred_danmaku_scroll_speed),
            preferred_danmaku_font_size=_normalize_danmaku_font_size(preferred_danmaku_font_size),
            main_window_geometry=main_window_geometry,
            player_window_geometry=player_window_geometry,
            player_main_splitter_state=player_main_splitter_state,
            browse_content_splitter_state=browse_content_splitter_state,
            last_selected_tab=last_selected_tab,
            last_selected_category_tab=last_selected_category_tab,
            last_selected_category_id=last_selected_category_id,
            global_search_history=_normalize_global_search_history(global_search_history),
        )

    def save_config(self, config: AppConfig) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE app_config
                SET
                    base_url = ?,
                    username = ?,
                    token = ?,
                    vod_token = ?,
                    last_path = ?,
                    last_active_window = ?,
                    last_playback_source = ?,
                    last_playback_source_key = ?,
                    last_playback_mode = ?,
                    last_playback_path = ?,
                    last_playback_vod_id = ?,
                    last_playback_clicked_vod_id = ?,
                    last_player_paused = ?,
                    player_volume = ?,
                    player_muted = ?,
                    player_wide_mode = ?,
                    player_log_visible = ?,
                    preferred_parse_key = ?,
                    preferred_danmaku_enabled = ?,
                    preferred_danmaku_line_count = ?,
                    preferred_danmaku_render_mode = ?,
                    preferred_danmaku_color_mode = ?,
                    preferred_danmaku_uniform_color = ?,
                    preferred_danmaku_position_preset = ?,
                    preferred_danmaku_scroll_speed = ?,
                    preferred_danmaku_font_size = ?,
                    main_window_geometry = ?,
                    player_window_geometry = ?,
                    player_main_splitter_state = ?,
                    browse_content_splitter_state = ?,
                    last_selected_tab = ?,
                    last_selected_category_tab = ?,
                    last_selected_category_id = ?,
                    global_search_history = ?
                WHERE id = 1
                """,
                (
                    config.base_url,
                    config.username,
                    config.token,
                    config.vod_token,
                    config.last_path,
                    config.last_active_window,
                    config.last_playback_source,
                    config.last_playback_source_key,
                    config.last_playback_mode,
                    config.last_playback_path,
                    config.last_playback_vod_id,
                    config.last_playback_clicked_vod_id,
                    int(config.last_player_paused),
                    config.player_volume,
                    int(config.player_muted),
                    int(config.player_wide_mode),
                    int(config.player_log_visible),
                    config.preferred_parse_key,
                    int(config.preferred_danmaku_enabled),
                    _normalize_danmaku_line_count(config.preferred_danmaku_line_count),
                    _normalize_danmaku_render_mode(config.preferred_danmaku_render_mode),
                    _normalize_danmaku_color_mode(config.preferred_danmaku_color_mode),
                    _normalize_danmaku_uniform_color(config.preferred_danmaku_uniform_color),
                    _normalize_danmaku_position_preset(config.preferred_danmaku_position_preset),
                    _normalize_danmaku_scroll_speed(config.preferred_danmaku_scroll_speed),
                    _normalize_danmaku_font_size(config.preferred_danmaku_font_size),
                    config.main_window_geometry,
                    config.player_window_geometry,
                    config.player_main_splitter_state,
                    config.browse_content_splitter_state,
                    config.last_selected_tab,
                    config.last_selected_category_tab,
                    config.last_selected_category_id,
                    json.dumps(_normalize_global_search_history(config.global_search_history), ensure_ascii=False),
                ),
            )

    def clear_token(self) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE app_config SET token = '', vod_token = '' WHERE id = 1")
