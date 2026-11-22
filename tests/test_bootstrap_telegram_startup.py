"""Telegram startup resilience (TR-0): network blips at startup are retried."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from telegram.error import Conflict, InvalidToken, NetworkError, TimedOut

from expenses.bootstrap.app import _start_bot, log_polling_error, retry_on_network_error


class _Flaky:
    """An async action that fails with the given errors, then returns "ok"."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def _recording_sleep():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    return slept, sleep


async def test_retries_network_errors_until_success():
    action = _Flaky(NetworkError("httpx.ConnectError: "), TimedOut())
    slept, sleep = _recording_sleep()

    result = await retry_on_network_error(action, what="t", delays=(2, 4, 8), sleep=sleep)

    assert result == "ok" and action.calls == 3
    assert slept == [2, 4]


async def test_gives_up_after_the_last_delay():
    action = _Flaky(*[NetworkError("down")] * 5)
    slept, sleep = _recording_sleep()

    with pytest.raises(NetworkError):
        await retry_on_network_error(action, what="t", delays=(1, 1), sleep=sleep)
    assert action.calls == 3  # first try + one per delay
    assert slept == [1, 1]


async def test_invalid_token_is_not_retried():
    action = _Flaky(InvalidToken())
    slept, sleep = _recording_sleep()

    with pytest.raises(InvalidToken):
        await retry_on_network_error(action, what="t", delays=(1, 1), sleep=sleep)
    assert action.calls == 1 and slept == []


async def test_start_bot_retries_initialize_and_configures_polling(monkeypatch):
    slept, sleep = _recording_sleep()
    monkeypatch.setattr("expenses.bootstrap.app.asyncio.sleep", sleep)
    initialize = _Flaky(NetworkError("httpx.ConnectError: "))
    polling_kwargs = {}

    async def start():
        pass

    async def start_polling(**kwargs):
        polling_kwargs.update(kwargs)

    application = SimpleNamespace(
        initialize=initialize, start=start, updater=SimpleNamespace(start_polling=start_polling)
    )
    components = SimpleNamespace(bot=SimpleNamespace(application=application))

    await _start_bot(components)

    assert initialize.calls == 2 and slept == [2]
    assert polling_kwargs["bootstrap_retries"] > 0
    assert polling_kwargs["error_callback"] is log_polling_error


def test_polling_network_error_is_a_warning_and_conflict_an_error(caplog):
    with caplog.at_level(logging.WARNING, logger="expenses.bootstrap.app"):
        log_polling_error(NetworkError("httpx.ConnectError: "))
        log_polling_error(Conflict("terminated by other getUpdates request"))
    (net, conflict) = caplog.records
    assert net.levelno == logging.WARNING and "network error" in net.getMessage()
    assert conflict.levelno == logging.ERROR and "other getUpdates" in conflict.getMessage()
    assert not any(r.exc_info for r in caplog.records)  # no tracebacks
