from atv_player.models import PlayItem
from atv_player.playlist_sorting import (
    NAME_ASC,
    NAME_DESC,
    ORIGINAL,
    RATING_ASC,
    RATING_DESC,
    SIZE_ASC,
    SIZE_DESC,
    TIME_ASC,
    TIME_DESC,
    PlaylistSortState,
    find_playlist_item_index,
)


def _item(name: str, **kwargs) -> PlayItem:
    return PlayItem(
        title=name,
        original_title=name,
        url=f"https://media/{name}",
        **kwargs,
    )


def test_playlist_sort_options_follow_available_fields() -> None:
    playlist = [
        _item("Episode 10.mkv", size=100, rating=8.0, time="2026-07-23T10:00:00+08:00"),
        _item("Episode 2.mkv", size=50, rating=9.0, time="2026-07-22T10:00:00+08:00"),
    ]
    state = PlaylistSortState()

    assert [option.value for option in state.options_for(playlist)] == [
        ORIGINAL,
        NAME_ASC,
        NAME_DESC,
        "size,asc",
        "size,desc",
        "rating,asc",
        "rating,desc",
        "time,asc",
        "time,desc",
    ]


def test_playlist_name_sort_is_natural_and_uses_original_filename() -> None:
    playlist = [
        PlayItem(title="第10集", original_title="Episode 10.mkv", url="10"),
        PlayItem(title="第2集", original_title="Episode 2.mkv", url="2"),
        PlayItem(title="第1集", original_title="episode 1.mkv", url="1"),
    ]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, NAME_ASC)
    assert [item.url for item in playlist] == ["1", "2", "10"]

    state.apply(playlist, NAME_DESC)
    assert [item.url for item in playlist] == ["10", "2", "1"]


def test_playlist_numeric_sort_keeps_missing_values_last_and_ties_stable() -> None:
    first = _item("first", rating=8.0)
    missing = _item("missing")
    second = _item("second", rating=8.0)
    high = _item("high", rating=9.0)
    playlist = [first, missing, second, high]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, RATING_ASC)
    assert playlist == [first, second, high, missing]

    state.apply(playlist, RATING_DESC)
    assert playlist == [high, first, second, missing]


def test_playlist_size_and_time_sort_in_both_directions() -> None:
    old_large = _item("old-large", size=300, time="2026-07-21T10:00:00+08:00")
    new_small = _item("new-small", size=100, time="2026-07-23T10:00:00+08:00")
    middle = _item("middle", size=200, time="2026-07-22T10:00:00+08:00")
    playlist = [old_large, new_small, middle]
    state = PlaylistSortState()
    state.reset([playlist])

    state.apply(playlist, SIZE_ASC)
    assert playlist == [new_small, middle, old_large]
    state.apply(playlist, SIZE_DESC)
    assert playlist == [old_large, middle, new_small]
    state.apply(playlist, TIME_ASC)
    assert playlist == [old_large, middle, new_small]
    state.apply(playlist, TIME_DESC)
    assert playlist == [new_small, middle, old_large]


def test_playlist_sort_restores_each_lists_original_order() -> None:
    first = [_item("b"), _item("a")]
    second = [_item("d"), _item("c")]
    state = PlaylistSortState()
    state.reset([first, second])

    state.apply(first, NAME_ASC)
    state.apply(second, NAME_ASC)
    state.apply(first, ORIGINAL)
    state.apply(second, ORIGINAL)

    assert [item.original_title for item in first] == ["b", "a"]
    assert [item.original_title for item in second] == ["d", "c"]


def test_playlist_sort_inherits_original_order_after_item_preserving_rebuild() -> None:
    first = _item("Episode 2.mkv")
    second = _item("Episode 1.mkv")
    playlist = [first, second]
    rebuilt = [second, first]
    state = PlaylistSortState()
    state.reset([playlist])

    state.inherit_original_order(playlist, rebuilt)
    state.apply(rebuilt, ORIGINAL)

    assert rebuilt == [first, second]


def test_find_playlist_item_index_prefers_object_then_stable_fields() -> None:
    current = PlayItem(
        title="Episode",
        url="https://media/2",
        vod_id="v2",
        path="/2.mkv",
    )
    playlist = [_item("one"), current]
    assert find_playlist_item_index(playlist, current, 0) == 1

    replacement = PlayItem(
        title="Renamed",
        url="https://new/2",
        vod_id="v2",
        path="/new.mkv",
    )
    assert find_playlist_item_index([_item("one"), replacement], current, 0) == 1
