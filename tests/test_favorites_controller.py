from pathlib import Path

from atv_player.favorites_repository import FavoritesRepository
from atv_player.models import VodItem


def test_favorites_controller_refreshes_latest_title_and_marks_changed(tmp_path: Path) -> None:
    from atv_player.controllers.favorites_controller import FavoritesController

    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "旧标题",
            "latest_vod_name": "旧标题",
            "vod_pic": "poster-a",
            "vod_remarks": "1080P",
            "title_changed": False,
            "created_at": 10,
            "updated_at": 10,
        }
    )

    controller = FavoritesController(
        repo,
        detail_loader_by_source={
            "browse": lambda record: VodItem(
                vod_id=record.vod_id,
                vod_name="新标题",
                vod_pic="poster-b",
                vod_remarks="完结",
            )
        },
    )

    records, total = controller.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].record.latest_vod_name == "新标题"
    assert records[0].record.title_changed is True
    assert records[0].display_title == "新标题"
    assert records[0].secondary_text == "原收藏标题: 旧标题"


def test_favorites_controller_refresh_failure_keeps_snapshot_data(tmp_path: Path) -> None:
    from atv_player.controllers.favorites_controller import FavoritesController

    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "youtube",
            "source_key": "",
            "source_name": "YouTube",
            "vod_id": "yt:video:1",
            "vod_name_snapshot": "吃饭录像",
            "latest_vod_name": "吃饭录像",
            "vod_pic": "poster-a",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 10,
            "updated_at": 10,
        }
    )

    controller = FavoritesController(
        repo,
        detail_loader_by_source={"youtube": lambda _record: (_ for _ in ()).throw(ValueError("boom"))},
    )

    records, total = controller.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].record.latest_vod_name == "吃饭录像"
    assert records[0].record.title_changed is False
    assert records[0].secondary_text == ""


def test_favorites_controller_routes_add_remove_and_lookup_to_repository(tmp_path: Path) -> None:
    from atv_player.controllers.favorites_controller import FavoritesController

    repo = FavoritesRepository(tmp_path / "app.db")
    controller = FavoritesController(repo, detail_loader_by_source={})
    payload = {
        "source_kind": "browse",
        "source_key": "",
        "source_name": "文件浏览",
        "vod_id": "detail-2",
        "vod_name_snapshot": "庆余年",
        "latest_vod_name": "庆余年",
        "vod_pic": "",
        "vod_remarks": "",
        "title_changed": False,
        "created_at": 11,
        "updated_at": 11,
    }

    controller.add_favorite(payload)

    assert controller.is_favorited(source_kind="browse", source_key="", vod_id="detail-2") is True

    records, _ = repo.load_page(page=1, size=20, keyword="")
    controller.remove_favorite([records[0]])

    assert controller.is_favorited(source_kind="browse", source_key="", vod_id="detail-2") is False
