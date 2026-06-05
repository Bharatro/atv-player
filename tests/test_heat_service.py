from __future__ import annotations

import httpx

from atv_player.heat.models import HeatClientContext, HeatEvent, HeatMediaIdentity
from atv_player.heat.service import HEAT_API_BASE_URL, HeatService


def test_heat_service_posts_events_to_fixed_backend() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(
            202, json={"ok": True, "accepted": True, "event_id": "evt-1"}
        )

    service = HeatService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    delivered = service.record_event(
        HeatEvent(
            event_id="evt-1",
            installation_id="install-1",
            event_type="play_start",
            occurred_at=1780660000000,
            client=HeatClientContext(
                app="atv-player", version="0.69.1", platform="linux"
            ),
            media=HeatMediaIdentity(media_key="tmdb:tv:1399", title="权力的游戏"),
            context={
                "position_seconds": 0,
                "episode_url": "https://secret.example/1.m3u8",
            },
        )
    )

    assert delivered is True
    assert captured["method"] == "POST"
    assert captured["url"] == f"{HEAT_API_BASE_URL}/events"
    assert "episode_url" not in captured["json"]
    assert "tmdb:tv:1399" in captured["json"]


def test_heat_service_loads_recommendations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{HEAT_API_BASE_URL}/recommendations?limit=24"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "generated_at": 1780660000000,
                "window_seconds": 86400,
                "items": [
                    {
                        "media_key": "tmdb:movie:1",
                        "title": "测试电影",
                        "poster": "https://image.example/p.jpg",
                        "heat_score": 10.5,
                        "rank": 1,
                        "watching_now": 2,
                        "reason": "2 人正在播放",
                    }
                ],
            },
        )

    service = HeatService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    items = service.load_recommendations(limit=24)

    assert len(items) == 1
    assert items[0].media_key == "tmdb:movie:1"
    assert items[0].title == "测试电影"
    assert items[0].reason == "2 人正在播放"


def test_heat_service_loads_media_summary_with_percent_encoded_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{HEAT_API_BASE_URL}/media/tmdb%3Atv%3A1399"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "media_key": "tmdb:tv:1399",
                "watching_now": 23,
                "recent_watchers": 128,
                "display_text": "23 人正在播放",
            },
        )

    service = HeatService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    summary = service.load_media_heat("tmdb:tv:1399")

    assert summary is not None
    assert summary.display_text == "23 人正在播放"


def test_heat_service_returns_empty_results_on_failures() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False})

    service = HeatService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert service.load_recommendations(limit=24) == []
    assert service.load_media_heat("tmdb:tv:1399") is None
