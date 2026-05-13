from atv_player.player.startup import (
    PlaybackFailureAction,
    PlaybackStartupCoordinator,
    PlaybackStartupStage,
)


def test_startup_coordinator_builds_progressive_states() -> None:
    coordinator = PlaybackStartupCoordinator()

    assert coordinator.preparing().stage is PlaybackStartupStage.PREPARING
    assert coordinator.preparing().message == "正在准备播放项"
    assert coordinator.resolving().stage is PlaybackStartupStage.RESOLVING
    assert coordinator.connecting().stage is PlaybackStartupStage.CONNECTING
    assert coordinator.buffering().stage is PlaybackStartupStage.BUFFERING
    assert coordinator.playing().stage is PlaybackStartupStage.PLAYING
    assert coordinator.playing().actions == ()


def test_startup_coordinator_builds_failure_actions_for_parse_item_with_multiple_lines() -> None:
    coordinator = PlaybackStartupCoordinator()

    state = coordinator.failed(
        message="当前线路响应超时",
        parse_required=True,
        has_multiple_sources=True,
    )

    assert state.stage is PlaybackStartupStage.FAILED
    assert state.message == "当前线路响应超时"
    assert state.actions == (
        PlaybackFailureAction(key="retry", label="重试"),
        PlaybackFailureAction(key="switch_line", label="换线路"),
        PlaybackFailureAction(key="switch_parser", label="换解析器"),
    )


def test_startup_coordinator_omits_unavailable_failure_actions() -> None:
    coordinator = PlaybackStartupCoordinator()

    state = coordinator.failed(
        message="解析器未返回可播放地址",
        parse_required=False,
        has_multiple_sources=False,
    )

    assert state.actions == (
        PlaybackFailureAction(key="retry", label="重试"),
    )
