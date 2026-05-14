import logging
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from time import time
from typing import cast

from atv_player.models import (
    HistoryRecord,
    PlayItem,
    PlaybackSource,
    PlaybackSourceGroup,
    PlaybackDetailAction,
    PlaybackDetailFieldAction,
    PlaybackLoadResult,
    VodItem,
)
from atv_player.player.resume import resolve_resume_index


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PlayerSession:
    vod: VodItem
    playlist: list[PlayItem]
    start_index: int
    start_position_seconds: int
    speed: float
    playlists: list[list[PlayItem]] = field(default_factory=list)
    playlist_index: int = 0
    source_groups: list[PlaybackSourceGroup] = field(default_factory=list)
    source_group_index: int = 0
    source_index: int = 0
    opening_seconds: int = 0
    ending_seconds: int = 0
    detail_resolver: Callable[[PlayItem], VodItem | None] | None = None
    resolved_vod_by_id: dict[str, VodItem] = field(default_factory=dict)
    use_local_history: bool = True
    playback_loader: Callable[[PlayItem], PlaybackLoadResult | None] | None = None
    async_playback_loader: bool = False
    detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None
    detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None
    danmaku_controller: object | None = None
    playback_progress_reporter: Callable[[PlayItem, int, bool], None] | None = None
    playback_stopper: Callable[[PlayItem], None] | None = None
    playback_history_saver: Callable[[dict[str, object]], None] | None = None
    initial_log_message: str = ""
    is_placeholder: bool = False
    video_cover_override: str = ""
    prefetched_next_danmaku_indices: set[int] = field(default_factory=set)


