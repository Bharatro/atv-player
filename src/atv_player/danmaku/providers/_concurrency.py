from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_SEGMENT_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class SettledResult(Generic[R]):
    value: R | None = None
    error: BaseException | None = None


def iter_bounded_settled(
    items: Iterable[T],
    worker: Callable[[T], R],
    *,
    max_workers: int = DEFAULT_SEGMENT_CONCURRENCY,
) -> Iterator[list[SettledResult[R]]]:
    rows = list(items)
    if not rows:
        return
    batch_size = max(1, max_workers)
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        with ThreadPoolExecutor(max_workers=min(batch_size, len(batch))) as executor:
            futures = [executor.submit(worker, row) for row in batch]
            settled: list[SettledResult[R]] = []
            for future in futures:
                try:
                    settled.append(SettledResult(value=future.result()))
                except BaseException as exc:
                    settled.append(SettledResult(error=exc))
            yield settled
