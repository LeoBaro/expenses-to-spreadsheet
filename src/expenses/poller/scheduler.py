"""Interval scheduler for poll cycles (TR-1 DD-1).

A single asyncio task runs one cycle at a time; the next cycle only starts after
the previous one finishes plus the configured interval, so cycles never overlap.
A cycle raising is logged and does not stop the loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class IntervalScheduler:
    def __init__(self, cycle: Callable[[], Awaitable[object]], interval_seconds: float) -> None:
        self._cycle = cycle
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._cycle()
            except Exception:  # noqa: BLE001 - a cycle failure must not kill the loop
                logger.exception("poll cycle failed; continuing")
            # Interruptible sleep: wakes immediately on stop().
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval_seconds)
            except asyncio.TimeoutError:
                pass

    def start(self) -> asyncio.Task:
        if self._task is not None:
            raise RuntimeError("scheduler already started")
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
