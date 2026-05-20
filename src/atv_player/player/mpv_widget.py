from __future__ import annotations

import glob
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from atv_player.models import AppConfig
from atv_player.player.ytdlp_runtime import (
    resolve_mpv_ytdl_raw_options,
    resolve_mpv_ytdlp_path,
)

_MPV_ERROR_MESSAGES = {
    -1: "事件队列已满",
    -2: "内存分配失败",
    -3: "播放器未初始化",
    -4: "参数无效",
    -5: "选项不存在",
    -6: "选项格式错误",
    -7: "选项值无效",
    -8: "属性不存在",
    -9: "属性格式错误",
    -10: "属性当前不可用",
    -11: "属性访问失败",
    -12: "执行播放器命令失败",
    -13: "媒体加载失败",
    -14: "音频输出初始化失败",
    -15: "视频输出初始化失败",
    -16: "没有可播放的音视频流",
    -17: "无法识别媒体格式",
    -18: "当前系统不支持该操作",
    -19: "功能尚未实现",
    -20: "未指定错误",
}

_DEFAULT_STREAM_PROFILE: dict[str, object] = {
    "cache-pause": "yes",
    "cache-pause-initial": "yes",
    "cache-pause-wait": 3,
    "demuxer-readahead-secs": 20,
}

_ISO_PROXY_STREAM_PROFILE: dict[str, object] = {
    "cache-pause": "no",
    "cache-pause-initial": "no",
    "cache-pause-wait": 0,
    "demuxer-readahead-secs": 3,
}

_LOW_LATENCY_STREAM_PROFILE: dict[str, object] = {
    "cache-pause": "no",
    "cache-pause-initial": "no",
    "cache-pause-wait": 0,
    "demuxer-readahead-secs": 3,
}

_YTDL_STREAM_PROFILE: dict[str, object] = {
    "cache-pause": "yes",
    "cache-pause-initial": "yes",
    "cache-pause-wait": 5,
    # "cache-secs": 120,
    "demuxer-readahead-secs": 120,
}

logger = logging.getLogger(__name__)
_NVIDIA_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)*)")
_LINUX_NVIDIA_DRIVER_MISMATCH: tuple[str, str] | bool | None = None


def _version_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _extract_nvidia_version(text: str) -> str:
    match = _NVIDIA_VERSION_RE.search(text)
    return match.group(1) if match is not None else ""


def _read_linux_nvidia_kernel_version() -> str:
    try:
        with open("/proc/driver/nvidia/version", encoding="utf-8") as handle:
            return _extract_nvidia_version(handle.read())
    except Exception:
        return ""


def _read_linux_nvidia_userspace_version() -> str:
    versions: set[str] = set()
    for pattern in (
        "/lib*/x86_64-linux-gnu/libnvidia-glcore.so.*",
        "/usr/lib*/x86_64-linux-gnu/libnvidia-glcore.so.*",
        "/lib*/x86_64-linux-gnu/libEGL_nvidia.so.*",
        "/usr/lib*/x86_64-linux-gnu/libEGL_nvidia.so.*",
    ):
        for candidate in glob.glob(pattern):
            version = _extract_nvidia_version(os.path.basename(candidate))
            if version:
                versions.add(version)
    if not versions:
        return ""
    return max(versions, key=_version_sort_key)


def detect_linux_nvidia_driver_mismatch() -> tuple[str, str] | None:
    global _LINUX_NVIDIA_DRIVER_MISMATCH

    if _LINUX_NVIDIA_DRIVER_MISMATCH is False:
        return None
    if isinstance(_LINUX_NVIDIA_DRIVER_MISMATCH, tuple):
        return _LINUX_NVIDIA_DRIVER_MISMATCH
    if not sys.platform.startswith("linux"):
        _LINUX_NVIDIA_DRIVER_MISMATCH = False
        return None
    kernel_version = _read_linux_nvidia_kernel_version()
    userspace_version = _read_linux_nvidia_userspace_version()
    if kernel_version and userspace_version and kernel_version != userspace_version:
        _LINUX_NVIDIA_DRIVER_MISMATCH = (userspace_version, kernel_version)
        return _LINUX_NVIDIA_DRIVER_MISMATCH
    _LINUX_NVIDIA_DRIVER_MISMATCH = False
    return None


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    id: int
    title: str
    lang: str
    is_default: bool
    is_forced: bool
    label: str


@dataclass(frozen=True, slots=True)
class AudioTrack:
    id: int
    title: str
    lang: str
    is_default: bool
    is_forced: bool
    label: str


