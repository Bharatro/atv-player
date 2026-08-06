import json
from pathlib import Path
import threading

from atv_player.danmaku.models import DanmakuSeriesPreference
from atv_player.danmaku.preferences import (
    DanmakuSeriesPreferenceStore,
    build_danmaku_episode_key,
)
from atv_player.models import PlayItem


def test_preference_store_round_trip(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")
    pref = DanmakuSeriesPreference(
        series_key="jianlai",
        provider="tencent",
        page_url="https://v.qq.com/x/cover/demo.html",
        title="剑来 第12集",
        updated_at=1770000000,
    )

    store.save(pref)

    loaded = store.load("jianlai")

    assert loaded == pref


def test_preference_store_overwrites_existing_series_key(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")
    store.save(
        DanmakuSeriesPreference(
            series_key="jianlai",
            provider="youku",
            page_url="https://v.youku.com/v_show/id_old.html",
            title="旧结果",
            updated_at=1,
        )
    )

    store.save(
        DanmakuSeriesPreference(
            series_key="jianlai",
            provider="tencent",
            page_url="https://v.qq.com/x/cover/demo.html",
            title="新结果",
            updated_at=2,
        )
    )

    loaded = store.load("jianlai")

    assert loaded is not None
    assert loaded.provider == "tencent"
    assert loaded.page_url.endswith("demo.html")
    assert store.load("missing") is None


def test_preference_store_reads_missing_search_title_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "danmaku-series.json"
    path.write_text(
        json.dumps(
            {
                "jianlai": {
                    "provider": "tencent",
                    "page_url": "https://v.qq.com/x/cover/demo.html",
                    "title": "剑来 第12集",
                    "updated_at": 1770000000,
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = DanmakuSeriesPreferenceStore(path).load("jianlai")

    assert loaded is not None
    assert loaded.search_title == ""


def test_preference_store_round_trip_preserves_search_title(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")
    pref = DanmakuSeriesPreference(
        series_key="jianlai",
        provider="tencent",
        page_url="https://v.qq.com/x/cover/demo.html",
        title="剑来 第12集",
        search_title="剑来",
        updated_at=1770000000,
    )

    store.save(pref)

    loaded = store.load("jianlai")
    payload = json.loads((tmp_path / "danmaku-series.json").read_text(encoding="utf-8"))

    assert loaded == pref
    assert payload["jianlai"]["search_title"] == "剑来"


def test_preference_store_isolates_episode_provider_offsets(tmp_path: Path) -> None:
    store = DanmakuSeriesPreferenceStore(tmp_path / "danmaku-series.json")

    store.save_offset("jianlai", "episode:12", "tencent", -3.0)
    store.save_offset("jianlai", "episode:12", "bilibili", 1.5)
    store.save_offset("jianlai", "episode:13", "tencent", 2.0)

    assert store.load_offset("jianlai", "episode:12", "tencent") == -3.0
    assert store.load_offset("jianlai", "episode:12", "bilibili") == 1.5
    assert store.load_offset("jianlai", "episode:13", "tencent") == 2.0


def test_preference_store_zero_removes_offset_and_reads_old_json(tmp_path: Path) -> None:
    path = tmp_path / "danmaku-series.json"
    path.write_text(
        '{"jianlai":{"provider":"tencent","page_url":"u","title":"t","updated_at":1}}',
        encoding="utf-8",
    )
    store = DanmakuSeriesPreferenceStore(path)

    assert store.load_offset("jianlai", "episode:12", "tencent") == 0.0
    store.save_offset("jianlai", "episode:12", "tencent", 4.0)
    store.save_offset("jianlai", "episode:12", "tencent", 0.0)

    assert store.load_offset("jianlai", "episode:12", "tencent") == 0.0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["jianlai"]["provider"] == "tencent"
    assert payload["jianlai"].get("episode_source_offsets", {}) == {}


def test_preference_store_ignores_invalid_persisted_offsets(tmp_path: Path) -> None:
    path = tmp_path / "danmaku-series.json"
    path.write_text(
        json.dumps(
            {
                "jianlai": {
                    "provider": "tencent",
                    "page_url": "u",
                    "title": "t",
                    "episode_source_offsets": {
                        "episode:12": {
                            "tencent": "nan",
                            "bilibili": 601,
                            "iqiyi": 2.5,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    store = DanmakuSeriesPreferenceStore(path)

    assert store.load_offset("jianlai", "episode:12", "tencent") == 0.0
    assert store.load_offset("jianlai", "episode:12", "bilibili") == 0.0
    assert store.load_offset("jianlai", "episode:12", "iqiyi") == 2.5


def test_preference_store_concurrent_offset_saves_keep_both_providers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "danmaku-series.json"
    store = DanmakuSeriesPreferenceStore(path)
    barrier = threading.Barrier(3)

    def save(provider: str, value: float) -> None:
        barrier.wait()
        store.save_offset("jianlai", "episode:12", provider, value)

    threads = [
        threading.Thread(target=save, args=("tencent", -2.0)),
        threading.Thread(target=save, args=("bilibili", 1.5)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["jianlai"]["episode_source_offsets"]["episode:12"] == {
        "bilibili": 1.5,
        "tencent": -2.0,
    }


def test_build_danmaku_episode_key_prefers_inferred_playlist_episode() -> None:
    first = PlayItem(title="第11集", url="")
    current = PlayItem(title="第12集", url="")

    assert build_danmaku_episode_key(current, [first, current]) == "episode:12"


def test_build_danmaku_episode_key_uses_normalized_search_label() -> None:
    item = PlayItem(
        title="片头曲",
        url="",
        danmaku_search_episode="  Special Episode  ",
    )

    assert build_danmaku_episode_key(item) == "label:specialepisode"


def test_build_danmaku_episode_key_uses_stable_item_digest() -> None:
    item = PlayItem(
        title="1080p.mkv",
        url="",
        vod_id="stable-item-id",
    )

    assert build_danmaku_episode_key(item) == build_danmaku_episode_key(item)
    assert build_danmaku_episode_key(item).startswith("item:")


def test_build_danmaku_episode_key_falls_back_to_single() -> None:
    item = PlayItem(title="片头曲", url="")

    assert build_danmaku_episode_key(item) == "single"
