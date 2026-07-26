"""Scheduler tests (TR-1 DD-1): interval behaviour, non-overlap, error resilience."""

from __future__ import annotations

import asyncio

from expenses.poller.scheduler import IntervalScheduler


async def test_runs_cycles_until_stopped():
    calls = 0

    async def cycle():
        nonlocal calls
        calls += 1

    scheduler = IntervalScheduler(cycle, interval_seconds=0.01)
    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert calls >= 2


async def test_cycles_do_not_overlap():
    concurrent = 0
    max_concurrent = 0

    async def cycle():
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await asyncio.sleep(0.02)
        concurrent -= 1

    scheduler = IntervalScheduler(cycle, interval_seconds=0.0)
    scheduler.start()
    await asyncio.sleep(0.1)
    await scheduler.stop()

    assert max_concurrent == 1


async def test_cycle_failure_does_not_stop_loop():
    calls = 0

    async def cycle():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    scheduler = IntervalScheduler(cycle, interval_seconds=0.01)
    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert calls >= 2  # kept going despite raising every time
