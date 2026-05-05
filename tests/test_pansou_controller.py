from atv_player.controllers.pansou_controller import PansouController
from atv_player.models import VodItem


class FakeBrowseController:
    def __init__(self) -> None:
        self.search_calls: list[str] = []
        self.resolve_calls: list[str] = []
        self.results = [
            VodItem(vod_id="pan-1", vod_name="盘搜结果", vod_play_url="https://t.me/share"),
            VodItem(vod_id="pan-2", vod_name="第二条", vod_play_url="https://t.me/share2"),
        ]

    def search(self, keyword: str) -> list[VodItem]:
        self.search_calls.append(keyword)
        return list(self.results)

    def resolve_search_result(self, item: VodItem) -> str:
        self.resolve_calls.append(item.vod_id)
        return f"/resolved/{item.vod_id}"


def test_pansou_controller_search_items_uses_browse_search_and_counts_results() -> None:
    browse = FakeBrowseController()
    controller = PansouController(browse)

    items, total = controller.search_items("庆余年", page=1)

    assert browse.search_calls == ["庆余年"]
    assert [item.vod_id for item in items] == ["pan-1", "pan-2"]
    assert total == 2


def test_pansou_controller_resolve_search_result_delegates_to_browse_controller() -> None:
    browse = FakeBrowseController()
    controller = PansouController(browse)

    resolved = controller.resolve_search_result(VodItem(vod_id="pan-1", vod_name="盘搜结果", vod_play_url="https://t.me/share"))

    assert resolved == "/resolved/pan-1"
    assert browse.resolve_calls == ["pan-1"]
