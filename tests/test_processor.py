"""Transaction Processor — automatic path (TR-2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expenses.categorization.models import MatchResult
from expenses.domain.transaction import Direction, Transaction, TransactionStatus
from expenses.processor.processor import TransactionProcessor


def _txn(txn_id="tx-1", description="STARBUCKS MILANO"):
    return Transaction(
        id=txn_id,
        description=description,
        amount=Decimal("12.90"),
        currency="EUR",
        booking_date=date(2026, 7, 25),
        status=TransactionStatus.BOOKED,
        direction=Direction.DEBIT,
    )


class _Engine:
    def __init__(self, ignore=None, match=None):
        self._ignore = ignore
        self._match = match

    def find_ignore_match(self, description):
        return self._ignore

    def match_merchant(self, description):
        return self._match


class _Sheets:
    def __init__(self, events):
        self.appended = []
        self._events = events

    async def append_expense(self, expense):
        self._events.append("write")
        self.appended.append(expense)


class _State:
    def __init__(self, events, processed=()):
        self.processed = set(processed)
        self._events = events

    def is_processed(self, transaction_id):
        return transaction_id in self.processed

    def mark_processed(self, transaction_id):
        self._events.append("mark")
        self.processed.add(transaction_id)


class _Notifier:
    def __init__(self, fail=False):
        self.sent = []
        self._fail = fail

    async def notify(self, text):
        if self._fail:
            raise RuntimeError("telegram down")
        self.sent.append(text)


class _Unknown:
    def __init__(self):
        self.seen = []

    async def handle_unknown(self, transaction):
        self.seen.append(transaction)


def _make(engine, *, processed=(), notifier=None):
    events = []
    sheets = _Sheets(events)
    state = _State(events, processed)
    notifier = notifier or _Notifier()
    unknown = _Unknown()
    processor = TransactionProcessor(engine, sheets, state, notifier, unknown)
    return processor, sheets, state, notifier, unknown, events


async def test_skips_already_processed():
    processor, sheets, state, notifier, unknown, _ = _make(
        _Engine(match=MatchResult("A", "B", "x")), processed={"tx-1"}
    )
    await processor.handle(_txn("tx-1"))
    assert sheets.appended == []
    assert notifier.sent == []
    assert unknown.seen == []


async def test_ignore_match_marks_processed_without_write_or_notify():
    processor, sheets, state, notifier, unknown, _ = _make(_Engine(ignore="revolut"))
    await processor.handle(_txn("tx-1"))
    assert state.is_processed("tx-1")
    assert sheets.appended == []
    assert notifier.sent == []
    assert unknown.seen == []


async def test_merchant_match_writes_marks_and_notifies_in_order():
    processor, sheets, state, notifier, unknown, events = _make(
        _Engine(match=MatchResult("Groceries", "General", "starbucks"))
    )
    await processor.handle(_txn("tx-1"))

    assert len(sheets.appended) == 1
    row = sheets.appended[0]
    assert row.primary == "Groceries" and row.secondary == "General"
    assert row.amount == Decimal("12.90")
    assert state.is_processed("tx-1")
    assert len(notifier.sent) == 1
    # DD-3: write happens before mark.
    assert events == ["write", "mark"]


async def test_unknown_transaction_is_delegated_and_not_marked():
    processor, sheets, state, notifier, unknown, _ = _make(_Engine())  # no ignore, no match
    txn = _txn("tx-1")
    await processor.handle(txn)
    assert unknown.seen == [txn]
    assert not state.is_processed("tx-1")  # revisited later
    assert sheets.appended == []


async def test_notification_failure_does_not_break_flow():
    processor, sheets, state, notifier, unknown, _ = _make(
        _Engine(match=MatchResult("A", "B", "starbucks")), notifier=_Notifier(fail=True)
    )
    await processor.handle(_txn("tx-1"))  # must not raise
    assert sheets.appended and state.is_processed("tx-1")  # still recorded
