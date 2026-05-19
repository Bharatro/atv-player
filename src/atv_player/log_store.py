from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import gzip
import json
import logging
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class AppLogEvent:
    timestamp: str
    level: str
    source: str
    category: str
    message: str
    module: str
    vod_id: str = ""
    vod_name: str = ""
    episode_title: str = ""
    session_id: str = ""
    url_summary: str = ""
    source_group_index: int = -1
    source_index: int = -1
    playlist_index: int = -1
    proxy_mode: str = ""
    exception: str = ""


@dataclass(frozen=True, slots=True)
class AppLogFilter:
    query: str = ""
    source: str = ""
    level: str = ""
    category: str = ""


class AppLogService:
    def __init__(
        self,
        logs_dir: Path,
        *,
        enabled_getter,
        max_bytes: int = 10 * 1024 * 1024,
        max_archives: int = 5,
    ) -> None:
        self._logs_dir = Path(logs_dir)
        self._enabled_getter = enabled_getter
        self._max_bytes = max_bytes
        self._max_archives = max_archives
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def active_path(self) -> Path:
        return self._logs_dir / "application.jsonl"

    def write_event(self, event: AppLogEvent) -> None:
        if not self._enabled_getter():
            return
        self._rotate_if_needed()
        with self.active_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def load_records(self, *, limit: int, log_filter: AppLogFilter) -> list[AppLogEvent]:
        records = [record for record in self._iter_records_newest_first() if self._matches(record, log_filter)]
        return records[:limit]

    def export_records(self, records: list[AppLogEvent], target_path: Path) -> None:
        lines: list[str] = []
        for record in records:
            parts = [
                f"[{record.timestamp}]",
                record.level,
                f"{record.source}/{record.category}",
                record.message,
            ]
            if record.vod_name:
                parts.append(f"vod={record.vod_name}")
            if record.episode_title:
                parts.append(f"episode={record.episode_title}")
            lines.append(" ".join(parts))
        target_path.write_text("\n".join(lines), encoding="utf-8")

    def clear(self) -> None:
        for path in self._logs_dir.glob("*"):
            if path.is_file():
                path.unlink()

    def _rotate_if_needed(self) -> None:
        if not self.active_path.exists():
            return
        if self.active_path.stat().st_size < self._max_bytes:
            return
        archive_path = self._logs_dir / f"application.{self._archive_timestamp()}.jsonl.gz"
        with self.active_path.open("rb") as source:
            with gzip.open(archive_path, "wb") as target:
                target.write(source.read())
        self.active_path.unlink()
        self._trim_archives()

    def _trim_archives(self) -> None:
        archives = sorted(self._logs_dir.glob("application.*.jsonl.gz"))
        while len(archives) > self._max_archives:
            oldest = archives.pop(0)
            oldest.unlink(missing_ok=True)

    def _iter_records_newest_first(self) -> list[AppLogEvent]:
        records: list[AppLogEvent] = []
        for path in sorted(self._logs_dir.glob("application.*.jsonl.gz"), reverse=True):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                records.extend(self._decode_lines(handle))
        if self.active_path.exists():
            with self.active_path.open("r", encoding="utf-8") as handle:
                records.extend(self._decode_lines(handle))
        records.sort(key=lambda record: record.timestamp, reverse=True)
        return records

    def _decode_lines(self, lines: Iterable[str]) -> list[AppLogEvent]:
        decoded: list[AppLogEvent] = []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            decoded.append(AppLogEvent(**json.loads(text)))
        return decoded

    def _matches(self, record: AppLogEvent, log_filter: AppLogFilter) -> bool:
        query = log_filter.query.strip().lower()
        if query:
            haystacks = [record.message, record.vod_name, record.episode_title]
            if not any(query in value.lower() for value in haystacks if value):
                return False
        if log_filter.source and record.source != log_filter.source:
            return False
        if log_filter.level and record.level != log_filter.level:
            return False
        if log_filter.category and record.category != log_filter.category:
            return False
        return True

    def _archive_timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


class StructuredJsonlHandler(logging.Handler):
    def __init__(self, service: AppLogService) -> None:
        super().__init__()
        self._service = service

    def emit(self, record: logging.LogRecord) -> None:
        event = AppLogEvent(
            timestamp=datetime.now().isoformat(timespec="milliseconds"),
            level=record.levelname,
            source=str(getattr(record, "log_source", "app") or "app"),
            category=str(getattr(record, "log_category", "app") or "app"),
            message=record.getMessage(),
            module=record.name,
            vod_id=str(getattr(record, "vod_id", "") or ""),
            vod_name=str(getattr(record, "vod_name", "") or ""),
            episode_title=str(getattr(record, "episode_title", "") or ""),
            session_id=str(getattr(record, "session_id", "") or ""),
            url_summary=str(getattr(record, "url_summary", "") or ""),
            source_group_index=int(getattr(record, "source_group_index", -1) or -1),
            source_index=int(getattr(record, "source_index", -1) or -1),
            playlist_index=int(getattr(record, "playlist_index", -1) or -1),
            proxy_mode=str(getattr(record, "proxy_mode", "") or ""),
            exception=self.formatException(record.exc_info) if record.exc_info else "",
        )
        self._service.write_event(event)
