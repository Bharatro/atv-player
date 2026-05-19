import threading
import time

from atv_player.danmaku.providers._concurrency import iter_bounded_settled


def test_iter_bounded_settled_preserves_batch_shape_for_sync_worker() -> None:
    rows = [1, 2, 3, 4, 5]

    batches = list(iter_bounded_settled(rows, lambda value: value * 10, max_workers=2))

    assert [[item.value for item in batch] for batch in batches] == [
        [10, 20],
        [30, 40],
        [50],
    ]


def test_iter_bounded_settled_limits_sync_worker_concurrency() -> None:
    state = {"active": 0, "max_active": 0}
    lock = threading.Lock()

    def worker(value: int) -> int:
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return value

    list(iter_bounded_settled([1, 2, 3, 4, 5], worker, max_workers=3))

    assert state["max_active"] == 3


def test_iter_bounded_settled_collects_async_worker_errors() -> None:
    async def worker(value: int) -> int:
        if value == 2:
            raise RuntimeError("boom")
        return value * 100

    batches = list(iter_bounded_settled([1, 2, 3], worker, max_workers=2))

    assert batches[0][0].value == 100
    assert isinstance(batches[0][1].error, RuntimeError)
    assert batches[1][0].value == 300


def test_iter_bounded_settled_can_stop_before_starting_later_batches() -> None:
    started: list[int] = []

    def worker(value: int) -> int:
        started.append(value)
        return value

    iterator = iter_bounded_settled([1, 2, 3, 4, 5], worker, max_workers=2)

    first_batch = next(iterator)

    assert [item.value for item in first_batch] == [1, 2]
    assert sorted(started) == [1, 2]
