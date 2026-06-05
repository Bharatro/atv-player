from __future__ import annotations

from atv_player.heat.controller import HeatController
from atv_player.heat.models import HeatClientContext, HeatMediaIdentity


class FakeService:
    def __init__(self) -> None:
        self.events = []

    def record_event(self, event):
        self.events.append(event)
        return True

    def load_recommendations(self, *, limit=24):
        return []

    def load_media_heat(self, media_key: str):
        return None


def test_heat_controller_records_media_event_with_installation_id() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        client=HeatClientContext(version="test", platform="linux"),
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: "evt-1",
    )

    controller.record_media_event(
        "play_start",
        HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏"),
        context={"source_kind": "plugin"},
    )

    assert len(service.events) == 1
    assert service.events[0].installation_id == "install-1"
    assert service.events[0].event_type == "play_start"


def test_heat_controller_sends_effective_watch_once_per_media_key() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: f"evt-{len(service.events) + 1}",
    )
    media = HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏")

    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=600,
            duration_seconds=2700,
        )
        is True
    )
    assert (
        controller.maybe_record_effective_watch(
            media, position_seconds=900, duration_seconds=2700
        )
        is False
    )
    assert [event.event_type for event in service.events] == ["watch_progress"]
    assert service.events[0].context["episode_index"] == 0
    assert service.events[0].context["episode_number"] == 0


def test_heat_controller_sends_effective_watch_once_per_episode_number() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: f"evt-{len(service.events) + 1}",
    )
    media = HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏")

    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=600,
            duration_seconds=2700,
            episode_index=0,
            episode_number=1,
        )
        is True
    )
    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=600,
            duration_seconds=2700,
            episode_index=1,
            episode_number=2,
        )
        is True
    )
    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=900,
            duration_seconds=2700,
            episode_index=1,
            episode_number=2,
        )
        is False
    )

    assert [event.context["episode_number"] for event in service.events] == [1, 2]


def test_heat_controller_sends_movie_progress_every_ten_minutes() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: f"evt-{len(service.events) + 1}",
    )
    media = HeatMediaIdentity(media_key="tmdb:movie:1", title="电影", media_type="movie")

    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=599,
            duration_seconds=7200,
        )
        is False
    )
    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=600,
            duration_seconds=7200,
        )
        is True
    )
    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=900,
            duration_seconds=7200,
        )
        is False
    )
    assert (
        controller.maybe_record_effective_watch(
            media,
            position_seconds=1200,
            duration_seconds=7200,
        )
        is True
    )

    assert [event.context["position_seconds"] for event in service.events] == [600, 1200]
    assert [event.context["duration_seconds"] for event in service.events] == [7200, 7200]
    for event in service.events:
        assert "progress_bucket" not in event.context
        assert "progress_checkpoint_seconds" not in event.context
        assert "progress_interval_seconds" not in event.context
        assert "progress_percent" not in event.context


def test_heat_controller_uses_short_media_threshold() -> None:
    service = FakeService()
    controller = HeatController(
        service,
        installation_id="install-1",
        async_runner=lambda fn: fn(),
        clock_ms=lambda: 1780660000000,
        event_id_factory=lambda: "evt-1",
    )

    sent = controller.maybe_record_effective_watch(
        HeatMediaIdentity(media_key="tmdb:movie:1", title="短片"),
        position_seconds=59,
        duration_seconds=300,
    )

    assert sent is False
    assert service.events == []

    sent = controller.maybe_record_effective_watch(
        HeatMediaIdentity(media_key="tmdb:movie:1", title="短片"),
        position_seconds=60,
        duration_seconds=300,
    )

    assert sent is True
