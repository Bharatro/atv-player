from pathlib import Path

from atv_player.favorites_repository import FavoritesRepository


def test_favorites_repository_upserts_and_marks_changed_title(tmp_path: Path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "庆余年",
            "latest_vod_name": "庆余年",
            "vod_pic": "poster-a",
            "vod_remarks": "4K",
            "title_changed": False,
            "created_at": 100,
            "updated_at": 100,
        }
    )

    repo.update_refresh_state(
        "browse",
        "",
        "detail-1",
        latest_vod_name="庆余年 第二季",
        vod_pic="poster-b",
        vod_remarks="完结",
    )
    records, total = repo.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert records[0].vod_name_snapshot == "庆余年"
    assert records[0].latest_vod_name == "庆余年 第二季"
    assert records[0].title_changed is True


def test_favorites_repository_deletes_selected_and_filtered_rows(tmp_path: Path) -> None:
    repo = FavoritesRepository(tmp_path / "app.db")
    repo.save_favorite(
        {
            "source_kind": "browse",
            "source_key": "",
            "source_name": "文件浏览",
            "vod_id": "detail-1",
            "vod_name_snapshot": "庆余年",
            "latest_vod_name": "庆余年",
            "vod_pic": "",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 100,
            "updated_at": 100,
        }
    )
    repo.save_favorite(
        {
            "source_kind": "youtube",
            "source_key": "",
            "source_name": "YouTube",
            "vod_id": "yt:video:2",
            "vod_name_snapshot": "吃饭录像",
            "latest_vod_name": "吃饭录像",
            "vod_pic": "",
            "vod_remarks": "",
            "title_changed": False,
            "created_at": 101,
            "updated_at": 101,
        }
    )

    records, _ = repo.load_page(page=1, size=20, keyword="庆")
    repo.delete_favorites(records)
    remaining, total = repo.load_page(page=1, size=20, keyword="")

    assert total == 1
    assert remaining[0].vod_id == "yt:video:2"

    repo.delete_filtered(keyword="吃饭")
    cleared, cleared_total = repo.load_page(page=1, size=20, keyword="")

    assert cleared == []
    assert cleared_total == 0
