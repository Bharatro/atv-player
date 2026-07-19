from atv_player.controllers.telegram_channel_controller import (
    TelegramChannelController,
)


class FakeApiClient:
    def __init__(self) -> None:
        self.search_payload: dict = {"list": [], "total": 0}
        self.search_calls: list[tuple[str, int]] = []

    def search_telegram_channel_items(self, keyword: str, page: int) -> dict:
        self.search_calls.append((keyword, page))
        return self.search_payload


def test_search_items_maps_channel_search_payload_drive_type() -> None:
    api = FakeApiClient()
    api.search_payload = {
        "list": [
            {
                "vod_id": "https://pan.baidu.com/s/demo",
                "vod_name": "频道资源",
                "vod_remarks": "百度",
            }
        ],
        "total": 1,
    }
    controller = TelegramChannelController(api)

    items, total = controller.search_items("频道资源", page=1)

    assert api.search_calls == [("频道资源", 1)]
    assert total == 1
    assert items[0].share_type == "10"
    assert items[0].type_name == "百度"


def test_search_items_maps_percent_encoded_channel_share_link_drive_type() -> None:
    api = FakeApiClient()
    api.search_payload = {
        "list": [
            {
                "vod_id": "https%3A%2F%2Fpan.baidu.com%2Fs%2Fdemo%3Fpwd%3D1234",
                "vod_name": "频道资源",
                "vod_remarks": "更新25集 4K",
                "vod_play_from": "tg-search",
            }
        ],
        "total": 1,
    }
    controller = TelegramChannelController(api)

    items, total = controller.search_items("频道资源", page=1)

    assert total == 1
    assert items[0].share_type == "10"
    assert items[0].type_name == "百度"
