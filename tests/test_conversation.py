"""Interactive unknown-merchant workflow (TR-2, FR-6→8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expenses.domain.transaction import Direction, Transaction, TransactionStatus
from expenses.processor.conversation import ConversationOrchestrator, Step

CHAT = 42


def _txn(txn_id="tx-1", description="PAGAMENTO CARTA STARBUCKS MILANO"):
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
    def __init__(self, *, primaries=None, secondaries=None, merchant=None, ignore=None):
        self._primaries = primaries or []
        self._secondaries = secondaries or {}
        self._merchant = [] if merchant is None else merchant
        self._ignore = [] if ignore is None else ignore

    def list_primaries(self):
        return list(self._primaries)

    def list_secondaries(self, primary):
        return list(self._secondaries.get(primary, []))

    def suggest_merchant_substrings(self, description):
        return list(self._merchant)

    def suggest_ignore_patterns(self, description):
        return list(self._ignore)


class _Sheets:
    def __init__(self):
        self.expenses = []
        self.substrings = []
        self.ignores = []

    async def append_expense(self, expense):
        self.expenses.append(expense)

    async def add_merchant_substring(self, primary, secondary, substring):
        self.substrings.append((primary, secondary, substring))

    async def add_ignore_pattern(self, pattern):
        self.ignores.append(pattern)


class _Cache:
    def __init__(self):
        self.refreshed = 0

    async def refresh(self):
        self.refreshed += 1


class _State:
    def __init__(self):
        self.processed = set()

    def is_processed(self, transaction_id):
        return transaction_id in self.processed

    def mark_processed(self, transaction_id):
        self.processed.add(transaction_id)


class _Presenter:
    def __init__(self):
        self.options = []  # (text, options, tag)
        self.messages = []  # (chat_id, text)

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))

    async def send_options(self, chat_id, text, options, *, tag):
        self.options.append((text, list(options), tag))

    @property
    def last(self):
        return self.options[-1]


def _make(engine):
    sheets, cache, state, presenter = _Sheets(), _Cache(), _State(), _Presenter()
    orch = ConversationOrchestrator(engine, sheets, cache, state, CHAT)
    orch.bind(presenter)
    return orch, sheets, cache, state, presenter


async def _tap(orch, presenter, index):
    """Tap the button at ``index`` of the most recent prompt."""
    _, _, tag = presenter.last
    await orch.on_callback(CHAT, message_id=1, data=f"{tag}:{index}", callback_id="cb")


# --- happy paths ---------------------------------------------------------------


async def test_categorize_happy_path():
    engine = _Engine(
        primaries=["Food"],
        secondaries={"Food": ["Groceries"]},
        merchant=["STARBUCKS", "MILANO"],
    )
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    assert pres.last[2] == Step.ACTION.value
    assert pres.last[1] == ["Categorize", "Ignore"]

    await _tap(orch, pres, 0)  # Categorize
    assert pres.last[1:] == (["Food"], Step.PRIMARY.value)

    await _tap(orch, pres, 0)  # Food
    assert pres.last[1:] == (["Groceries"], Step.SECONDARY.value)

    await _tap(orch, pres, 0)  # Groceries
    assert pres.last[1:] == (["STARBUCKS", "MILANO"], Step.MERCHANT.value)

    await _tap(orch, pres, 0)  # STARBUCKS

    assert sheets.substrings == [("Food", "Groceries", "STARBUCKS")]  # FR-11
    assert cache.refreshed == 1  # FR-14
    assert len(sheets.expenses) == 1  # FR-12
    assert sheets.expenses[0].primary == "Food" and sheets.expenses[0].secondary == "Groceries"
    assert state.is_processed("tx-1")  # FR-13
    assert orch._active is None
    assert any("Categorized" in text for _, text in pres.messages)


async def test_ignore_happy_path():
    engine = _Engine(ignore=["REVOLUT", "TOPUP"])
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 1)  # Ignore
    assert pres.last[1:] == (["REVOLUT", "TOPUP"], Step.IGNORE.value)

    await _tap(orch, pres, 0)  # REVOLUT

    assert sheets.ignores == ["REVOLUT"]  # FR-8.4
    assert cache.refreshed == 1  # FR-14
    assert state.is_processed("tx-1")  # FR-8.6
    assert sheets.expenses == []  # FR-8: no expense written
    assert orch._active is None


# --- callback robustness -------------------------------------------------------


async def test_wrong_step_callback_is_ignored():
    orch, _, _, state, pres = _make(_Engine(primaries=["Food"]))
    await orch.handle_unknown(_txn("tx-1"))  # step = ACTION
    await orch.on_callback(CHAT, 1, "pri:0", "cb")  # a stale PRIMARY tap
    assert orch._active.step is Step.ACTION  # unchanged
    assert not state.is_processed("tx-1")


async def test_out_of_range_and_malformed_callbacks_are_ignored():
    orch, _, _, _, pres = _make(_Engine())
    await orch.handle_unknown(_txn("tx-1"))
    await orch.on_callback(CHAT, 1, "act:9", "cb")  # index out of range
    await orch.on_callback(CHAT, 1, "act:x", "cb")  # non-numeric
    assert orch._active.step is Step.ACTION


async def test_callback_with_no_active_session_is_noop():
    orch, sheets, _, state, _ = _make(_Engine())
    await orch.on_callback(CHAT, 1, "act:0", "cb")  # nothing pending
    assert orch._active is None and sheets.expenses == []


# --- empty-candidate fallbacks -------------------------------------------------


async def test_no_merchant_candidates_records_expense_without_rule():
    engine = _Engine(primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=[])
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries → no candidates → auto-finish

    assert sheets.substrings == []  # no rule created
    assert cache.refreshed == 0  # nothing written to Support
    assert len(sheets.expenses) == 1  # expense still recorded
    assert state.is_processed("tx-1")
    assert orch._active is None


async def test_no_ignore_candidates_still_marks_processed():
    orch, sheets, cache, state, pres = _make(_Engine(ignore=[]))
    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 1)  # Ignore → no candidates → auto-finish

    assert sheets.ignores == []
    assert cache.refreshed == 0
    assert sheets.expenses == []
    assert state.is_processed("tx-1")
    assert orch._active is None


async def test_no_primaries_aborts_without_marking():
    orch, sheets, _, state, pres = _make(_Engine(primaries=[]))
    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 0)  # Categorize → no primaries → abort

    assert orch._active is None
    assert not state.is_processed("tx-1")  # left for retry
    assert sheets.expenses == []
    assert pres.messages  # a warning was sent


# --- queueing & draining -------------------------------------------------------


async def test_second_unknown_queues_and_next_begins_after_completion():
    engine = _Engine(
        primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=["STARBUCKS"]
    )
    orch, sheets, cache, state, pres = _make(engine)

    reprocessed = []

    async def reprocess(txn):
        reprocessed.append(txn.id)
        await orch.handle_unknown(txn)  # still unknown → opens its own conversation

    orch.set_reprocess(reprocess)

    await orch.handle_unknown(_txn("tx-1"))
    await orch.handle_unknown(_txn("tx-2", "OTHER SHOP"))  # queued
    assert orch._active.transaction.id == "tx-1"
    assert list(orch._queue)[0].id == "tx-2"

    # Complete tx-1 → drain pops tx-2 → reprocess → new conversation for tx-2.
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap(orch, pres, 0)  # STARBUCKS

    assert reprocessed == ["tx-2"]
    assert orch._active is not None and orch._active.transaction.id == "tx-2"
    assert orch._active.step is Step.ACTION


async def test_same_transaction_is_not_queued_twice():
    orch, *_ , pres = _make(_Engine(primaries=["Food"]))
    await orch.handle_unknown(_txn("tx-1"))  # active
    await orch.handle_unknown(_txn("tx-2", "SHOP"))  # queued
    await orch.handle_unknown(_txn("tx-2", "SHOP"))  # duplicate — ignored
    await orch.handle_unknown(_txn("tx-1"))  # already active — ignored
    assert len(orch._queue) == 1


async def test_drain_auto_processes_queue_until_empty():
    engine = _Engine(
        primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=["STARBUCKS"]
    )
    orch, sheets, cache, state, pres = _make(engine)

    reprocessed = []

    async def reprocess(txn):
        reprocessed.append(txn.id)
        state.mark_processed(txn.id)  # simulate: now matches a rule, no conversation opened

    orch.set_reprocess(reprocess)

    await orch.handle_unknown(_txn("tx-1"))
    await orch.handle_unknown(_txn("tx-2", "A"))
    await orch.handle_unknown(_txn("tx-3", "B"))

    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap(orch, pres, 0)  # STARBUCKS → completes tx-1, drains tx-2 then tx-3

    assert reprocessed == ["tx-2", "tx-3"]
    assert orch._active is None
    assert not orch._queue
