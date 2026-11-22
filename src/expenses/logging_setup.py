"""Shared logging setup for every ``expenses-*`` entry point."""

from __future__ import annotations

import logging

# httpx/httpcore log every request URL at INFO. Telegram puts the bot token in the URL
# (https://api.telegram.org/bot<token>/...), so at INFO the token would end up in the
# logs — and Telegram long polling would add a line every ~10 s. Warnings and errors
# from these libraries still come through.
_QUIET_LIBRARIES = ("httpx", "httpcore")


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    for name in _QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))
