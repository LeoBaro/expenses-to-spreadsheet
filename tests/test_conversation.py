"""Interactive unknown-merchant workflow (TR-2, FR-6→8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expenses.domain.transaction import Direction, Transaction, TransactionStatus
from expenses.processor.conversation import ConversationOrchestrator, Step
from expenses.telegram_bot.keyboards import (
    BACK_ACTION,
    DONE_ACTION,
    NEXT_MONTH_ACTION,
    PREV_MONTH_ACTION,
    SKIP_ACTION,
)

CHAT = 42


def _txn(txn_id="tx-1", description="PAGAMENTO CARTA STARBUCKS MILANO", booked=date(2026, 7, 25)):
    return Transaction(
        id=txn_id,
        description=description,
        amount=Decimal("12.90"),
        currency="EUR",
        booking_date=booked,
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
    """Records every render. ``send_options`` hands out increasing message ids like
    Telegram does; ``live_id`` is the message the conversation's buttons live on."""

    def __init__(self):
        self.options = []  # (text, options, tag) — appended on both send and edit
        self.messages = []  # (chat_id, text)
        self.labels = {}  # extra-button labels of the latest render
        self.sent = 0  # number of prompts sent as new messages
        self.edits = []  # message ids edited in place
        self.live_id = None

    @property
    def last_done_label(self):
        return self.labels.get("done_label")

    @property
    def last_skip_label(self):
        return self.labels.get("skip_label")

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))

    async def send_options(self, chat_id, text, options, *, tag, **labels):
        self.options.append((text, list(options), tag))
        self.labels = labels
        self.sent += 1
        self.live_id = 100 + self.sent
        return self.live_id

    async def edit_options(self, chat_id, message_id, text, options, *, tag, **labels):
        self.options.append((text, list(options), tag))
        self.labels = labels
        self.edits.append(message_id)

    @property
    def last(self):
        return self.options[-1]


def _make(engine):
    sheets, cache, state, presenter = _Sheets(), _Cache(), _State(), _Presenter()
    orch = ConversationOrchestrator(engine, sheets, cache, state, CHAT)
    orch.bind(presenter)
    return orch, sheets, cache, state, presenter


async def _press(orch, presenter, arg, message_id=None):
    """Tap the button ``f"{tag}:{arg}"`` of the live prompt (or of ``message_id``)."""
    _, _, tag = presenter.last
    mid = presenter.live_id if message_id is None else message_id
    await orch.on_callback(CHAT, message_id=mid, data=f"{tag}:{arg}", callback_id="cb")


async def _tap(orch, presenter, index):
    """Tap the option at ``index`` of the live prompt."""
    await _press(orch, presenter, index)


async def _tap_done(orch, presenter):
    """Tap the Done button of a multi-select prompt."""
    await _press(orch, presenter, DONE_ACTION)


async def _tap_skip(orch, presenter):
    """Tap the Skip button of the merchant/ignore prompt."""
    await _press(orch, presenter, SKIP_ACTION)


async def _tap_back(orch, presenter):
    await _press(orch, presenter, BACK_ACTION)


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
    await orch.on_callback(CHAT, pres.live_id, "pri:0", "cb")  # a stale PRIMARY tap
    assert orch._active.step is Step.ACTION  # unchanged
    assert not state.is_processed("tx-1")


async def test_out_of_range_and_malformed_callbacks_are_ignored():
    orch, _, _, _, pres = _make(_Engine())
    await orch.handle_unknown(_txn("tx-1"))
    await orch.on_callback(CHAT, pres.live_id, "act:9", "cb")  # index out of range
    await orch.on_callback(CHAT, pres.live_id, "act:x", "cb")  # non-numeric
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
    await _tap(orch, pres, 0)  # Groceries → no candidates → prompt with Skip + Back only
    assert pres.last[1:] == ([], Step.MERCHANT.value)
    assert pres.last_skip_label is not None and pres.labels.get("back_label") is not None
    assert sheets.expenses == []  # nothing written until the final choice

    await _tap_skip(orch, pres)

    assert sheets.substrings == []  # no rule created
    assert cache.refreshed == 0  # nothing written to Support
    assert len(sheets.expenses) == 1  # expense still recorded
    assert state.is_processed("tx-1")
    assert orch._active is None


async def test_no_ignore_candidates_still_marks_processed():
    orch, sheets, cache, state, pres = _make(_Engine(ignore=[]))
    await orch.handle_unknown(_txn("tx-1"))
    await _tap(orch, pres, 1)  # Ignore → no candidates → prompt with Skip + Back only
    assert pres.last[1:] == ([], Step.IGNORE.value)
    assert not state.is_processed("tx-1")  # not final yet — Ignore can still be undone

    await _tap_skip(orch, pres)

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
    # Regression: tx-1 yields NO merchant candidates. The queued tx-2 must still be
    # picked up once tx-1 is filed — previously the drain was keyed off the step's
    # return value, which stranded the queue until an app restart. (The abort test
    # below covers completion from inside a helper.)
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
    await _tap(orch, pres, 0)  # Groceries → no candidates → Skip/Back prompt
    await _tap_skip(orch, pres)  # file tx-1 without a rule

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


