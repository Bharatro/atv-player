from atv_player.app import AppCoordinator, build_application
from atv_player.logging_utils import configure_logging


def main() -> int:
    configure_logging("INFO")
    app, repo, app_log_service = build_application()
    coordinator = AppCoordinator(repo, app_log_service=app_log_service)
    widget = coordinator.start()
    widget.show()
    try:
        return app.exec()
    finally:
        coordinator.close()


if __name__ == "__main__":
    raise SystemExit(main())
