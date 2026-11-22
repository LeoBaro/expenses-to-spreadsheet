"""FastAPI application factory + lifespan (TR-0).

The Composition Root runs inside the FastAPI ``lifespan``: build the object graph on
startup, trigger the initial actions (state load FR-13, cache build FR-14, start the
poll scheduler FR-1, start Telegram long polling), and tear everything down in reverse
on shutdown. The HTTP surface is intentionally tiny — just ``/health``; the real work
happens on the internal scheduler.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import FastAPI
from telegram.error import NetworkError, TelegramError

from expenses.bootstrap.composition import Components, build_components
from expenses.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Waits between attempts to reach Telegram at startup (~1.5 min in total). A network
# blip right after the container starts (seen on the Pi's Wi-Fi) is retried instead of
# failing startup; if Telegram stays unreachable, startup fails and Docker restarts
# the container, as before.
TELEGRAM_STARTUP_DELAYS: tuple[float, ...] = (2, 4, 8, 15, 30, 30)
# Same idea for PTB's own bootstrap step inside start_polling (deleteWebhook).
TELEGRAM_BOOTSTRAP_RETRIES = 5


async def retry_on_network_error(
    action: Callable[[], Awaitable[T]],
    *,
    what: str,
    delays: Sequence[float] = TELEGRAM_STARTUP_DELAYS,
    sleep: Callable[[float], Awaitable[object]] | None = None,
) -> T:
    """Run ``action``, retrying after each delay while it raises a Telegram
    ``NetworkError`` (connection problems, timeouts). Any other error — e.g. an invalid
    token — is raised immediately, and so is the last network error."""
    sleep = sleep or asyncio.sleep  # looked up at call time (patchable in tests)
    for attempt, delay in enumerate([*delays, None], start=1):
        try:
            return await action()
        except NetworkError as exc:
            if delay is None:
                raise
            # The message never contains the token; don't log the traceback.
            logger.warning(
                "%s: network error (attempt %d): %s — retrying in %ss", what, attempt, exc, delay
            )
            await sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def log_polling_error(error: TelegramError) -> None:
    """PTB error_callback for get_updates: PTB retries by itself, so a network blip is
    one warning line instead of a full traceback. Anything else (e.g. a Conflict from a
    second instance using the same token) stays an error."""
    if isinstance(error, NetworkError):
        logger.warning("Telegram polling: network error, retrying: %s", error)
    else:
        logger.error("Telegram polling error: %s", error)


async def _start_bot(components: Components) -> None:
    """Run PTB inside the existing FastAPI event loop (not run_polling, which owns
    its own loop). initialize → start → start_polling; reversed on shutdown."""
    if components.bot is None:
        return
    app = components.bot.application
    await retry_on_network_error(app.initialize, what="Telegram startup")
    await app.start()
    await app.updater.start_polling(
        bootstrap_retries=TELEGRAM_BOOTSTRAP_RETRIES,
        error_callback=log_polling_error,
    )
    logger.info("Telegram long polling started")


async def _stop_bot(components: Components) -> None:
    if components.bot is None:
        return
    app = components.bot.application
    if app.updater is not None:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("Telegram bot stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    components = build_components(settings)
    app.state.components = components

    components.state.load()  # FR-13: replay processed ids before any polling
    await components.cache.refresh()  # FR-14: initial cache build from the spreadsheet
    await _start_bot(components)
    components.scheduler.start()  # FR-1: internal poll loop
    logger.info(
        "startup complete: polling every %ss (lookback %sd)",
        settings.poll_interval_seconds,
        settings.poll_lookback_days,
    )

    try:
        yield
    finally:
        await components.scheduler.stop()
        await _stop_bot(components)
        await components.http_client.aclose()
        logger.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title="Expenses to Spreadsheet", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, object]:
        components: Components = app.state.components
        snapshot = components.cache.snapshot
        return {
            "status": "ok",
            "category_rows": len(snapshot.entries),
            "ignore_patterns": len(snapshot.ignore_patterns),
            "telegram": components.bot is not None,
        }

    return app
