from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class ResolveCacheValue:
    url: str
    headers: dict[str, str]


@dataclass(slots=True)
class _ResolveCacheEntry:
    value: ResolveCacheValue
    expires_at: float


class PlaybackResolveCache:
    def __init__(self, ttl_seconds: float = 300.0, now: Callable[[], float] = monotonic) -> None:
        self._ttl_seconds = float(ttl_seconds)
        self._now = now
        self._entries: dict[tuple[str, str, str], _ResolveCacheEntry] = {}

    def _key(self, *, flag: str, url: str, parser_key: str) -> tuple[str, str, str]:
        return (flag.strip(), url.strip(), parser_key.strip())

    def get(self, *, flag: str, url: str, parser_key: str) -> ResolveCacheValue | None:
        key = self._key(flag=flag, url=url, parser_key=parser_key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._entries.pop(key, None)
            return None
        return entry.value

    def put(self, *, flag: str, url: str, parser_key: str, value: ResolveCacheValue) -> None:
        key = self._key(flag=flag, url=url, parser_key=parser_key)
        self._entries[key] = _ResolveCacheEntry(
            value=value,
            expires_at=self._now() + self._ttl_seconds,
        )
