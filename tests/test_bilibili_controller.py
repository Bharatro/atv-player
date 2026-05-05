from atv_player.controllers.bilibili_controller import BilibiliController
from atv_player.models import CategoryFilter, CategoryFilterOption, DoubanCategory, PlayItem


class FakeApiClient:
    def __init__(self) -> None:
        self.category_payload = {"class": []}
        self.items_payload = {"list": [], "total": 0}
        self.search_payload = {"list": [], "total": 0}
        self.detail_payload = {"list": []}
        self.playback_payload = {"url": ["Episode 1", "http://b/1.mp4"], "header": {"Referer": "https://www.bilibili.com/"}}
        self.item_calls: list[tuple[str, int, dict[str, str] | None]] = []
        self.search_calls: list[tuple[str, int]] = []
        self.detail_calls: list[str] = []
        self.playback_source_calls: list[str] = []

    def list_bilibili_categories(self) -> dict:
        return self.category_payload

    def list_bilibili_items(self, category_id: str, page: int, filters: dict[str, str] | None = None) -> dict:
        self.item_calls.append((category_id, page, None if filters is None else dict(filters)))
        return self.items_payload

    def search_bilibili_items(self, keyword: str, page: int) -> dict:
        self.search_calls.append((keyword, page))
        return self.search_payload

    def get_bilibili_detail(self, vod_id: str) -> dict:
        self.detail_calls.append(vod_id)
        return self.detail_payload

    def get_bilibili_playback_source(self, vod_id: str) -> dict:
        self.playback_source_calls.append(vod_id)
        return self.playback_payload


def test_load_categories_preserves_backend_provided_recommendation() -> None:
    api = FakeApiClient()
    api.category_payload = {
        "class": [
            {"type_id": "0", "type_name": "后端推荐"},
            {"type_id": "bangumi", "type_name": "番剧"},
            {"type_id": "movie", "type_name": "电影"},
        ]
    }
    controller = BilibiliController(api)

    categories = controller.load_categories()

    assert categories == [
        DoubanCategory(type_id="0", type_name="后端推荐"),
        DoubanCategory(type_id="bangumi", type_name="番剧"),
        DoubanCategory(type_id="movie", type_name="电影"),
    ]


def test_load_categories_maps_filter_groups() -> None:
    api = FakeApiClient()
    api.category_payload = {
        "class": [
            {"type_id": "0", "type_name": "推荐"},
            {"type_id": "bangumi", "type_name": "番剧"},
        ],
        "filters": {
            "bangumi": [
                {
                    "key": "season_status",
                    "name": "状态",
                    "value": [
                        {"n": "全部", "v": "0"},
                        {"n": "完结", "v": "1"},
                    ],
                }
            ]
        },
    }
    controller = BilibiliController(api)

    categories = controller.load_categories()

    assert categories[1].filters == [
        CategoryFilter(
            key="season_status",
            name="状态",
            options=[
                CategoryFilterOption(name="全部", value="0"),
                CategoryFilterOption(name="完结", value="1"),
            ],
        )
    ]


def test_search_items_maps_bilibili_search_payload() -> None:
    api = FakeApiClient()
    api.search_payload = {
        "list": [
            {
                "vod_id": "BV1xx411c7mD",
                "vod_name": "孤独摇滚",
                "vod_pic": "poster.jpg",
                "vod_year": "2022",
                "vod_remarks": "9.2",
            }
        ],
        "total": 8,
    }
    controller = BilibiliController(api)

    items, total = controller.search_items("孤独摇滚", page=1)

    assert api.search_calls == [("孤独摇滚", 1)]
    assert total == 8
    assert items[0].vod_id == "BV1xx411c7mD"
    assert items[0].vod_remarks == "2022 - 9.2"


def test_bilibili_controller_passes_optional_filters_argument() -> None:
    api = FakeApiClient()
    controller = BilibiliController(api)

    controller.load_items("bangumi", 1, filters={"season_status": "1"})

    assert api.item_calls[-1] == ("bangumi", 1, {"season_status": "1"})


def test_load_folder_items_uses_t_query_and_first_page() -> None:
    api = FakeApiClient()
    api.items_payload = {
        "list": [
            {
                "vod_id": "folder-1",
                "vod_name": "第一季",
                "vod_pic": "folder.jpg",
                "vod_tag": "folder",
                "vod_year": "2024",
            },
            {
                "vod_id": "BVchild1",
                "vod_name": "第1话",
                "vod_pic": "episode.jpg",
                "vod_tag": "file",
                "vod_year": "2024",
                "vod_remarks": "9.9",
            },
        ]
    }
    controller = BilibiliController(api)

    items, total = controller.load_folder_items("folder-1")

    assert api.item_calls == [("folder-1", 1, None)]
    assert api.detail_calls == []
    assert total == 2
    assert [(item.vod_id, item.vod_tag) for item in items] == [("folder-1", "folder"), ("BVchild1", "file")]
    assert [item.vod_remarks for item in items] == ["2024", "2024 - 9.9"]


