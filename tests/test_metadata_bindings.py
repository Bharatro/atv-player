from pathlib import Path

from atv_player.metadata.bindings import MetadataBindingRepository


def test_metadata_binding_repository_round_trips_normalized_title_and_year(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")

    repo.save(
        "  星际 穿越  ",
        "2014-11-07",
        provider="tmdb",
        provider_id="movie:157336",
        matched_title="Interstellar",
        matched_year="2014",
    )

    binding = repo.load("星际穿越", "2014")

    assert binding is not None
    assert binding.provider == "tmdb"
    assert binding.provider_id == "movie:157336"
    assert binding.matched_title == "Interstellar"
    assert binding.normalized_title == "星际穿越"
    assert binding.normalized_year == "2014"


def test_metadata_binding_repository_overwrites_existing_binding(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")

    repo.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")
    repo.save("深空彼岸", "2026", provider="local_douban", provider_id="35746415")

    binding = repo.load("深空彼岸", "2026")

    assert binding is not None
    assert binding.provider == "local_douban"
    assert binding.provider_id == "35746415"


def test_metadata_binding_repository_deletes_binding(tmp_path: Path) -> None:
    repo = MetadataBindingRepository(tmp_path / "app.db")
    repo.save("深空彼岸", "2026", provider="tmdb", provider_id="tv:42")

    repo.delete("深空彼岸", "2026")

    assert repo.load("深空彼岸", "2026") is None