class PlayerController:
    def __init__(self, api_client) -> None:
        self._api_client = api_client

    def _bind_playback_loader(
        self,
        playback_loader: Callable[..., PlaybackLoadResult | None] | None,
        session: PlayerSession,
    ) -> Callable[[PlayItem], PlaybackLoadResult | None] | None:
        if playback_loader is None:
            return None
        parameters = list(inspect.signature(playback_loader).parameters.values())
        positional = [
            parameter
            for parameter in parameters
            if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
        if has_varargs or len(positional) >= 2:
            return lambda item, playback_loader=playback_loader, session=session: playback_loader(session, item)
        return cast(Callable[[PlayItem], PlaybackLoadResult | None], playback_loader)

    def _build_legacy_source_groups(
        self,
        playlist: list[PlayItem],
        playlists: list[list[PlayItem]] | None,
    ) -> list[PlaybackSourceGroup]:
        normalized = [group for group in (playlists or []) if group]
        if not normalized:
            normalized = [playlist]
        source_groups: list[PlaybackSourceGroup] = []
        for group_index, current_playlist in enumerate(normalized):
            label = (
                current_playlist[0].play_source
                if current_playlist and current_playlist[0].play_source
                else f"线路 {group_index + 1}"
            )
            source_groups.append(
                PlaybackSourceGroup(
                    label=label,
                    sources=[PlaybackSource(label=label, playlist=current_playlist)],
                )
            )
        return source_groups

    def _flatten_source_groups(
        self,
        source_groups: list[PlaybackSourceGroup],
    ) -> tuple[list[list[PlayItem]], dict[tuple[int, int], int], dict[int, tuple[int, int]]]:
        playlists: list[list[PlayItem]] = []
        pair_to_flat: dict[tuple[int, int], int] = {}
        flat_to_pair: dict[int, tuple[int, int]] = {}
        for group_index, group in enumerate(source_groups):
            for source_index, source in enumerate(group.sources):
                flat_index = len(playlists)
                playlists.append(source.playlist)
                pair_to_flat[(group_index, source_index)] = flat_index
                flat_to_pair[flat_index] = (group_index, source_index)
        return playlists, pair_to_flat, flat_to_pair

    def _normalize_source_groups(
        self,
        playlist: list[PlayItem],
        playlists: list[list[PlayItem]] | None,
        playlist_index: int,
        source_groups: list[PlaybackSourceGroup] | None,
        source_group_index: int,
        source_index: int,
    ) -> tuple[list[PlaybackSourceGroup], list[list[PlayItem]], int, int, int, list[PlayItem]]:
        normalized_groups = [group for group in (source_groups or []) if group.sources]
        if not normalized_groups:
            normalized_groups = self._build_legacy_source_groups(playlist, playlists)
            source_group_index = max(0, min(playlist_index, len(normalized_groups) - 1))
            source_index = 0
        flat_playlists, pair_to_flat, _ = self._flatten_source_groups(normalized_groups)
        if not flat_playlists:
            flat_playlists = [playlist]
            normalized_groups = [
                PlaybackSourceGroup(label="线路 1", sources=[PlaybackSource(label="线路 1", playlist=playlist)])
            ]
            pair_to_flat = {(0, 0): 0}
        source_group_index = max(0, min(source_group_index, len(normalized_groups) - 1))
        active_group = normalized_groups[source_group_index]
        source_index = max(0, min(source_index, len(active_group.sources) - 1))
        playlist_index = pair_to_flat[(source_group_index, source_index)]
        return (
            normalized_groups,
            flat_playlists,
            playlist_index,
            source_group_index,
            source_index,
            active_group.sources[source_index].playlist,
        )

    def _restore_selected_source(
        self,
        source_groups: list[PlaybackSourceGroup],
        playlists: list[list[PlayItem]],
        playlist_index: int,
        source_group_index: int,
        source_index: int,
        history: HistoryRecord | None,
    ) -> tuple[int, int, int, list[PlayItem]]:
        _, pair_to_flat, flat_to_pair = self._flatten_source_groups(source_groups)
        if history is not None:
            history_pair = (history.source_group_index, history.source_index)
            pair_flat_index = pair_to_flat.get(history_pair, -1)
            should_use_explicit_pair = (
                history_pair in pair_to_flat
                and (
                    history.source_group_index != 0
                    or history.source_index != 0
                    or pair_flat_index == history.playlist_index
                )
            )
            if should_use_explicit_pair:
                source_group_index = history.source_group_index
                active_group = source_groups[source_group_index]
                if 0 <= history.source_index < len(active_group.sources):
                    source_index = history.source_index
                else:
                    source_index = 0
            elif 0 <= history.playlist_index < len(playlists):
                source_group_index, source_index = flat_to_pair[history.playlist_index]
        playlist_index = pair_to_flat[(source_group_index, source_index)]
        return (
            source_group_index,
            source_index,
            playlist_index,
            source_groups[source_group_index].sources[source_index].playlist,
        )

    def create_session(
        self,
        vod: VodItem,
        playlist: list[PlayItem],
        clicked_index: int,
        playlists: list[list[PlayItem]] | None = None,
        playlist_index: int = 0,
        source_groups: list[PlaybackSourceGroup] | None = None,
        source_group_index: int = 0,
        source_index: int = 0,
        detail_resolver: Callable[[PlayItem], VodItem | None] | None = None,
        resolved_vod_by_id: dict[str, VodItem] | None = None,
        use_local_history: bool = True,
        restore_history: bool = False,
        playback_loader: Callable[[PlayItem], PlaybackLoadResult | None] | None = None,
        async_playback_loader: bool = False,
        detail_action_runner: Callable[[PlayItem, str], list[PlaybackDetailAction]] | None = None,
        detail_field_runner: Callable[[PlayItem, PlaybackDetailFieldAction], None] | None = None,
        danmaku_controller: object | None = None,
        playback_progress_reporter: Callable[[PlayItem, int, bool], None] | None = None,
        playback_stopper: Callable[[PlayItem], None] | None = None,
        playback_history_loader: Callable[[], HistoryRecord | None] | None = None,
        playback_history_saver: Callable[[dict[str, object]], None] | None = None,
        initial_log_message: str = "",
        is_placeholder: bool = False,
    ) -> PlayerSession:
        normalized_source_groups, normalized_playlists, playlist_index, source_group_index, source_index, active_playlist = self._normalize_source_groups(
            playlist,
            playlists,
            playlist_index,
            source_groups,
            source_group_index,
            source_index,
        )
        history = playback_history_loader() if playback_history_loader is not None else None
        if history is None and (use_local_history or restore_history):
            history = self._api_client.get_history(vod.vod_id)
        source_group_index, source_index, playlist_index, active_playlist = self._restore_selected_source(
            normalized_source_groups,
            normalized_playlists,
            playlist_index,
            source_group_index,
            source_index,
            history,
        )
        start_index = resolve_resume_index(history, active_playlist, clicked_index)
        matched_history = history is not None and (
            start_index == history.episode or playback_history_loader is not None
        )
        if matched_history and history is not None:
            position_seconds = int(history.position / 1000)
            speed = history.speed
        else:
            position_seconds = 0
            speed = 1.0
        logger.info(
            "Create player session vod_id=%s playlist_size=%s start_index=%s restored=%s",
            vod.vod_id,
            len(active_playlist),
            start_index,
            matched_history,
        )
        session = PlayerSession(
            vod=vod,
            playlist=active_playlist,
            start_index=start_index,
            start_position_seconds=position_seconds,
            speed=speed,
            playlists=normalized_playlists,
            playlist_index=playlist_index,
            source_groups=normalized_source_groups,
            source_group_index=source_group_index,
            source_index=source_index,
            opening_seconds=int((history.opening if history else 0) / 1000),
            ending_seconds=int((history.ending if history else 0) / 1000),
            detail_resolver=detail_resolver,
            resolved_vod_by_id=dict(resolved_vod_by_id or {}),
            use_local_history=use_local_history,
            playback_loader=playback_loader,
            async_playback_loader=async_playback_loader,
            detail_action_runner=detail_action_runner,
            detail_field_runner=detail_field_runner,
            danmaku_controller=danmaku_controller,
            playback_progress_reporter=playback_progress_reporter,
            playback_stopper=playback_stopper,
            initial_log_message=initial_log_message,
            is_placeholder=is_placeholder,
        )
        session.playback_loader = self._bind_playback_loader(playback_loader, session)
        session.playback_history_saver = playback_history_saver
        return session

    def resolve_play_item_detail(self, session: PlayerSession, play_item: PlayItem) -> VodItem | None:
        if not play_item.vod_id or session.detail_resolver is None:
            return None
        if play_item.vod_id in session.resolved_vod_by_id:
            resolved_vod = session.resolved_vod_by_id[play_item.vod_id]
            if resolved_vod is None:
                return None
        else:
            resolved_vod = session.detail_resolver(play_item)
            session.resolved_vod_by_id[play_item.vod_id] = resolved_vod
        if resolved_vod is None:
            return None
        url = resolved_vod.items[0].url if resolved_vod.items else resolved_vod.vod_play_url
        if not url:
            return None
        play_item.url = url
        return resolved_vod

    def report_progress(
        self,
        session: PlayerSession,
        current_index: int,
        position_seconds: int,
        speed: float,
        opening_seconds: int,
        ending_seconds: int,
        paused: bool,
        force_remote_report: bool = False,
    ) -> None:
        if not (0 <= current_index < len(session.playlist)):
            return
        current_item = session.playlist[current_index]
        position_ms = position_seconds * 1000
        if session.playback_progress_reporter is not None and (not paused or force_remote_report):
            session.playback_progress_reporter(current_item, position_ms, paused)
        logger.info(
            "Report playback progress vod_id=%s index=%s position_ms=%s paused=%s",
            session.vod.vod_id,
            current_index,
            position_ms,
            paused,
        )
        payload = {
            "cid": 0,
            "key": session.vod.vod_id,
            "vodName": session.vod.vod_name,
            "vodPic": session.vod.vod_pic,
            "vodRemarks": current_item.title,
            "episode": current_index,
            "episodeUrl": current_item.url,
            "position": position_ms,
            "opening": opening_seconds * 1000,
            "ending": ending_seconds * 1000,
            "speed": speed,
            "playlistIndex": session.playlist_index,
            "sourceGroupIndex": session.source_group_index,
            "sourceIndex": session.source_index,
            "createTime": int(time() * 1000),
        }
        if session.playback_history_saver is not None:
            session.playback_history_saver(payload)
        if not session.use_local_history:
            return
        self._api_client.save_history(payload)

    def stop_playback(self, session: PlayerSession, current_index: int) -> None:
        if session.playback_stopper is None:
            return
        if not (0 <= current_index < len(session.playlist)):
            return
        logger.info("Stop playback vod_id=%s index=%s", session.vod.vod_id, current_index)
        session.playback_stopper(session.playlist[current_index])
