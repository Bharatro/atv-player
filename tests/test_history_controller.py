from atv_player.controllers.history_controller import HistoryController
from atv_player.models import HistoryRecord


class FakeRepository:
    def __init__(self, histories: list[HistoryRecord] | None = None) -> None:
        self.histories = list(histories or [])
        self.deleted: list[tuple[str, str, str]] = []
        self.pending_deletions: list[tuple[str, str, str, int]] = []

    def list_histories(self) -> list[HistoryRecord]:
        return list(self.histories)

    def delete_history(self, source_kind: str, vod_id: str, source_key: str = "") -> None:
        self.deleted.append((source_kind, vod_id, source_key))

    def record_pending_deletion(
        self, source_kind: str, source_key: str, vod_id: str, deleted_at: int
    ) -> None:
        self.pending_deletions.append((source_kind, source_key, vod_id, deleted_at))


def _record(
    *,
    key: str,
    name: str,
    create_time: int,
    source_kind: str = "telegram",
    source_key: str = "",
    position: int = 0,
    episode: int = 0,
) -> HistoryRecord:
    return HistoryRecord(
        id=0,
        key=key,
        vod_name=name,
        vod_pic="pic",
        vod_remarks=f"第{episode + 1}集",
        episode=episode,
        episode_url=f"{key}.m3u8",
        position=position,
        opening=0,
        ending=0,
        speed=1.0,
        create_time=create_time,
        source_kind=source_kind,
        source_key=source_key,
        source_name="",
    )


def test_load_page_returns_local_records_in_descending_time_order() -> None:
    repository = FakeRepository(
        histories=[
            _record(key="a", name="A", create_time=100),
            _record(key="b", name="B", create_time=300),
            _record(key="c", name="C", create_time=200),
        ]
    )
    controller = HistoryController(None, repository)

    records, total = controller.load_page(page=1, size=20)

    assert total == 3
    assert [record.key for record in records] == ["b", "c", "a"]


def test_load_page_paginates_local_records() -> None:
    repository = FakeRepository(
        histories=[_record(key=str(n), name=str(n), create_time=n) for n in range(5)]
    )
    controller = HistoryController(None, repository)

    records, total = controller.load_page(page=2, size=2)

    assert total == 5
    # create_time 4,3,2,1,0 desc → page 2 (offset 2) → 2,1
    assert [record.key for record in records] == ["2", "1"]


def test_load_page_filters_by_keyword_source_kind_and_continue_watching() -> None:
    repository = FakeRepository(
        histories=[
            _record(key="tg-1", name="心动信号", create_time=300, source_kind="telegram", position=0),
            _record(key="tg-2", name="心动信号 续", create_time=200, source_kind="telegram", position=5000),
            _record(key="bili-1", name="心动信号", create_time=100, source_kind="bilibili", position=3000),
        ]
    )
    controller = HistoryController(None, repository)

    # keyword + source_kind
    records, _ = controller.load_page(page=1, size=20, keyword="续", source_kind="telegram")
    assert [record.key for record in records] == ["tg-2"]

    # continue_watching keeps only entries with progress
    watching, _ = controller.load_page(page=1, size=20, continue_watching=True)
    assert {record.key for record in watching} == {"tg-2", "bili-1"}


def test_load_page_returns_empty_without_repository() -> None:
    controller = HistoryController(None)

    records, total = controller.load_page(page=1, size=20)

    assert records == []
    assert total == 0


def test_delete_one_delegates_to_repository() -> None:
    repository = FakeRepository()
    controller = HistoryController(None, repository)
    record = _record(key="detail-1", name="x", create_time=1, source_kind="spider_plugin", source_key="7")

    controller.delete_one(record)

    assert repository.deleted == [("spider_plugin", "detail-1", "7")]
    assert repository.pending_deletions == [("spider_plugin", "7", "detail-1", 1)]


def test_delete_many_and_clear_page_delegate_to_repository() -> None:
    repository = FakeRepository()
    controller = HistoryController(None, repository)
    records = [
        _record(key="emby-1", name="x", create_time=1, source_kind="emby"),
        _record(key="fn-1", name="y", create_time=2, source_kind="feiniu", source_key="fn"),
    ]

    controller.delete_many(records)
    controller.clear_page(records)

    assert repository.deleted == [
        ("emby", "emby-1", ""),
        ("feiniu", "fn-1", "fn"),
        ("emby", "emby-1", ""),
        ("feiniu", "fn-1", "fn"),
    ]
    assert repository.pending_deletions == [
        ("emby", "", "emby-1", 1),
        ("feiniu", "fn", "fn-1", 2),
        ("emby", "", "emby-1", 1),
        ("feiniu", "fn", "fn-1", 2),
    ]


def test_delete_is_noop_without_repository() -> None:
    controller = HistoryController(None)

    controller.delete_one(_record(key="a", name="a", create_time=1))
    controller.delete_many([_record(key="a", name="a", create_time=1)])
    controller.clear_page([_record(key="a", name="a", create_time=1)])
    # 无仓库时不抛异常即可。