# --- undo (Back) ---------------------------------------------------------------


def _full_engine():
    return _Engine(
        primaries=["Food", "Transport"],
        secondaries={"Food": ["Groceries", "Restaurants"], "Transport": ["Parking"]},
        merchant=["STARBUCKS", "MILANO"],
        ignore=["REVOLUT"],
    )


async def test_back_is_offered_on_every_step_but_the_first():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    assert pres.labels.get("back_label") is None  # Categorize/Ignore: nothing to undo
    await _tap(orch, pres, 0)  # Categorize
    assert pres.labels.get("back_label") is not None  # PRIMARY
    await _tap(orch, pres, 0)  # Food
    assert pres.labels.get("back_label") is not None  # SECONDARY
    await _tap(orch, pres, 0)  # Groceries
    assert pres.labels.get("back_label") is not None  # MERCHANT
    await _tap(orch, pres, 0)  # toggle a word: re-render keeps Back
    assert pres.labels.get("back_label") is not None


async def test_back_from_primary_returns_to_categorize_or_ignore():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    await _tap_back(orch, pres)
    assert pres.last[1:] == (["Categorize", "Ignore"], Step.ACTION.value)

    await _tap(orch, pres, 1)  # change of mind → Ignore
    assert pres.last[2] == Step.IGNORE.value
    await _tap(orch, pres, 0)  # REVOLUT
    assert sheets.ignores == ["REVOLUT"] and sheets.expenses == []
    assert state.is_processed("tx-1")


async def test_back_from_secondary_lets_user_pick_another_primary():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap_back(orch, pres)
    assert pres.last[1:] == (["Food", "Transport"], Step.PRIMARY.value)
    assert orch._active.primary is None  # choice forgotten

    await _tap(orch, pres, 1)  # Transport
    assert pres.last[1:] == (["Parking"], Step.SECONDARY.value)
    await _tap(orch, pres, 0)  # Parking
    await _tap_skip(orch, pres)
    assert (sheets.expenses[0].primary, sheets.expenses[0].secondary) == ("Transport", "Parking")


async def test_back_from_merchant_clears_selection_and_reasks_secondary():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap(orch, pres, 0)  # select STARBUCKS
    await _tap_back(orch, pres)
    assert pres.last[1:] == (["Groceries", "Restaurants"], Step.SECONDARY.value)
    assert orch._active.secondary is None and orch._active.selected == []

    await _tap(orch, pres, 1)  # Restaurants
    assert pres.last[1] == ["STARBUCKS", "MILANO"]  # fresh, nothing pre-selected
    await _tap(orch, pres, 1)  # MILANO
    await _tap_done(orch, pres)
    assert sheets.substrings == [("Food", "Restaurants", "MILANO")]
    assert sheets.expenses[0].secondary == "Restaurants"


async def test_back_from_ignore_returns_to_categorize_or_ignore():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 1)  # Ignore
    await _tap_back(orch, pres)
    assert pres.last[1:] == (["Categorize", "Ignore"], Step.ACTION.value)
    assert sheets.ignores == [] and not state.is_processed("tx-1")

    await _tap(orch, pres, 0)  # Categorize instead
    assert pres.last[2] == Step.PRIMARY.value


async def test_back_from_empty_candidate_prompts():
    engine = _Engine(primaries=["Food"], secondaries={"Food": ["Groceries"]}, merchant=[], ignore=[])
    orch, sheets, cache, state, pres = _make(engine)
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 1)  # Ignore → no candidates
    await _tap_back(orch, pres)
    assert pres.last[2] == Step.ACTION.value
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries → no candidates
    await _tap_back(orch, pres)
    assert pres.last[2] == Step.SECONDARY.value
    assert sheets.expenses == [] and not state.is_processed("tx-1")


async def test_final_choice_cannot_be_undone():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap_skip(orch, pres)  # final
    await _tap_back(orch, pres)  # a late Back on the finished prompt
    assert orch._active is None
    assert len(sheets.expenses) == 1 and state.is_processed("tx-1")


async def test_back_on_first_question_is_ignored():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap_back(orch, pres)
    assert orch._active.step is Step.ACTION


# --- one live prompt per conversation -------------------------------------------


async def test_every_step_edits_the_first_prompt_in_place():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    first = pres.live_id
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap_back(orch, pres)
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap(orch, pres, 0)  # toggle word
    assert pres.sent == 1  # only the first prompt is a new message
    assert pres.edits and set(pres.edits) == {first}


