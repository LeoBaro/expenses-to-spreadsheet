"""FastAPI application factory + lifespan (TR-0).

The Composition Root runs inside the FastAPI ``lifespan``: build the object graph on
startup, trigger the initial actions (state load FR-13, cache build FR-14, start the
poll scheduler FR-1, start Telegram long polling), and tear everything down in reverse
on shutdown. The HTTP surface is intentionally tiny — just ``/health``; the real work
happens on the internal scheduler.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from expenses.bootstrap.composition import Components, build_components
from expenses.config import Settings

logger = logging.getLogger(__name__)


async def _start_bot(components: Components) -> None:
    """Run PTB inside the existing FastAPI event loop (not run_polling, which owns
    its own loop). initialize → start → start_polling; reversed on shutdown."""
    if components.bot is None:
        return
    app = components.bot.application
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
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
