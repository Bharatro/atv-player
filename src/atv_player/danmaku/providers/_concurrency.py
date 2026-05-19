from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterable, Iterator
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
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    *,
    max_workers: int = DEFAULT_SEGMENT_CONCURRENCY,
) -> Iterator[list[SettledResult[R]]]:
    rows = list(items)
    if not rows:
        return
    for batch in asyncio.run(
        _iter_bounded_settled_async(rows, worker, max_workers=max_workers)
    ):
        yield batch


async def _run_worker(
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    row: T,
) -> R:
    if inspect.iscoroutinefunction(worker):
        return await worker(row)
    return await asyncio.to_thread(worker, row)


async def _iter_bounded_settled_async(
    items: list[T],
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    *,
    max_workers: int,
) -> list[list[SettledResult[R]]]:
    semaphore = asyncio.Semaphore(max(1, max_workers))

    async def run_one(row: T) -> SettledResult[R]:
        async with semaphore:
            try:
                return SettledResult(value=await _run_worker(worker, row))
            except BaseException as exc:
                return SettledResult(error=exc)

    settled_rows = list(await asyncio.gather(*(run_one(row) for row in items)))
    batch_size = max(1, max_workers)
    return [
        settled_rows[start : start + batch_size]
        for start in range(0, len(settled_rows), batch_size)
    ]