def test_build_request_disables_remote_history_and_exposes_local_bilibili_history_hooks() -> None:
    api = FakeApiClient()
    api.detail_payload = {
        "list": [
            {
                "vod_id": "BV1xx411c7mD",
                "vod_name": "孤独摇滚",
                "vod_pic": "poster.jpg",
                "vod_play_url": "第1话$BV1xx411c7mD#第2话$BV1yy522d8nE",
            }
        ]
    }
    load_calls: list[str] = []
    save_calls: list[tuple[str, dict[str, object]]] = []
    controller = BilibiliController(
        api,
        playback_history_loader=lambda vod_id: load_calls.append(vod_id) or None,
        playback_history_saver=lambda vod_id, payload: save_calls.append((vod_id, payload)),
    )

    request = controller.build_request("BV1xx411c7mD")
    first_item = request.playlist[0]

    assert request.use_local_history is False
    assert request.restore_history is False
    assert request.playback_loader is not None
    assert request.async_playback_loader is True
    assert request.playback_progress_reporter is None
    assert request.playback_stopper is None
    assert request.playback_history_loader is not None
    assert request.playback_history_saver is not None

    request.playback_history_loader()
    request.playback_history_saver({"position": 45000})
    request.playback_loader(first_item)

    assert load_calls == ["BV1xx411c7mD"]
    assert save_calls == [("BV1xx411c7mD", {"position": 45000})]
    assert first_item.url == "http://b/1.mp4"
    assert first_item.headers == {"Referer": "https://www.bilibili.com/"}
    assert api.playback_source_calls == ["BV1xx411c7mD"]


def test_load_playback_item_parses_java_map_style_header_string() -> None:
    api = FakeApiClient()
    api.playback_payload = {
        "url": "data:application/dash+xml;base64,PE1QRD48L01QRD4=",
        "header": (
            "{Cookie=SESSDATA=627aa33b%2C1793512479%2Cd0aa8%2A51;"
            "bili_jct=d2487e6999b44715203ec3db8b4afd0a;sid=fq0q4ahm, "
            "Referer=https://www.bilibili.com, "
            "User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36}"
        ),
    }
    controller = BilibiliController(api)
    item = PlayItem(title="视频", url="", vod_id="BV1xx411c7mD")

    controller.load_playback_item(item)

    assert item.url == "data:application/dash+xml;base64,PE1QRD48L01QRD4="
    assert item.headers == {
        "Cookie": "SESSDATA=627aa33b%2C1793512479%2Cd0aa8%2A51;bili_jct=d2487e6999b44715203ec3db8b4afd0a;sid=fq0q4ahm",
        "Referer": "https://www.bilibili.com",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    }


def test_build_request_splits_bilibili_routes_by_play_source_without_cross_group_id_corruption() -> None:
    api = FakeApiClient()
    api.detail_payload = {
        "list": [
            {
                "vod_id": "BV1ebREBmEha",
                "vod_name": "和AI玩猜历史人物游戏，又被它给耍了",
                "vod_pic": "poster.jpg",
                "vod_play_from": "BiliBili$$$相关视频$$$UP主视频",
                "vod_play_url": (
                    "视频$BV1ebREBmEha$$$"
                    "和AI玩历史猜人物游戏，差点吵起来$116225338313894-36684630727#"
                    "当朋友恋爱脑发作，就让他看这个视频$116458038368774-37773577100$$$"
                    "和AI玩猜历史人物游戏，又被它给耍了$BV1ebREBmEha#"
                    "读“野史”笑了就吃柠檬挑战（3）$BV1YgRKBGELF"
                ),
            }
        ]
    }
    controller = BilibiliController(api)

    request = controller.build_request("BV1ebREBmEha")

    assert request.playlist_index == 0
    assert len(request.playlists) == 3
    assert request.playlist is request.playlists[0]
    assert [item.play_source for item in request.playlists[0]] == ["BiliBili"]
    assert [item.play_source for item in request.playlists[1]] == ["相关视频", "相关视频"]
    assert [item.play_source for item in request.playlists[2]] == ["UP主视频", "UP主视频"]
    assert [item.vod_id for item in request.playlists[0]] == ["BV1ebREBmEha"]
    assert [item.vod_id for item in request.playlists[1]] == [
        "116225338313894-36684630727",
        "116458038368774-37773577100",
    ]
    assert [item.vod_id for item in request.playlists[2]] == ["BV1ebREBmEha", "BV1YgRKBGELF"]


def test_load_playback_item_raises_when_vod_id_missing() -> None:
    controller = BilibiliController(FakeApiClient())

    item = PlayItem(title="第1话", url="")

    try:
        controller.load_playback_item(item)
    except ValueError as exc:
        assert str(exc) == "缺少 B站 播放 ID"
    else:
        raise AssertionError("expected ValueError")
