from __future__ import annotations

import logging

from atv_player.logging_utils import configure_logging


def test_configure_logging_demotes_httpx_request_noise() -> None:
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    httpx_original_level = httpx_logger.level
    httpcore_original_level = httpcore_logger.level

    try:
        configure_logging("INFO")

        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING
    finally:
        httpx_logger.setLevel(httpx_original_level)
        httpcore_logger.setLevel(httpcore_original_level)

