from __future__ import annotations

from pathlib import Path
import types
import threading

from atv_player import crash_diagnostics


def test_install_crash_diagnostics_enables_faulthandler_and_creates_log_file(monkeypatch, tmp_path) -> None:
    enable_calls: list[tuple[object, bool]] = []

    def fake_enable(*, file, all_threads: bool) -> None:
        enable_calls.append((file, all_threads))

    monkeypatch.setattr(crash_diagnostics.faulthandler, "enable", fake_enable)
    monkeypatch.setattr(crash_diagnostics, "_crash_log_stream", None)
    monkeypatch.setattr(crash_diagnostics, "_crash_log_path", None)

    path = crash_diagnostics.install_crash_diagnostics(tmp_path)

    assert path == tmp_path / "fatal.log"
    assert path.exists()
    assert len(enable_calls) == 1
    assert Path(enable_calls[0][0].name) == path
    assert enable_calls[0][1] is True


def test_install_crash_diagnostics_logs_thread_and_unraisable_exceptions(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(crash_diagnostics.faulthandler, "enable", lambda **_kwargs: None)
    monkeypatch.setattr(crash_diagnostics, "_crash_log_stream", None)
    monkeypatch.setattr(crash_diagnostics, "_crash_log_path", None)

    path = crash_diagnostics.install_crash_diagnostics(tmp_path)
    thread_exception = RuntimeError("thread boom")
    unraisable_exception = ValueError("unraisable boom")

    threading.excepthook(
        types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=thread_exception,
            exc_traceback=None,
            thread=types.SimpleNamespace(name="worker-1"),
        )
    )
    crash_diagnostics.sys.unraisablehook(
        types.SimpleNamespace(
            exc_type=ValueError,
            exc_value=unraisable_exception,
            exc_traceback=None,
            err_msg="callback failed",
            object="metadata callback",
        )
    )

    text = path.read_text(encoding="utf-8")

    assert "Uncaught thread exception in worker-1" in text
    assert "thread boom" in text
    assert "Unraisable exception: callback failed" in text
    assert "metadata callback" in text
    assert "unraisable boom" in text
