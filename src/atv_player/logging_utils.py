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

    # These libraries emit one INFO log per request, which is too noisy for
    # the structured app log and can add significant synchronous file I/O
    # during HLS playback.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
