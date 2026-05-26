from pathlib import Path

from atv_player.favorite_tmdb_bindings import FavoriteTMDBBindingRepository


def test_favorite_tmdb_binding_repository_round_trips_provider_identity(tmp_path: Path) -> None:
    repo = FavoriteTMDBBindingRepository(tmp_path / "app.db")

    repo.save(
        source_kind="browse",
        source_key="",
        vod_id="detail-1",
        provider_id="tv:76479",
        tmdb_id="76479",
        media_type="tv",
        title="黑袍纠察队",
        year="2019",
        updated_at=200,
    )

    binding = repo.load(source_kind="browse", source_key="", vod_id="detail-1")

    assert binding is not None
    assert binding.provider_id == "tv:76479"
    assert binding.tmdb_id == "76479"
    assert binding.media_type == "tv"
    assert binding.title == "黑袍纠察队"
    assert binding.year == "2019"


def test_favorite_tmdb_binding_repository_load_recent_orders_by_updated_at_desc(tmp_path: Path) -> None:
    repo = FavoriteTMDBBindingRepository(tmp_path / "app.db")
    repo.save(
        source_kind="browse",
        source_key="",
        vod_id="a",
        provider_id="tv:1",
        tmdb_id="1",
        media_type="tv",
        title="A",
        year="2020",
        updated_at=100,
    )
    repo.save(
        source_kind="browse",
        source_key="",
        vod_id="b",
        provider_id="movie:2",
        tmdb_id="2",
        media_type="movie",
        title="B",
        year="2021",
        updated_at=300,
    )

    rows = repo.load_recent(limit=1)

    assert [row.vod_id for row in rows] == ["b"]
