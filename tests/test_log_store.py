from __future__ import annotations

import logging
from pathlib import Path

from atv_player.log_store import AppLogEvent, AppLogFilter, AppLogService, StructuredJsonlHandler


def test_app_log_service_writes_jsonl_record(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=10_000_000, max_archives=5)

    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:00.000",
            level="INFO",
            source="app",
            category="app",
            message="Application initialized",
            module="atv_player.app",
        )
    )

    active_path = tmp_path / "logs" / "application.jsonl"

    assert active_path.exists()
    assert '"message": "Application initialized"' in active_path.read_text(encoding="utf-8")


def test_app_log_service_rotates_and_compresses_after_size_limit(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=180, max_archives=5)

    for index in range(8):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:0{index}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"event-{index}-" + ("x" * 40),
                module="atv_player.app",
            )
        )

    archives = sorted((tmp_path / "logs").glob("application.*.jsonl.gz"))

    assert archives


def test_app_log_service_keeps_only_five_archives(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=160, max_archives=5)

    for index in range(40):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:{index:02d}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"rotation-{index}-" + ("y" * 40),
                module="atv_player.app",
            )
        )

    assert len(list((tmp_path / "logs").glob("application.*.jsonl.gz"))) == 5


def test_app_log_service_reads_filters_and_exports_records(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=10_000_000, max_archives=5)
    export_path = tmp_path / "filtered.log"

    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:00.000",
            level="ERROR",
            source="playback",
            category="player",
            message="播放失败: boom",
            module="atv_player.ui.player_window",
            vod_name="测试剧",
            episode_title="第1集",
        )
    )
    service.write_event(
        AppLogEvent(
            timestamp="2026-05-19T12:00:01.000",
            level="INFO",
            source="app",
            category="network",
            message="Proxy prepared",
            module="atv_player.proxy.server",
        )
    )

    records = service.load_records(
        limit=2000,
        log_filter=AppLogFilter(query="测试剧", source="playback", level="ERROR"),
    )

    assert [record.message for record in records] == ["播放失败: boom"]

    service.export_records(records, export_path)

    exported = export_path.read_text(encoding="utf-8")
    assert "播放失败: boom" in exported
    assert "测试剧" in exported


def test_app_log_service_clear_removes_active_and_archives(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=160, max_archives=5)

    for index in range(30):
        service.write_event(
            AppLogEvent(
                timestamp=f"2026-05-19T12:00:{index:02d}.000",
                level="INFO",
                source="app",
                category="app",
                message=f"clear-{index}-" + ("z" * 40),
                module="atv_player.app",
            )
        )

    service.clear()

    assert list((tmp_path / "logs").glob("*")) == []


def test_structured_handler_noops_when_logging_disabled(tmp_path: Path) -> None:
    enabled = {"value": False}
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: enabled["value"], max_bytes=10_000_000, max_archives=5)
    handler = StructuredJsonlHandler(service)
    logger = logging.getLogger("test_structured_handler_noops_when_logging_disabled")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("disabled")

    assert not (tmp_path / "logs" / "application.jsonl").exists()


def test_structured_handler_persists_exception_text(tmp_path: Path) -> None:
    service = AppLogService(tmp_path / "logs", enabled_getter=lambda: True, max_bytes=10_000_000, max_archives=5)
    handler = StructuredJsonlHandler(service)
    logger = logging.getLogger("test_structured_handler_persists_exception_text")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.exception("failed")

    records = service.load_records(limit=10, log_filter=AppLogFilter())

    assert len(records) == 1
    assert records[0].message == "failed"
    assert "RuntimeError: boom" in records[0].exception