async def test_every_prompt_repeats_transaction_details():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    for text, _, _ in pres.options:
        assert "PAGAMENTO CARTA STARBUCKS MILANO" in text and "12.90 EUR" in text


async def test_taps_on_a_superseded_message_are_ignored():
    orch, sheets, cache, state, pres = _make(_full_engine())

    async def reprocess(txn):
        await orch.handle_unknown(txn)

    orch.set_reprocess(reprocess)
    await orch.handle_unknown(_txn("tx-1"))
    await orch.handle_unknown(_txn("tx-2", "OTHER SHOP"))  # queued
    old = pres.live_id
    await _tap(orch, pres, 1)  # Ignore
    await _tap_skip(orch, pres)  # tx-1 done → tx-2 prompt sent as a new message
    assert pres.live_id != old

    # A tap on tx-1's old message with a tag that happens to match tx-2's step.
    await orch.on_callback(CHAT, old, "act:1", "cb")
    assert orch._active.transaction.id == "tx-2" and orch._active.step is Step.ACTION


# --- month override -------------------------------------------------------------


async def test_next_month_moves_expense_to_next_sheet_keeping_booking_date():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn(booked=date(2026, 7, 25)))
    assert "Month: Jul" in pres.last[0]
    assert pres.labels.get("prev_label") and pres.labels.get("next_label")

    await _press(orch, pres, NEXT_MONTH_ACTION)
    assert pres.last[2] == Step.ACTION.value  # still the same question
    assert "Month: Aug (booked in Jul)" in pres.last[0]

    await _tap(orch, pres, 0)  # Categorize
    await _tap(orch, pres, 0)  # Food
    await _tap(orch, pres, 0)  # Groceries
    await _tap_skip(orch, pres)

    expense = sheets.expenses[0]
    assert expense.sheet_month == 8
    assert expense.date == date(2026, 7, 25)  # Date column keeps the booking date
    assert any("Month: Aug" in text for _, text in pres.messages)


async def test_prev_month_and_back_to_booking_month_writes_default_sheet():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn(booked=date(2026, 7, 25)))
    await _press(orch, pres, PREV_MONTH_ACTION)
    await _press(orch, pres, PREV_MONTH_ACTION)
    assert "Month: May (booked in Jul)" in pres.last[0]
    await _press(orch, pres, NEXT_MONTH_ACTION)
    await _press(orch, pres, NEXT_MONTH_ACTION)
    assert "booked in" not in pres.last[0]

    await _tap(orch, pres, 0)
    await _tap(orch, pres, 0)
    await _tap(orch, pres, 0)
    await _tap_skip(orch, pres)
    assert sheets.expenses[0].sheet_month is None  # booking month → default sheet


async def test_month_choice_survives_back_navigation():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn(booked=date(2026, 7, 25)))
    await _press(orch, pres, NEXT_MONTH_ACTION)  # Aug
    await _tap(orch, pres, 0)  # Categorize
    assert "Month: Aug" in pres.last[0]  # shown on later steps too
    await _tap_back(orch, pres)
    assert "Month: Aug (booked in Jul)" in pres.last[0]
    await _tap(orch, pres, 0)
    await _tap(orch, pres, 0)
    await _tap(orch, pres, 0)
    await _tap_skip(orch, pres)
    assert sheets.expenses[0].sheet_month == 8


async def test_month_navigation_stays_within_the_year():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn(booked=date(2026, 1, 3)))
    assert pres.labels.get("prev_label") is None  # no December of last year
    assert pres.labels.get("next_label") is not None
    await _press(orch, pres, PREV_MONTH_ACTION)  # stale/forged tap
    assert orch._active.month == 1

    orch2, *_, pres2 = _make(_full_engine())
    await orch2.handle_unknown(_txn(booked=date(2026, 11, 30)))
    await _press(orch2, pres2, NEXT_MONTH_ACTION)  # Dec
    assert pres2.labels.get("next_label") is None and pres2.labels.get("prev_label") is not None
    await _press(orch2, pres2, NEXT_MONTH_ACTION)
    assert orch2._active.month == 12


async def test_month_buttons_only_on_the_first_question():
    orch, *_, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _tap(orch, pres, 0)  # Categorize
    assert pres.labels.get("prev_label") is None and pres.labels.get("next_label") is None
    await _press(orch, pres, NEXT_MONTH_ACTION)  # wrong step → ignored
    assert orch._active.step is Step.PRIMARY and orch._active.month == 7


async def test_ignore_after_moving_month_writes_nothing():
    orch, sheets, cache, state, pres = _make(_full_engine())
    await orch.handle_unknown(_txn())
    await _press(orch, pres, NEXT_MONTH_ACTION)
    await _tap(orch, pres, 1)  # Ignore
    await _tap_skip(orch, pres)
    assert sheets.expenses == [] and state.is_processed("tx-1")