class MpvWidget(QWidget):
    double_clicked = Signal()
    playback_finished = Signal()
    playback_failed = Signal(str)
    video_picture_state_changed = Signal(str)
    subtitle_tracks_changed = Signal()
    audio_tracks_changed = Signal()
    context_menu_requested = Signal()
    context_menu_dismiss_requested = Signal()

    def __init__(self, parent=None, config: AppConfig | None = None) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._player: Any | None = None
        self._video_picture_state = "idle"
        self._audio_cover_active = False
        self._audio_cover_mode = False
        self._playback_finished_emitted = False
        self._placeholder = QLabel("")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._placeholder)

    def _set_video_picture_state(self, state: str) -> None:
        if self._video_picture_state == state:
            return
        self._video_picture_state = state
        self.video_picture_state_changed.emit(state)

    def _emit_playback_finished_once(self) -> None:
        if self._playback_finished_emitted:
            return
        self._playback_finished_emitted = True
        self.playback_finished.emit()

    def _base_player_options(self) -> dict[str, object]:
        options = dict(
            wid=str(int(self.winId())),
            hwdec=str(getattr(self._config, "mpv_hwdec_mode", "auto-safe") or "auto-safe"),
            force_window="yes",
            audio_spdif="no",
            ad="ffmpeg",
            input_default_bindings=False,
            input_vo_keyboard=False,
            cache=True,
            cache_pause_initial=True,
            cache_pause_wait=3,
            demuxer_max_bytes=f"{int(getattr(self._config, 'mpv_cache_size_mb', 512) or 512)}M",
            demuxer_max_back_bytes="128M",
            demuxer_readahead_secs=int(getattr(self._config, "mpv_default_readahead_secs", 20) or 20),
            stream_buffer_size="4M",
            network_timeout=int(getattr(self._config, "mpv_network_timeout_seconds", 15) or 15),
        )
        mismatch = detect_linux_nvidia_driver_mismatch()
        if mismatch is not None:
            userspace_version, kernel_version = mismatch
            options["hwdec"] = "no"
            options["vo"] = "wlshm" if os.getenv("WAYLAND_DISPLAY") and not os.getenv("DISPLAY") else "x11"
            logger.warning(
                "Detected NVIDIA driver mismatch userspace=%s kernel=%s forcing software video output",
                userspace_version,
                kernel_version,
            )
        return options

    def _create_player(self):
        import mpv

        common = self._base_player_options()
        ytdlp_path = resolve_mpv_ytdlp_path()
        if ytdlp_path:
            common["script_opts"] = f"ytdl_hook-ytdl_path={ytdlp_path}"
        ytdl_raw_options = resolve_mpv_ytdl_raw_options(
            cookie_browser=str(getattr(self._config, "youtube_cookie_browser", "") or "")
        )
        if ytdl_raw_options:
            common["ytdl_raw_options"] = ytdl_raw_options
        if os.getenv("ATV_MPV_DEBUG"):
            common["log_handler"] = print
            common["loglevel"] = "warn"

        if sys.platform.startswith("win"):
            return mpv.MPV(
                **common,
                audio_device="auto",
                audio_exclusive="no",
            )

        elif sys.platform == "darwin":
            return mpv.MPV(
                **common,
                # macOS 👉 不指定最稳
                # audio_device="auto" 也可以
                audio_exclusive="no",
            )

        else:
            return mpv.MPV(
                **common,
                ao="pulse,pipewire,alsa,",
            )

    def _ensure_player(self) -> None:
        if self._player is not None and not getattr(self._player, "core_shutdown", False):
            return
        self._player = self._create_player()
        self._register_player_events()

    def shutdown(self) -> None:
        if self._player is None:
            return
        player, self._player = self._player, None
        if getattr(player, "core_shutdown", False):
            return
        try:
            terminate = getattr(player, "terminate", None)
            if terminate is not None:
                terminate()
        except Exception:
            if getattr(player, "core_shutdown", False):
                return
            raise

    def _register_player_events(self) -> None:
        if self._player is None:
            return
        event_callback = getattr(self._player, "event_callback", None)
        if event_callback is None:
            return

        @event_callback("end-file")
        def handle_end_file(event) -> None:
            event_data = getattr(event, "data", None)
            if event_data is None:
                return
            reason = getattr(event_data, "reason", None)
            eof_reason = getattr(type(event_data), "EOF", 0)
            if reason == eof_reason:
                self._emit_playback_finished_once()
                return
            error_reason = getattr(type(event_data), "ERROR", 4)
            if reason == error_reason:
                self.playback_failed.emit(self._format_end_file_failure_message(event_data))

        self._end_file_handler = handle_end_file
        observe_property = getattr(self._player, "observe_property", None)
        if observe_property is None:
            return

        def handle_track_list(_property_name, _tracks) -> None:
            self.subtitle_tracks_changed.emit()
            self.audio_tracks_changed.emit()
            normalized = _tracks or []
            has_video_track = any(isinstance(track, dict) and track.get("type") == "video" for track in normalized)
            if has_video_track:
                self._audio_cover_active = False
                return
            if self._audio_cover_active:
                self._set_video_picture_state("audio-cover")
                return
            self._set_video_picture_state("unavailable")

        observe_property("track-list", handle_track_list)
        self._track_list_handler = handle_track_list

        def handle_video_out_params(_property_name, params) -> None:
            if params:
                if self._audio_cover_active:
                    self._set_video_picture_state("audio-cover")
                    return
                self._set_video_picture_state("visible")

        observe_property("video-out-params", handle_video_out_params)
        self._video_out_params_handler = handle_video_out_params

        def handle_eof_reached(_property_name, reached) -> None:
            if reached and self._audio_cover_mode:
                self._emit_playback_finished_once()

        observe_property("eof-reached", handle_eof_reached)
        self._eof_reached_handler = handle_eof_reached

        register_key_binding = getattr(self._player, "register_key_binding", None)
        if register_key_binding is None:
            return

        def handle_right_click(*_args) -> None:
            self.context_menu_requested.emit()

        def handle_left_click(*_args) -> None:
            self.context_menu_dismiss_requested.emit()

        register_key_binding("MBTN_RIGHT", handle_right_click, mode="force")
        register_key_binding("MBTN_LEFT", handle_left_click, mode="force")
        self._right_click_handler = handle_right_click
        self._left_click_handler = handle_left_click

    def _build_http_header_fields(self, headers: dict[str, str] | None) -> list[str]:
        if not headers:
            return []
        return [f"{key}: {value}" for key, value in headers.items()]

    def _apply_http_header_fields(self, player: Any, header_fields: list[str]) -> None:
        if not hasattr(type(player), "__setitem__"):
            return
        player["http-header-fields"] = header_fields

    def _is_local_iso_proxy_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.path.startswith("/iso/")

    def _is_local_dash_proxy_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.path.startswith("/dash/")

    def _apply_stream_profile(
        self,
        player: Any,
        url: str,
        *,
        audio_files: str = "",
        ytdl_format: str = "",
    ) -> str:
        default_profile = dict(_DEFAULT_STREAM_PROFILE)
        default_profile["demuxer-readahead-secs"] = int(
            getattr(self._config, "mpv_default_readahead_secs", 20) or 20
        )
        if self._is_local_iso_proxy_url(url):
            profile = _ISO_PROXY_STREAM_PROFILE
            profile_name = "iso-proxy"
        elif self._is_local_dash_proxy_url(url):
            # DASH proxy needs some buffering for remote media, but a full initial cache pause
            # makes first-frame startup feel much slower than direct playback.
            profile = _YTDL_STREAM_PROFILE
            profile_name = "dash-proxy"
        elif ytdl_format:
            profile = _YTDL_STREAM_PROFILE
            profile_name = "hybrid-ytdl"
        elif audio_files:
            # Separate remote video/audio streams pay the startup cost twice if we keep
            # mpv's initial cache pause enabled.
            profile = _LOW_LATENCY_STREAM_PROFILE
            profile_name = "low-latency-external-audio"
        else:
            profile = default_profile
            profile_name = "default"
        for key, value in profile.items():
            self._set_player_property(key, value)
        return profile_name

    def _apply_extra_mpv_options(self, player: Any) -> None:
        raw = str(getattr(self._config, "mpv_extra_options", "") or "").strip()
        if not raw:
            return
        previous_player = self._player
        self._player = player
        try:
            for line in raw.splitlines():
                normalized = line.strip()
                if not normalized:
                    continue
                key, value = normalized.split("=", 1)
                self._set_player_property(key.strip(), value.strip())
        finally:
            self._player = previous_player

    def _loadfile_options(self, url: str) -> dict[str, str]:
        lowered_path = urlparse(url).path.lower()
        lowered = url.lower()
        if self._is_local_iso_proxy_url(url):
            return {
                "demuxer_lavf_format": "mpegts",
                "demuxer_lavf_linearize_timestamps": "yes",
                "rebase_start_time": "yes",
            }
        if lowered_path.endswith(".mkv"):
            return {"demuxer_mkv_subtitle_preroll_secs": "0"}
        if ".m3u8" not in lowered and ".mpd" not in lowered:
            return {}
        # Some HLS/DASH sources use fragment URLs mpv would otherwise reject by extension.
        return {"demuxer_lavf_o_add": "allowed_extensions=ALL"}

    def _encode_loadfile_options(self, options: dict[str, str]) -> str:
        # mpv's option list uses commas between entries, so option values must stay comma-free.
        # Values may still contain "=" because some mpv suboptions are expressed as nested key=value text.
        for key, value in options.items():
            if "," in key or "," in value:
                raise ValueError(f"mpv loadfile option {key!r} cannot contain ','")
        return ",".join(f"{key}={value}" for key, value in options.items())

    def _loadfile_index_supported(self, player: Any) -> bool:
        mpv_version = getattr(player, "mpv_version_tuple", None)
        return isinstance(mpv_version, tuple) and mpv_version >= (0, 38, 0)

    def _should_use_async_loadfile(self, player: Any, mode: str) -> bool:
        if sys.platform.startswith("win"):
            return False
        command_async = getattr(player, "command_async", None)
        if not callable(command_async):
            return False
        if mode != "replace":
            return True
        mpv_version = getattr(player, "mpv_version_tuple", None)
        if isinstance(mpv_version, tuple) and mpv_version < (0, 38, 0):
            return not bool(self._player_property("path", ""))
        return True

    def _load_player_media(
        self,
        player: Any,
        url: str,
        *,
        mode: str = "replace",
        index: int | None = None,
        options: dict[str, str] | None = None,
    ) -> None:
        normalized_options = dict(options or {})
        command_async = getattr(player, "command_async", None)
        if self._should_use_async_loadfile(player, mode):
            command_args: list[object] = [url, mode]
            encoded_options = self._encode_loadfile_options(normalized_options)
            if self._loadfile_index_supported(player):
                command_args.append(-1 if index is None else index)
                if encoded_options:
                    command_args.append(encoded_options)
            elif encoded_options:
                command_args.append(encoded_options)
            command_async("loadfile", *command_args)
            return
        if index is not None:
            player.loadfile(url, mode, index, **normalized_options)
            return
        player.loadfile(url, mode, **normalized_options)

    def _player_property(self, name: str, default: object | None = None) -> object | None:
        if self._player is None:
            return default
        try:
            return self._player[name]
        except Exception:
            if hasattr(self._player, name.replace("-", "_")):
                return getattr(self._player, name.replace("-", "_"))
            return default

    def _set_player_property(self, name: str, value: object) -> None:
        if self._player is None:
            return
        try:
            if hasattr(type(self._player), "__setitem__"):
                self._player[name] = value
            else:
                setattr(self._player, name.replace("-", "_"), value)
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def _is_missing_mpv_property_error(self, exc: Exception) -> bool:
        return "property does not exist" in str(exc)

    def _format_mpv_error(self, error: object | None) -> str:
        if isinstance(error, bool):
            return str(error)
        if isinstance(error, int):
            message = _MPV_ERROR_MESSAGES.get(error)
            return f"{message} ({error})" if message else str(error)
        normalized = str(error or "").strip()
        if not normalized:
            return ""
        try:
            error_code = int(normalized)
        except ValueError:
            return normalized
        message = _MPV_ERROR_MESSAGES.get(error_code)
        return f"{message} ({error_code})" if message else normalized

    def _format_end_file_failure_message(self, event_data: object | None) -> str:
        error = self._format_mpv_error(getattr(event_data, "error", ""))
        if error:
            return f"播放失败: {error}"
        return "播放失败: 未知错误"

    def _int_property_value(self, value: object | None, default: int) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def _scale_property_percent(self, value: object | None, default: int) -> int:
        if isinstance(value, bool):
            return int(round(float(value) * 100))
        if isinstance(value, (int, float)):
            return int(round(float(value) * 100))
        if isinstance(value, str):
            try:
                return int(round(float(value) * 100))
            except ValueError:
                return default
        return default

    def _ass_override_value(self, value: object | None, default: str) -> str:
        allowed = {"yes", "no", "force", "strip", "scale"}
        if isinstance(value, bool):
            return "yes" if value else "no"
        normalized = str(value or "").strip().lower()
        if normalized in allowed:
            return normalized
        return default

    def _yes_no_value(self, value: object | None, default: str) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        normalized = str(value or "").strip().lower()
        if normalized in {"yes", "no"}:
            return normalized
        return default

    def load(
            self,
            url: str,
            pause: bool = False,
            start_seconds: int = 0,
            headers: dict[str, str] | None = None,
            poster_image_path: str | None = None,
            audio_files: str = "",
            ytdl_format: str = "",
    ) -> None:
        self._set_video_picture_state("loading")
        self._audio_cover_active = False
        self._audio_cover_mode = bool(poster_image_path)
        self._playback_finished_emitted = False
        self._ensure_player()
        player = self._player
        if player is None:
            return
        header_fields = self._build_http_header_fields(headers)
        loadfile_options = self._loadfile_options(url)
        if ytdl_format:
            loadfile_options["ytdl"] = "yes"
            loadfile_options["ytdl_format"] = ytdl_format
        can_loadfile = hasattr(player, "loadfile") or callable(getattr(player, "command_async", None))
        try:
            self._apply_http_header_fields(player, header_fields)
            profile_name = self._apply_stream_profile(
                player,
                url,
                audio_files=audio_files,
                ytdl_format=ytdl_format,
            )
            self._apply_extra_mpv_options(player)
            logger.info(
                "MPV load url=%s audio=%s ytdl_format=%s start=%s pause=%s profile=%s headers=%s",
                self._summarize_media_url(url),
                self._summarize_media_url(audio_files),
                ytdl_format,
                start_seconds,
                pause,
                profile_name,
                bool(header_fields),
            )
            if poster_image_path and can_loadfile:
                self._load_media(
                    player,
                    url,
                    start_seconds,
                    {
                        **loadfile_options,
                        "cover_art_files": poster_image_path,
                        "audio_display": "external-first",
                    },
                )
            elif poster_image_path:
                self._load_media(player, url, start_seconds, loadfile_options)
                self.attach_audio_cover(poster_image_path)
            elif start_seconds > 0 and can_loadfile:
                self._load_player_media(
                    player,
                    url,
                    options={**loadfile_options, "start": str(start_seconds)},
                )
            elif audio_files and can_loadfile:
                self._load_player_media(player, url, options=loadfile_options)
            elif (header_fields or loadfile_options) and can_loadfile:
                self._load_player_media(player, url, options=loadfile_options)
            else:
                player.play(url)
            self._attach_external_audio(player, audio_files)
        except Exception:
            if getattr(player, "core_shutdown", False):
                player = self._create_player()
                self._player = player
                self._register_player_events()
                self._apply_http_header_fields(player, header_fields)
                profile_name = self._apply_stream_profile(
                    player,
                    url,
                    audio_files=audio_files,
                    ytdl_format=ytdl_format,
                )
                self._apply_extra_mpv_options(player)
                logger.info(
                    "MPV reload after player restart url=%s audio=%s ytdl_format=%s start=%s pause=%s profile=%s headers=%s",
                    self._summarize_media_url(url),
                    self._summarize_media_url(audio_files),
                    ytdl_format,
                    start_seconds,
                    pause,
                    profile_name,
                    bool(header_fields),
                )
                can_loadfile = hasattr(player, "loadfile") or callable(getattr(player, "command_async", None))
                if poster_image_path and can_loadfile:
                    self._load_media(
                        player,
                        url,
                        start_seconds,
                        {
                            **loadfile_options,
                            "cover_art_files": poster_image_path,
                            "audio_display": "external-first",
                        },
                    )
                elif poster_image_path:
                    self._load_media(player, url, start_seconds, loadfile_options)
                    self.attach_audio_cover(poster_image_path)
                elif start_seconds > 0 and can_loadfile:
                    self._load_player_media(
                        player,
                        url,
                        options={**loadfile_options, "start": str(start_seconds)},
                    )
                elif audio_files and can_loadfile:
                    self._load_player_media(player, url, options=loadfile_options)
                elif (header_fields or loadfile_options) and can_loadfile:
                    self._load_player_media(player, url, options=loadfile_options)
                else:
                    player.play(url)
                self._attach_external_audio(player, audio_files)
            else:
                raise
        player.pause = pause

    def _summarize_media_url(self, url: str) -> str:
        parsed = urlparse(url or "")
        if not parsed.scheme or not parsed.netloc:
            return url
        path = parsed.path or "/"
        if len(path) > 96:
            path = f"...{path[-96:]}"
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    def _load_media(self, player: Any, url: str, start_seconds: int, loadfile_options: dict[str, str]) -> None:
        can_loadfile = hasattr(player, "loadfile") or callable(getattr(player, "command_async", None))
        if start_seconds > 0 and can_loadfile:
            self._load_player_media(
                player,
                url,
                options={**loadfile_options, "start": str(start_seconds)},
            )
            return
        if loadfile_options and can_loadfile:
            self._load_player_media(player, url, options=loadfile_options)
            return
        player.play(url)

    def _attach_external_audio(self, player: Any, audio_files: str) -> None:
        if not audio_files:
            return
        audio_add = getattr(player, "audio_add", None)
        if callable(audio_add):
            audio_add(audio_files)
            return
        command = getattr(player, "command", None)
        if callable(command):
            command("audio-add", audio_files, "select")
            return
        if hasattr(player, "loadfile"):
            player.loadfile(audio_files, "append")

    def attach_audio_cover(self, poster_image_path: str) -> None:
        player = self._player
        if player is None or not poster_image_path:
            return
        try:
            self._set_player_property("audio-display", "external-first")
            self._set_player_property("image-display-duration", "inf")
            self._set_player_property("keep-open", "yes")
            player.command("video-add", poster_image_path, "select", "", "", True)
        except Exception:
            self._audio_cover_active = False
            self._audio_cover_mode = False
            if getattr(player, "core_shutdown", False):
                return
            self._set_video_picture_state("unavailable")
            return
        self._audio_cover_active = True
        self._audio_cover_mode = True
        self._set_video_picture_state("audio-cover")

    def seek(self, seconds: int) -> None:
        if self._player is None:
            return
        try:
            self._player.command("seek", seconds, "absolute")
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def seek_relative(self, seconds: int) -> None:
        if self._player is None:
            return
        try:
            self._player.command("seek", seconds, "relative")
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def can_seek(self) -> bool:
        if self._player is None:
            return False
        try:
            return bool(self._player.seekable)
        except Exception:
            return False

    def set_speed(self, speed: float) -> None:
        if self._player is None:
            return
        try:
            self._player.speed = speed
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def set_volume(self, value: int) -> None:
        if self._player is None:
            return
        try:
            self._player.volume = value
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def toggle_mute(self) -> None:
        if self._player is None:
            return
        try:
            self._player.mute = not bool(getattr(self._player, "mute", False))
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def set_muted(self, muted: bool) -> None:
        if self._player is None:
            return
        try:
            self._player.mute = muted
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def set_cursor_autohide(self, value: int | None) -> None:
        if self._player is None:
            return
        try:
            self._player["input-cursor"] = True
            self._player["cursor-autohide-fs-only"] = False
            self._player["cursor-autohide"] = value if value is not None else "no"
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def pause(self) -> None:
        if self._player is None:
            return
        try:
            self._player.pause = True
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def resume(self) -> None:
        if self._player is None:
            return
        try:
            self._player.pause = False
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def position_seconds(self) -> int | None:
        if self._player is None:
            return None
        try:
            pos = self._player.time_pos
            return int(pos) if pos is not None else None
        except Exception:
            return None

    def duration_seconds(self) -> int:
        if self._player is None:
            return 0
        try:
            return int(self._player.duration or 0)
        except Exception:
            return 0

    def _subtitle_language_label(self, lang: str) -> str:
        normalized = lang.strip().lower()
        return {
            "zh": "简体中文",
            "chi": "简体中文",
            "zho": "简体中文",
            "chs": "简体中文",
            "simplified": "简体中文",
            "zh-cn": "简体中文",
            "zh-hans": "简体中文",
            "zh-tw": "繁体中文",
            "cht": "繁体中文",
            "traditional": "繁体中文",
            "zh-hant": "繁体中文",
            "en": "English",
            "eng": "English",
            "ja": "日本語",
            "jpn": "日本語",
        }.get(normalized, normalized or "")

    def _subtitle_track_label(self, title: str, lang: str, is_default: bool, is_forced: bool, index: int) -> str:
        base = title.strip() or self._subtitle_language_label(lang) or f"字幕 {index}"
        suffixes = []
        if is_default:
            suffixes.append("默认")
        if is_forced:
            suffixes.append("强制")
        if not suffixes:
            return base
        return f"{base} ({'/'.join(suffixes)})"

    def _is_chinese_subtitle_track(self, track: SubtitleTrack) -> bool:
        if track.lang in {"zh", "chi", "zho", "chs", "zh-cn", "zh-hans", "zh-tw", "cht", "zh-hant"}:
            return True
        lowered_title = track.title.casefold()
        return any(token in lowered_title for token in ("中文", "简中", "繁中", "中字", "chinese"))

    def _chinese_subtitle_preference(self, track: SubtitleTrack) -> int:
        normalized_lang = track.lang.casefold()
        lowered_title = track.title.casefold()
        simplified_langs = {"zh", "chi", "zho", "chs", "zh-cn", "zh-hans"}
        traditional_langs = {"zh-tw", "cht", "zh-hant"}
        simplified_tokens = ("简中", "简体", "chs", "sc", "gb", "hans", "simplified")
        traditional_tokens = ("繁中", "繁體", "繁体", "cht", "tc", "big5", "hant", "traditional", "tranditional")
        if any(token in lowered_title for token in simplified_tokens):
            return 2
        if any(token in lowered_title for token in traditional_tokens):
            return 0
        if normalized_lang in simplified_langs:
            return 2
        if normalized_lang in traditional_langs:
            return 0
        return 1

    def _is_english_subtitle_track(self, track: SubtitleTrack) -> bool:
        if track.lang in {"en", "eng"}:
            return True
        lowered_title = track.title.casefold()
        return "english" in lowered_title

    def _preferred_subtitle_sort_key(self, track: SubtitleTrack) -> tuple[int, int, int]:
        return (
            self._chinese_subtitle_preference(track),
            int(track.is_default),
            int(bool(track.title)),
        )

    def subtitle_tracks(self) -> list[SubtitleTrack]:
        if self._player is None:
            return []
        try:
            raw_tracks = getattr(self._player, "track_list", None) or []
        except Exception:
            return []

        tracks: list[SubtitleTrack] = []
        for raw_track in raw_tracks:
            if raw_track.get("type") != "sub" or raw_track.get("external"):
                continue
            title = str(raw_track.get("title") or "").strip()
            lang = str(raw_track.get("lang") or "").strip().lower()
            is_default = bool(raw_track.get("default"))
            is_forced = bool(raw_track.get("forced"))
            tracks.append(
                SubtitleTrack(
                    id=int(raw_track["id"]),
                    title=title,
                    lang=lang,
                    is_default=is_default,
                    is_forced=is_forced,
                    label=self._subtitle_track_label(title, lang, is_default, is_forced, len(tracks) + 1),
                )
            )
        return tracks

    def apply_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
        if self._player is None:
            return None
        try:
            if mode == "off":
                self._player.sid = "no"
                return None
            if mode == "track" and track_id is not None:
                self._player.sid = track_id
                return track_id
            tracks = self.subtitle_tracks()
            chinese_tracks = [track for track in tracks if self._is_chinese_subtitle_track(track)]
            english_tracks = [track for track in tracks if self._is_english_subtitle_track(track)]
            preferred_track = None
            if chinese_tracks:
                preferred_track = max(chinese_tracks, key=self._preferred_subtitle_sort_key)
            elif english_tracks:
                preferred_track = max(english_tracks, key=self._preferred_subtitle_sort_key)
            if preferred_track is not None:
                self._player.sid = preferred_track.id
                return preferred_track.id
            self._player.sid = "auto"
            return None
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return None
            raise

    def apply_secondary_subtitle_mode(self, mode: str, track_id: int | None = None) -> int | None:
        if self._player is None:
            return None
        try:
            if mode == "off":
                self._set_player_property("secondary-sid", "no")
                return None
            if mode == "track" and track_id is not None:
                self._set_player_property("secondary-sid", track_id)
                return track_id
            self._set_player_property("secondary-sid", "no")
            return None
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return None
            raise

    def current_subtitle_track_id(self) -> int | None:
        value = self._player_property("sid", None)
        if value in {None, "auto", "no"}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _subtitle_track_ids(self) -> set[int]:
        if self._player is None:
            return set()
        raw_tracks = getattr(self._player, "track_list", [])
        track_ids: set[int] = set()
        for raw_track in raw_tracks:
            if raw_track.get("type") != "sub":
                continue
            try:
                track_ids.add(int(raw_track["id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return track_ids

    def _detect_new_subtitle_track_id(self, before_ids: set[int]) -> int | None:
        for attempt in range(6):
            after_ids = self._subtitle_track_ids()
            new_ids = sorted(after_ids - before_ids)
            if new_ids:
                return new_ids[-1]
            if attempt == 5:
                break
            app = QCoreApplication.instance()
            if app is not None:
                app.processEvents()
            time.sleep(0.01)
        return None

    def load_external_subtitle(self, path: str, *, select_for_secondary: bool = False) -> int | None:
        if self._player is None:
            return None
        before_ids = self._subtitle_track_ids()
        try:
            self._player.command("sub-add", path, "auto")
            track_id = self._detect_new_subtitle_track_id(before_ids)
            if select_for_secondary and track_id is not None:
                self.apply_secondary_subtitle_mode("track", track_id=track_id)
            return track_id
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return None
            raise

    def remove_subtitle_track(self, track_id: int | None) -> None:
        if self._player is None or track_id is None:
            return
        try:
            current_secondary_sid = self._player_property("secondary-sid", None)
            if str(current_secondary_sid) == str(track_id):
                self.apply_secondary_subtitle_mode("off")
            if track_id not in self._subtitle_track_ids():
                return
            self._player.command("sub-remove", track_id)
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def subtitle_position(self) -> int:
        value = self._player_property("sub-pos", 50)
        return self._int_property_value(value, 50)

    def set_subtitle_position(self, value: int) -> None:
        clamped = max(0, min(int(value), 100))
        self._set_player_property("sub-pos", clamped)

    def secondary_subtitle_position(self) -> int:
        value = self._player_property("secondary-sub-pos", 50)
        return self._int_property_value(value, 50)

    def supports_secondary_subtitle_position(self) -> bool:
        if self._player is None:
            return False
        try:
            self._player_property("secondary-sub-pos", 50)
            if hasattr(self._player, "__getitem__"):
                _ = self._player["secondary-sub-pos"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def set_secondary_subtitle_position(self, value: int) -> None:
        clamped = max(0, min(int(value), 100))
        self._set_player_property("secondary-sub-pos", clamped)

    def subtitle_scale(self) -> int:
        value = self._player_property("sub-scale", 1.0)
        return self._scale_property_percent(value, 100)

    def set_subtitle_scale(self, value: int) -> None:
        clamped = max(50, min(int(value), 200))
        self._set_player_property("sub-scale", clamped / 100)

    def secondary_subtitle_scale(self) -> int:
        value = self._player_property("secondary-sub-scale", 1.0)
        return self._scale_property_percent(value, 100)

    def set_secondary_subtitle_scale(self, value: int) -> None:
        clamped = max(50, min(int(value), 200))
        self._set_player_property("secondary-sub-scale", clamped / 100)

    def subtitle_ass_override(self) -> str:
        value = self._player_property("sub-ass-override", "scale")
        return self._ass_override_value(value, "scale")

    def set_subtitle_ass_override(self, value: str) -> None:
        self._set_player_property("sub-ass-override", self._ass_override_value(value, "scale"))

    def secondary_subtitle_ass_override(self) -> str:
        value = self._player_property("secondary-sub-ass-override", "strip")
        return self._ass_override_value(value, "strip")

    def set_secondary_subtitle_ass_override(self, value: str) -> None:
        self._set_player_property("secondary-sub-ass-override", self._ass_override_value(value, "strip"))

    def subtitle_ass_force_margins(self) -> str:
        value = self._player_property("sub-ass-force-margins", "no")
        return self._yes_no_value(value, "no")

    def set_subtitle_ass_force_margins(self, value: str) -> None:
        self._set_player_property("sub-ass-force-margins", self._yes_no_value(value, "no"))

    def supports_subtitle_scale(self) -> bool:
        if self._player is None:
            return False
        try:
            _ = self._player["sub-scale"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def supports_secondary_subtitle_scale(self) -> bool:
        if self._player is None:
            return False
        try:
            _ = self._player["secondary-sub-scale"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def supports_subtitle_ass_override(self) -> bool:
        if self._player is None:
            return False
        try:
            _ = self._player["sub-ass-override"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def supports_secondary_subtitle_ass_override(self) -> bool:
        if self._player is None:
            return False
        try:
            _ = self._player["secondary-sub-ass-override"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def supports_subtitle_ass_force_margins(self) -> bool:
        if self._player is None:
            return False
        try:
            _ = self._player["sub-ass-force-margins"]
            return True
        except Exception as exc:
            if self._is_missing_mpv_property_error(exc):
                return False
            if getattr(self._player, "core_shutdown", False):
                return False
            raise

    def _audio_language_label(self, lang: str) -> str:
        normalized = lang.strip().lower()
        return {
            "zh": "中文",
            "chi": "中文",
            "zho": "中文",
            "cmn": "国语",
            "en": "English",
            "eng": "English",
            "ja": "日语",
            "jpn": "日语",
        }.get(normalized, normalized or "")

    def _audio_track_label(self, title: str, lang: str, is_default: bool, is_forced: bool, index: int) -> str:
        base = title.strip() or self._audio_language_label(lang) or f"音轨 {index}"
        suffixes = []
        if is_default:
            suffixes.append("默认")
        if is_forced:
            suffixes.append("强制")
        if not suffixes:
            return base
        return f"{base} ({'/'.join(suffixes)})"

    def _audio_track_detail_label(self, raw_track: object, track_id: int) -> str:
        if not isinstance(raw_track, dict):
            return f"ID {track_id}"

        parts: list[str] = []

        codec = str(raw_track.get("codec") or raw_track.get("audio-codec") or "").strip().upper()
        if codec:
            parts.append(codec)

        channels = raw_track.get("audio-channels")
        if channels in (None, ""):
            channels = raw_track.get("channels")
        if channels not in (None, ""):
            parts.append(f"{channels}ch")

        samplerate = raw_track.get("audio-samplerate")
        if samplerate in (None, ""):
            samplerate = raw_track.get("samplerate")
        if samplerate not in (None, ""):
            parts.append(f"{samplerate}Hz")

        parts.append(f"ID {track_id}")
        return " / ".join(parts)

    def _audio_track_detail_parts(self, raw_track: object) -> list[str]:
        if not isinstance(raw_track, dict):
            return []

        parts: list[str] = []

        codec = str(raw_track.get("codec") or raw_track.get("audio-codec") or "").strip().upper()
        if codec:
            parts.append(codec)

        channels = raw_track.get("audio-channels")
        if channels in (None, ""):
            channels = raw_track.get("channels")
        if channels not in (None, ""):
            parts.append(f"{channels}ch")

        samplerate = raw_track.get("audio-samplerate")
        if samplerate in (None, ""):
            samplerate = raw_track.get("samplerate")
        if samplerate not in (None, ""):
            parts.append(f"{samplerate}Hz")

        return parts

    def _is_preferred_audio_track(self, track: AudioTrack) -> bool:
        if track.lang in {"zh", "chi", "zho", "cmn"}:
            return True
        lowered_title = track.title.casefold()
        return any(token in lowered_title for token in ("中文", "国语", "普通话", "mandarin", "chinese"))

    def _preferred_audio_sort_key(self, track: AudioTrack) -> tuple[int, int]:
        return (int(track.is_default), int(bool(track.title)))

    def audio_tracks(self) -> list[AudioTrack]:
        if self._player is None:
            return []
        try:
            raw_tracks = getattr(self._player, "track_list", None) or []
        except Exception:
            return []

        track_entries: list[tuple[int, str, str, bool, bool, object]] = []
        for raw_track in raw_tracks:
            if raw_track.get("type") != "audio" or raw_track.get("external"):
                continue
            title = str(raw_track.get("title") or "").strip()
            lang = str(raw_track.get("lang") or "").strip().lower()
            is_default = bool(raw_track.get("default"))
            is_forced = bool(raw_track.get("forced"))
            track_entries.append(
                (
                    int(raw_track["id"]),
                    title,
                    lang,
                    is_default,
                    is_forced,
                    raw_track,
                )
            )

        base_labels = [
            self._audio_track_label(title, lang, is_default, is_forced, index + 1)
            for index, (_, title, lang, is_default, is_forced, _) in enumerate(track_entries)
        ]
        duplicate_labels = {label for label in base_labels if base_labels.count(label) > 1}

        tracks: list[AudioTrack] = []
        for index, (track_id, title, lang, is_default, is_forced, raw_track) in enumerate(track_entries):
            label = base_labels[index]
            detail_parts = self._audio_track_detail_parts(raw_track)
            if label in duplicate_labels:
                if detail_parts:
                    detail_parts.append(f"ID {track_id}")
                else:
                    detail_parts = [f"ID {track_id}"]
                label = f"{label} [{ ' / '.join(detail_parts) }]"
            tracks.append(
                AudioTrack(
                    id=track_id,
                    title=title,
                    lang=lang,
                    is_default=is_default,
                    is_forced=is_forced,
                    label=label,
                )
            )
        return tracks

    def apply_audio_mode(self, mode: str, track_id: int | None = None) -> int | None:
        if self._player is None:
            return None
        try:
            if mode == "track" and track_id is not None:
                self._player.aid = track_id
                return track_id
            # preferred_tracks = [track for track in self.audio_tracks() if self._is_preferred_audio_track(track)]
            # if preferred_tracks:
            #     preferred_track = max(preferred_tracks, key=self._preferred_audio_sort_key)
            #     self._player.aid = preferred_track.id
            #     return preferred_track.id
            self._player.aid = "auto"
            return None
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return None
            raise

    def toggle_video_info(self) -> None:
        if self._player is None:
            return
        try:
            self._player.command("script-binding", "stats/display-stats-toggle")
        except Exception:
            if getattr(self._player, "core_shutdown", False):
                return
            raise

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)
