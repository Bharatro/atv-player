from __future__ import annotations

import logging


def configure_logging(level: str = "INFO", structured_handler: logging.Handler | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(console)

    if structured_handler is not None:
        structured_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        root.addHandler(structured_handler)
