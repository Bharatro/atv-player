from __future__ import annotations

from datetime import datetime
import faulthandler
from pathlib import Path
import sys
import threading
import traceback

_crash_log_lock = threading.Lock()
_crash_log_path: Path | None = None
_crash_log_stream = None


def _write_header(line: str) -> None:
    stream = _crash_log_stream
    if stream is None:
        return
    with _crash_log_lock:
        stream.write(f"[{datetime.now().isoformat(timespec='seconds')}] {line}\n")
        stream.flush()


def _write_exception(header: str, exc_type, exc_value, exc_traceback) -> None:
    stream = _crash_log_stream
    if stream is None:
        return
    with _crash_log_lock:
        stream.write(f"[{datetime.now().isoformat(timespec='seconds')}] {header}\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=stream)
        stream.flush()


def _install_threading_hook() -> None:
    def handle_thread_exception(args) -> None:
        thread_name = getattr(getattr(args, "thread", None), "name", "") or "unknown-thread"
        _write_exception(
            f"Uncaught thread exception in {thread_name}",
            getattr(args, "exc_type", Exception),
            getattr(args, "exc_value", Exception("unknown thread exception")),
            getattr(args, "exc_traceback", None),
        )

    threading.excepthook = handle_thread_exception


def _install_unraisable_hook() -> None:
    def handle_unraisable(unraisable) -> None:
        err_msg = str(getattr(unraisable, "err_msg", "") or "").strip() or "no message"
        obj_repr = repr(getattr(unraisable, "object", None))
        _write_header(f"Unraisable exception: {err_msg} object={obj_repr}")
        _write_exception(
            "Unraisable traceback",
            getattr(unraisable, "exc_type", Exception),
            getattr(unraisable, "exc_value", Exception("unknown unraisable exception")),
            getattr(unraisable, "exc_traceback", None),
        )

    sys.unraisablehook = handle_unraisable


def install_crash_diagnostics(logs_dir: Path) -> Path:
    global _crash_log_path, _crash_log_stream

    resolved_dir = Path(logs_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    path = resolved_dir / "fatal.log"
    if _crash_log_stream is not None and _crash_log_path != path:
        try:
            _crash_log_stream.close()
        except Exception:
            pass
        _crash_log_stream = None
    if _crash_log_stream is None:
        _crash_log_stream = path.open("a", encoding="utf-8", buffering=1)
        _crash_log_path = path
    faulthandler.enable(file=_crash_log_stream, all_threads=True)
    _install_threading_hook()
    _install_unraisable_hook()
    _write_header("Crash diagnostics installed")
    return path
