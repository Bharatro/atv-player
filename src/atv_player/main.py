from __future__ import annotations

import cProfile
from collections.abc import Callable
import os
from pathlib import Path

from atv_player.app import AppCoordinator, build_application
from atv_player.logging_utils import configure_logging


def _profile_mode() -> str | None:
    mode = os.environ.get("ATV_PROFILE", "").strip().lower()
    return mode or None


def _profile_output_path() -> Path:
    output = os.environ.get("ATV_PROFILE_OUTPUT", "").strip()
    return Path(output) if output else Path.cwd() / "atv-player-profile.prof"


def _dump_profile(profiler: cProfile.Profile) -> None:
    profiler.dump_stats(_profile_output_path())


def _run_with_profile(profile_mode: str | None, runner: Callable[[], int]) -> int:
    if profile_mode is None:
        return runner()
    profiler = cProfile.Profile()
    result = profiler.runcall(runner)
    _dump_profile(profiler)
    return result


def _build_and_show() -> tuple[object, object]:
    app, repo, app_log_service = build_application()
    coordinator = AppCoordinator(repo, app_log_service=app_log_service)
    widget = coordinator.start()
    widget.show()
    return app, coordinator


def main() -> int:
    configure_logging("INFO")
    profile_mode = _profile_mode()

    if profile_mode == "startup":
        profiler = cProfile.Profile()
        app, coordinator = profiler.runcall(_build_and_show)
        _dump_profile(profiler)
        try:
            return app.exec()
        finally:
            coordinator.close()

    app, coordinator = _build_and_show()

    if profile_mode == "runtime":
        def runner() -> int:
            try:
                return app.exec()
            finally:
                coordinator.close()

        return _run_with_profile(profile_mode, runner)

    try:
        return app.exec()
    finally:
        coordinator.close()


if __name__ == "__main__":
    raise SystemExit(main())
