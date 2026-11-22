"""Shared logging setup."""

from __future__ import annotations

import logging

from expenses.logging_setup import configure_logging


def test_http_libraries_do_not_log_request_urls_at_info():
    # Telegram request URLs contain the bot token; they must not be logged at INFO.
    configure_logging()
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)


def test_debug_level_keeps_http_libraries_quiet():
    configure_logging(logging.DEBUG)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
