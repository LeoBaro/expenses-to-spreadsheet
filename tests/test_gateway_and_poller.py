"""Gateway pagination and end-to-end poll-cycle tests (mocked HTTP)."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from expenses.poller.enable_banking.auth import EnableBankingAuth
from expenses.poller.enable_banking.gateway import EnableBankingGateway
from expenses.poller.local_adapters import InMemoryProcessedStore
from expenses.poller.poller import TransactionPoller

BASE = "https://api.enablebanking.test"


class _StubAuth(EnableBankingAuth):
    def __init__(self):
        pass

    def bearer(self) -> str:  # type: ignore[override]
        return "stub-token"


class _RecordingSink:
    def __init__(self):
        self.received = []

    async def handle(self, transaction):
        self.received.append(transaction)


@respx.mock
async def test_gateway_follows_continuation_key():
    url = f"{BASE}/accounts/acc-1/transactions"
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(200, json={"transactions": [{"transaction_id": "a"}], "continuation_key": "k2"}),
        httpx.Response(200, json={"transactions": [{"transaction_id": "b"}]}),
    ]

    async with httpx.AsyncClient() as client:
        gateway = EnableBankingGateway(client, _StubAuth(), BASE)
        ids = [raw["transaction_id"] async for raw in gateway.iter_transactions("acc-1", date(2026, 7, 1), date(2026, 7, 24))]

    assert ids == ["a", "b"]
    assert route.call_count == 2
    # Second call carried the continuation key.
    assert "continuation_key=k2" in str(route.calls[1].request.url)


@respx.mock
async def test_poll_cycle_filters_and_forwards(booked_debit, pending_debit, booked_credit):
    url = f"{BASE}/accounts/acc-1/transactions"
    respx.get(url).mock(
        return_value=httpx.Response(200, json={"transactions": [booked_debit, pending_debit, booked_credit]})
    )

    sink = _RecordingSink()
    async with httpx.AsyncClient() as client:
        gateway = EnableBankingGateway(client, _StubAuth(), BASE)
        poller = TransactionPoller(gateway, InMemoryProcessedStore(), sink, account_uid="acc-1", lookback_days=7)
        result = await poller.poll_once(today=date(2026, 7, 24))

    # Only the booked debit is an expense.
    assert [t.id for t in sink.received] == ["tx-1001"]
    assert result.forwarded == 1
    assert result.skipped_not_expense == 2


@respx.mock
async def test_poll_cycle_skips_zero_amount_debit(booked_debit, zero_amount_debit):
    url = f"{BASE}/accounts/acc-1/transactions"
    respx.get(url).mock(
        return_value=httpx.Response(200, json={"transactions": [booked_debit, zero_amount_debit]})
    )

    sink = _RecordingSink()
    async with httpx.AsyncClient() as client:
        gateway = EnableBankingGateway(client, _StubAuth(), BASE)
        poller = TransactionPoller(gateway, InMemoryProcessedStore(), sink, account_uid="acc-1", lookback_days=7)
        result = await poller.poll_once(today=date(2026, 7, 24))

    # DD-6: the zero-amount debit is not an expense, even though it's settled+debit.
    assert [t.id for t in sink.received] == ["tx-1001"]
    assert result.forwarded == 1
    assert result.skipped_not_expense == 1


@respx.mock
async def test_poll_cycle_skips_already_processed(booked_debit):
    url = f"{BASE}/accounts/acc-1/transactions"
    respx.get(url).mock(return_value=httpx.Response(200, json={"transactions": [booked_debit]}))

    processed = InMemoryProcessedStore()
    processed.mark_processed("tx-1001")
    sink = _RecordingSink()

    async with httpx.AsyncClient() as client:
        gateway = EnableBankingGateway(client, _StubAuth(), BASE)
        poller = TransactionPoller(gateway, processed, sink, account_uid="acc-1")
        result = await poller.poll_once(today=date(2026, 7, 24))

    assert sink.received == []
    assert result.skipped_processed == 1
