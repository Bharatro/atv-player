import pstats

from atv_player.main import main


def test_main_configures_logging_before_start(monkeypatch) -> None:
    configured_levels: list[str] = []
    closed = {"called": False}
    captured = {"service": None}

    monkeypatch.setattr("atv_player.main.configure_logging", configured_levels.append, raising=False)

    class DummyApp:
        def exec(self) -> int:
            return 0

    class DummyWidget:
        def show(self) -> None:
            return None

    class DummyCoordinator:
        def __init__(self, repo, *, app_log_service=None) -> None:
            self.repo = repo
            captured["service"] = app_log_service

        def start(self):
            return DummyWidget()

        def close(self) -> None:
            closed["called"] = True

    service = object()
    monkeypatch.setattr("atv_player.main.build_application", lambda: (DummyApp(), object(), service))
    monkeypatch.setattr("atv_player.main.AppCoordinator", DummyCoordinator)

    assert main() == 0
    assert configured_levels == ["INFO"]
    assert captured["service"] is service
    assert closed["called"] is True


def test_main_writes_profile_output_when_atv_profile_is_enabled(monkeypatch, tmp_path) -> None:
    profile_output = tmp_path / "profile.prof"
    monkeypatch.setenv("ATV_PROFILE", "runtime")
    monkeypatch.setenv("ATV_PROFILE_OUTPUT", str(profile_output))

    closed = {"called": False}

    class DummyApp:
        def exec(self) -> int:
            return 0

    class DummyWidget:
        def show(self) -> None:
            return None

    class DummyCoordinator:
        def __init__(self, repo, *, app_log_service=None) -> None:
            del repo, app_log_service

        def start(self):
            return DummyWidget()

        def close(self) -> None:
            closed["called"] = True

    monkeypatch.setattr("atv_player.main.build_application", lambda: (DummyApp(), object(), object()))
    monkeypatch.setattr("atv_player.main.AppCoordinator", DummyCoordinator)

    assert main() == 0
    assert profile_output.exists()
    assert profile_output.stat().st_size > 0
    assert closed["called"] is True


def test_main_profiles_startup_initialization_when_requested(monkeypatch, tmp_path) -> None:
    profile_output = tmp_path / "startup.prof"
    monkeypatch.setenv("ATV_PROFILE", "startup")
    monkeypatch.setenv("ATV_PROFILE_OUTPUT", str(profile_output))

    closed = {"called": False}
    build_calls: list[str] = []

    class DummyApp:
        def exec(self) -> int:
            return 0

    class DummyWidget:
        def show(self) -> None:
            return None

    class DummyCoordinator:
        def __init__(self, repo, *, app_log_service=None) -> None:
            del repo, app_log_service

        def start(self):
            return DummyWidget()

        def close(self) -> None:
            closed["called"] = True

    def build_application() -> tuple[DummyApp, object, object]:
        build_calls.append("called")
        return DummyApp(), object(), object()

    monkeypatch.setattr("atv_player.main.build_application", build_application)
    monkeypatch.setattr("atv_player.main.AppCoordinator", DummyCoordinator)

    assert main() == 0
    assert build_calls == ["called"]
    assert profile_output.exists()
    assert profile_output.stat().st_size > 0
    stats = pstats.Stats(str(profile_output))
    profiled_functions = {func_name for _, _, func_name in stats.stats}
    assert "build_application" in profiled_functions
    assert closed["called"] is True
