"""Interactive unknown-merchant workflow (TR-2, FR-6→8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expenses.domain.transaction import Direction, Transaction, TransactionStatus
from expenses.processor.conversation import ConversationOrchestrator, Step
from expenses.telegram_bot.keyboards import DONE_ACTION, SKIP_ACTION

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
        self.options = []  # (text, options, tag) — appended on both send and edit
        self.messages = []  # (chat_id, text)
        self.last_done_label = None
        self.last_skip_label = None

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))

    async def send_options(self, chat_id, text, options, *, tag, done_label=None, skip_label=None):
        self.options.append((text, list(options), tag))
        self.last_done_label = done_label
        self.last_skip_label = skip_label

    async def edit_options(
        self, chat_id, message_id, text, options, *, tag, done_label=None, skip_label=None
    ):
        self.options.append((text, list(options), tag))
        self.last_done_label = done_label
        self.last_skip_label = skip_label

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


async def _tap_done(orch, presenter):
    """Tap the Done button of a multi-select prompt."""
    _, _, tag = presenter.last
    await orch.on_callback(CHAT, message_id=1, data=f"{tag}:{DONE_ACTION}", callback_id="cb")


async def _tap_skip(orch, presenter):
    """Tap the Skip button of the merchant prompt."""
    _, _, tag = presenter.last
    await orch.on_callback(CHAT, message_id=1, data=f"{tag}:{SKIP_ACTION}", callback_id="cb")


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

    await _tap(orch, pres, 0)  # Groceries → enters MERCHANT multi-select
    assert pres.last[1:] == (["STARBUCKS", "MILANO"], Step.MERCHANT.value)
    assert pres.last_done_label is None  # no Done until a word is picked
    assert pres.last_skip_label is not None  # Skip is always available

    await _tap(orch, pres, 0)  # add STARBUCKS
    assert pres.last[1] == ["✓ STARBUCKS", "MILANO"]  # checkmarked
    assert pres.last_done_label is not None  # Done now offered

    await _tap_done(orch, pres)  # finalize single-word rule

    assert sheets.substrings == [("Food", "Groceries", "STARBUCKS")]  # FR-11
    assert cache.refreshed == 1  # FR-14
    assert len(sheets.expenses) == 1  # FR-12
    assert sheets.expenses[0].primary == "Food" and sheets.expenses[0].secondary == "Groceries"
    assert state.is_processed("tx-1")  # FR-13
    assert orch._active is None
    assert any("Categorized" in text for _, text in pres.messages)


async def test_merchant_and_combination_builds_plus_rule():
    engine = _Engine(
        primaries=["Transport"],
        secondaries={"Transport": ["Parking"]},
        merchant=["APCOA", "PARCHEGGIO", "PIAZZ"],
    )
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1", "APCOA PARCHEGGIO PIAZZ"))
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Transport
    await _tap(orch, pres, 0)  # Parking → MERCHANT

    await _tap(orch, pres, 0)  # add APCOA
    await _tap(orch, pres, 1)  # add PARCHEGGIO
    assert pres.last[1] == ["✓ APCOA", "✓ PARCHEGGIO", "PIAZZ"]
    await _tap_done(orch, pres)

    # AND-combination stored joined by '+'.
    assert sheets.substrings == [("Transport", "Parking", "APCOA+PARCHEGGIO")]
    assert len(sheets.expenses) == 1
    assert state.is_processed("tx-1")


async def test_merchant_skip_categorizes_without_a_rule():
    engine = _Engine(
        primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=["STARBUCKS", "MILANO"]
    )
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries → MERCHANT (candidates present)
    await _tap_skip(orch, pres)  # skip rule creation

    assert sheets.substrings == []  # no rule created
    assert cache.refreshed == 0  # nothing written to Support
    assert len(sheets.expenses) == 1  # expense still recorded with chosen category
    assert sheets.expenses[0].primary == "Food" and sheets.expenses[0].secondary == "Groceries"
    assert state.is_processed("tx-1")
    assert orch._active is None


async def test_merchant_skip_available_even_after_selecting_words():
    engine = _Engine(
        primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=["STARBUCKS", "MILANO"]
    )
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap(orch, pres, 0)  # select STARBUCKS
    assert pres.last_done_label is not None and pres.last_skip_label is not None
    await _tap_skip(orch, pres)  # skip anyway → no rule despite a selection

    assert sheets.substrings == []
    assert len(sheets.expenses) == 1
    assert state.is_processed("tx-1")


async def test_merchant_toggle_deselects_and_done_needs_a_word():
    engine = _Engine(
        primaries=["Transport"], secondaries={"Transport": ["Parking"]}, merchant=["APCOA", "PIAZZ"]
    )
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1", "APCOA PIAZZ"))
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Transport
    await _tap(orch, pres, 0)  # Parking

    await _tap(orch, pres, 0)  # add APCOA
    await _tap(orch, pres, 0)  # tap APCOA again → deselect
    assert pres.last[1] == ["APCOA", "PIAZZ"]
    assert pres.last_done_label is None  # nothing selected

    await _tap_done(orch, pres)  # Done with nothing → ignored
    assert orch._active is not None and sheets.substrings == []

    await _tap(orch, pres, 1)  # add PIAZZ
    await _tap_done(orch, pres)
    assert sheets.substrings == [("Transport", "Parking", "PIAZZ")]  # single-word still works


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


async def test_ignore_skip_marks_processed_without_a_pattern():
    engine = _Engine(ignore=["REVOLUT", "TOPUP"])
    orch, sheets, cache, state, pres = _make(engine)

    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 1)  # Ignore → candidates present
    assert pres.last[1:] == (["REVOLUT", "TOPUP"], Step.IGNORE.value)
    assert pres.last_skip_label is not None  # Skip offered alongside patterns

    await _tap_skip(orch, pres)  # ignore this one, add no pattern

    assert sheets.ignores == []  # no pattern written
    assert cache.refreshed == 0  # nothing written to Ignore
    assert sheets.expenses == []  # still no expense (FR-8)
    assert state.is_processed("tx-1")  # but marked processed
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
    await _tap(orch, pres, 0)  # add STARBUCKS
    await _tap_done(orch, pres)  # finalize

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
    await _tap(orch, pres, 0)  # add STARBUCKS
    await _tap_done(orch, pres)  # completes tx-1, drains tx-2 then tx-3

    assert reprocessed == ["tx-2", "tx-3"]
    assert orch._active is None
    assert not orch._queue


async def test_empty_merchant_candidates_still_drains_queue():
    # Regression: tx-1 yields NO merchant candidates → the session auto-finishes from
    # inside the SECONDARY step (not a MERCHANT Done/Skip tap). The queued tx-2 must
    # still be picked up — previously the drain was keyed off the step's return value,
    # so this completion path stranded the queue until an app restart.
    engine = _Engine(primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=[])
    orch, sheets, cache, state, pres = _make(engine)

    reprocessed = []

    async def reprocess(txn):
        reprocessed.append(txn.id)
        await orch.handle_unknown(txn)  # still unknown → opens its own conversation

    orch.set_reprocess(reprocess)

    await orch.handle_unknown(_txn("tx-1", "OPENAI"))
    await orch.handle_unknown(_txn("tx-2", "SPESA CONAD"))  # queued behind tx-1
    assert orch._active.transaction.id == "tx-1"

    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries → no candidates → auto-finish tx-1

    assert state.is_processed("tx-1")  # tx-1 filed without a rule
    assert reprocessed == ["tx-2"]  # queue drained
    assert orch._active is not None and orch._active.transaction.id == "tx-2"


async def test_abort_on_misconfig_still_drains_queue():
    # An abort (no Primary Categories) also ends the session from inside a helper;
    # the queue must drain there too.
    engine = _Engine(primaries=[])  # misconfigured Support → abort on Categorize
    orch, sheets, cache, state, pres = _make(engine)

    reprocessed = []

    async def reprocess(txn):
        reprocessed.append(txn.id)
        await orch.handle_unknown(txn)

    orch.set_reprocess(reprocess)

    await orch.handle_unknown(_txn("tx-1"))
    await orch.handle_unknown(_txn("tx-2", "SHOP"))  # queued
    await _tap(orch, pres, 0)  # Categorize → no primaries → abort tx-1

    assert not state.is_processed("tx-1")  # aborted, not marked (will retry)
    assert reprocessed == ["tx-2"]  # queue still drained
    assert orch._active is not None and orch._active.transaction.id == "tx-2"
