from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlaybackStartupStage(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    RESOLVING = "resolving"
    CONNECTING = "connecting"
    BUFFERING = "buffering"
    PLAYING = "playing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlaybackFailureAction:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class PlaybackStartupState:
    stage: PlaybackStartupStage
    message: str = ""
    actions: tuple[PlaybackFailureAction, ...] = ()


class PlaybackStartupCoordinator:
    def idle(self) -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.IDLE)

    def preparing(self, message: str = "正在准备播放项") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.PREPARING, message=message)

    def resolving(self, message: str = "正在解析播放地址") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.RESOLVING, message=message)

    def connecting(self, message: str = "正在连接视频源") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.CONNECTING, message=message)

    def buffering(self, message: str = "正在等待首帧") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.BUFFERING, message=message)

    def playing(self, message: str = "播放中") -> PlaybackStartupState:
        return PlaybackStartupState(stage=PlaybackStartupStage.PLAYING, message=message)

    def failed(
        self,
        *,
        message: str,
        parse_required: bool,
        has_multiple_sources: bool,
    ) -> PlaybackStartupState:
        actions = [PlaybackFailureAction(key="retry", label="重试")]
        if has_multiple_sources:
            actions.append(PlaybackFailureAction(key="switch_line", label="换线路"))
        if parse_required:
            actions.append(PlaybackFailureAction(key="switch_parser", label="换解析器"))
        return PlaybackStartupState(
            stage=PlaybackStartupStage.FAILED,
            message=message,
            actions=tuple(actions),
        )
