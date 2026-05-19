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
    batch_size = max(1, max_workers)
    for start in range(0, len(rows), batch_size):
        yield asyncio.run(
            _settle_batch_async(
                rows[start : start + batch_size],
                worker,
            )
        )


async def _run_worker(
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
    row: T,
) -> R:
    if inspect.iscoroutinefunction(worker):
        return await worker(row)
    return await asyncio.to_thread(worker, row)


async def _settle_batch_async(
    items: list[T],
    worker: Callable[[T], R] | Callable[[T], Awaitable[R]],
) -> list[SettledResult[R]]:
    async def run_one(row: T) -> SettledResult[R]:
        try:
            return SettledResult(value=await _run_worker(worker, row))
        except BaseException as exc:
            return SettledResult(error=exc)

    return list(await asyncio.gather(*(run_one(row) for row in items)))
