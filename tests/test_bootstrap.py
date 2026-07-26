"""Composition Root — the consent-expiry poll cycle (TR-0)."""

from __future__ import annotations

import httpx
import pytest

from expenses.bootstrap.composition import PollCycle


class _Poller:
    """Scriptable stand-in: each call pops the next scripted outcome (a result value
    or an exception to raise)."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    async def poll_once(self):
        self.calls += 1
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Notifier:
    def __init__(self):
        self.sent = []

    async def notify(self, text):
        self.sent.append(text)


def _auth_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.enablebanking.com/accounts/x/transactions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("auth", request=request, response=response)


async def test_normal_cycle_returns_result_and_does_not_notify():
    notifier = _Notifier()
    cycle = PollCycle(_Poller(["ok"]), notifier)
    assert await cycle() == "ok"
    assert notifier.sent == []


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_error_notifies_once_and_swallows(status):
    notifier = _Notifier()
    poller = _Poller([_auth_error(status), _auth_error(status)])
    cycle = PollCycle(poller, notifier)

    assert await cycle() is None  # swallowed so the scheduler keeps looping
    assert await cycle() is None
    # Deduped: expiry is announced once, not every cycle.
    assert len(notifier.sent) == 1
    assert "expired" in notifier.sent[0].lower()


async def test_notification_re_arms_after_a_successful_poll():
    notifier = _Notifier()
    poller = _Poller([_auth_error(401), "ok", _auth_error(401)])
    cycle = PollCycle(poller, notifier)

    await cycle()  # notifies (1)
    await cycle()  # success re-arms
    await cycle()  # notifies again (2)
    assert len(notifier.sent) == 2


async def test_non_auth_http_error_propagates():
    request = httpx.Request("GET", "https://api.enablebanking.com/x")
    boom = httpx.HTTPStatusError(
        "server", request=request, response=httpx.Response(500, request=request)
    )
    cycle = PollCycle(_Poller([boom]), _Notifier())
    with pytest.raises(httpx.HTTPStatusError):
        await cycle()
