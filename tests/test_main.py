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
