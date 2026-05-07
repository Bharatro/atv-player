from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class KaraokeWord:
    text: str
    start_ms: int
    end_ms: int


@dataclass(slots=True)
class KaraokeLine:
    start_ms: int
    end_ms: int
    text: str
    translation: str = ""
    words: list[KaraokeWord] = field(default_factory=list)


@dataclass(slots=True)
class KaraokeDocument:
    source_format: str
    offset_ms: int = 0
    lines: list[KaraokeLine] = field(default_factory=list)
