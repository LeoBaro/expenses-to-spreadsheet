"""Interactive unknown-merchant workflow (TR-2, FR-6 → FR-8).

The Processor is the sole orchestrator of the interactive flow; this module holds
that orchestration and the workflow state. It plays two roles:

- ``UnknownTransactionHandler`` — the automatic path (``TransactionProcessor``)
  delegates a no-rule-match transaction here to start a conversation.
- ``TelegramUpdateHandler`` — the Bot (TR-6, pure UI) routes button taps back here.

The Bot holds no workflow state; all of it lives here: which transaction, the current
step, and the partial selections. Every Engine / Sheets / Cache / State call is made
here — the Bot only renders and relays.

**Concurrency / ordering (single-user design):** at most one conversation is *active*
at a time. Further unknown transactions queue (FIFO) and are drained when the active
one finishes — so callbacks are never ambiguous. All state mutation is serialized by
an ``asyncio.Lock``; the lock is never held while re-processing a queued transaction
(which re-enters this handler), so there is no re-entrancy deadlock. Draining
re-processes each queued transaction through the *full* pipeline, so a rule just added
for one transaction auto-categorizes its siblings in the same batch.

**Callback protocol:** each prompt is sent with an inline keyboard whose buttons carry
``f"{step}:{index}"`` (see ``keyboards``). A tap is accepted only when its step tag
matches the active session's current step, which cheaply rejects stale taps on
superseded prompts.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from expenses.domain.transaction import Transaction
from expenses.processor.ports import ProcessedState
from expenses.sheets.models import ExpenseRow

logger = logging.getLogger(__name__)


class Step(str, Enum):
    """A conversation step; its value is the callback-data tag for that step."""

    ACTION = "act"  # Categorize / Ignore (FR-6)
    PRIMARY = "pri"  # pick Primary Category (FR-7.1)
    SECONDARY = "sec"  # pick Secondary Category (FR-7.2)
    MERCHANT = "mer"  # pick merchant substring (FR-7.4)
    IGNORE = "ign"  # pick ignore pattern (FR-8.3)


_ACTION_CATEGORIZE = "Categorize"
_ACTION_IGNORE = "Ignore"


@runtime_checkable
class ConversationEngine(Protocol):
    """Categorization Engine (TR-3) — the query/suggestion side used interactively."""

    def list_primaries(self) -> list[str]: ...
    def list_secondaries(self, primary: str) -> list[str]: ...
    def suggest_merchant_substrings(self, description: str) -> list[str]: ...
    def suggest_ignore_patterns(self, description: str) -> list[str]: ...


@runtime_checkable
class RuleWriter(Protocol):
    """Google Sheets Client (TR-4) — the writes the interactive flow performs."""

    async def append_expense(self, expense: ExpenseRow) -> None: ...
    async def add_merchant_substring(self, primary: str, secondary: str, substring: str) -> None: ...
    async def add_ignore_pattern(self, pattern: str) -> None: ...


@runtime_checkable
class RefreshableCache(Protocol):
    """Cache Manager (TR-5) — rebuilt after every Support/Ignore write (FR-14)."""

    async def refresh(self) -> object: ...


@runtime_checkable
class Presenter(Protocol):
    """Telegram Bot (TR-6) — the outbound surface the orchestrator drives."""

    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def send_options(self, chat_id: int, text: str, options: list[str], *, tag: str) -> None: ...


@dataclass
class Session:
    """The in-flight workflow state for one unknown transaction."""

    transaction: Transaction
    step: Step
    options: list[str] = field(default_factory=list)  # currently presented (index → value)
    primary: str | None = None
    secondary: str | None = None


ReprocessFn = Callable[[Transaction], Awaitable[None]]


class ConversationOrchestrator:
    def __init__(
        self,
        engine: ConversationEngine,
        sheets: RuleWriter,
        cache: RefreshableCache,
        state: ProcessedState,
        chat_id: int,
    ) -> None:
        self._engine = engine
        self._sheets = sheets
        self._cache = cache
        self._state = state
        self._chat_id = chat_id
        self._bot: Presenter | None = None
        self._reprocess: ReprocessFn | None = None

        self._active: Session | None = None
        self._queue: deque[Transaction] = deque()
        self._queued_ids: set[str] = set()
        self._lock = asyncio.Lock()

    # --- wiring (breaks the bot ⇄ orchestrator and processor ⇄ orchestrator cycles) ---

    def bind(self, bot: Presenter) -> None:
        """Set the outbound surface. Called by the composition root once the Bot exists."""
        self._bot = bot

    def set_reprocess(self, reprocess: ReprocessFn) -> None:
        """Set the full-pipeline entry point used to drain queued transactions."""
        self._reprocess = reprocess

    @property
    def _presenter(self) -> Presenter:
        if self._bot is None:  # pragma: no cover - a wiring error, never a runtime path
            raise RuntimeError("ConversationOrchestrator.bind(bot) was not called")
        return self._bot

    # --- UnknownTransactionHandler (called by the automatic path) ---

    async def handle_unknown(self, transaction: Transaction) -> None:
        """FR-6 entry: begin a conversation, or queue if one is already active."""
        async with self._lock:
            if self._is_pending(transaction.id):
                logger.debug("transaction %s already pending, not re-queuing", transaction.id)
                return
            if self._active is not None:
                self._queue.append(transaction)
                self._queued_ids.add(transaction.id)
                logger.info("queued unknown transaction %s (a conversation is active)", transaction.id)
                return
            await self._begin(transaction)

    def _is_pending(self, transaction_id: str) -> bool:
        active_id = self._active.transaction.id if self._active is not None else None
        return transaction_id == active_id or transaction_id in self._queued_ids

    async def _begin(self, transaction: Transaction) -> None:
        """FR-6: notify + show amount/date/description with Categorize / Ignore."""
        self._active = Session(transaction, Step.ACTION, [_ACTION_CATEGORIZE, _ACTION_IGNORE])
        text = (
            "🆕 Unknown transaction\n"
            f"Amount: {transaction.amount} {transaction.currency}\n"
            f"Date: {transaction.booking_date.isoformat()}\n"
            f"Description: {transaction.description}\n\n"
            "What should I do?"
        )
        await self._presenter.send_options(
            self._chat_id, text, self._active.options, tag=Step.ACTION.value
        )

    # --- TelegramUpdateHandler (called by the Bot) ---

    async def on_callback(self, chat_id: int, message_id: int, data: str, callback_id: str) -> None:
        finished = False
        async with self._lock:
            session = self._active
            if session is None:
                logger.debug("callback %r with no active conversation; ignoring", data)
                return
            choice = self._decode(session, data)
            if choice is None:
                return  # stale / wrong-step / malformed tap
            finished = await self._advance(session, choice)
        # Drain queued transactions outside the lock (re-processing re-enters this handler).
        if finished:
            await self._drain()

    async def on_message(self, chat_id: int, text: str) -> None:
        # This slice is entirely button-driven; free text is not part of any step.
        logger.debug("ignoring free-text message from %s: %r", chat_id, text)

    def _decode(self, session: Session, data: str) -> str | None:
        """Map a ``"{tag}:{index}"`` callback to the option the active step presented."""
        tag, _, index_str = data.partition(":")
        if tag != session.step.value:
            logger.info("stale/wrong-step callback %r (step is %s); ignoring", data, session.step.value)
            return None
        try:
            index = int(index_str)
        except ValueError:
            logger.warning("malformed callback data %r", data)
            return None
        if not 0 <= index < len(session.options):
            logger.warning("callback index %d out of range for %r", index, session.options)
            return None
        return session.options[index]

    # --- step machine; returns True when the session finished ---

    async def _advance(self, session: Session, choice: str) -> bool:
        if session.step is Step.ACTION:
            if choice == _ACTION_CATEGORIZE:
                await self._ask_primary(session)
            else:
                await self._ask_ignore_pattern(session)
            return False
        if session.step is Step.PRIMARY:
            session.primary = choice
            await self._ask_secondary(session)
            return False
        if session.step is Step.SECONDARY:
            session.secondary = choice
            await self._ask_merchant_substring(session)
            return False
        if session.step is Step.MERCHANT:
            await self._finish_categorize(session, substring=choice)
            return True
        if session.step is Step.IGNORE:
            await self._finish_ignore(session, pattern=choice)
            return True
        return False  # pragma: no cover - exhaustive above

    # --- prompts ---

    async def _ask_primary(self, session: Session) -> None:
        primaries = self._engine.list_primaries()
        if not primaries:
            await self._abort(session, "No Primary Categories are configured in the Support sheet.")
            return
        session.step = Step.PRIMARY
        session.options = primaries
        await self._presenter.send_options(
            self._chat_id, "Pick a Primary Category:", primaries, tag=Step.PRIMARY.value
        )

    async def _ask_secondary(self, session: Session) -> None:
        assert session.primary is not None
        secondaries = self._engine.list_secondaries(session.primary)
        if not secondaries:
            await self._abort(session, f"No Secondary Categories under {session.primary!r}.")
            return
        session.step = Step.SECONDARY
        session.options = secondaries
        await self._presenter.send_options(
            self._chat_id,
            f"Primary: {session.primary}\nPick a Secondary Category:",
            secondaries,
            tag=Step.SECONDARY.value,
        )

    async def _ask_merchant_substring(self, session: Session) -> None:
        candidates = self._engine.suggest_merchant_substrings(session.transaction.description)
        if not candidates:
            # No reusable word available: record the expense with the chosen category
            # (don't lose the user's work), but create no rule. Communicated below.
            await self._finish_categorize(session, substring=None)
            return
        session.step = Step.MERCHANT
        session.options = candidates
        await self._presenter.send_options(
            self._chat_id,
            f"{session.primary} / {session.secondary}\nWhich word should become the merchant rule?",
            candidates,
            tag=Step.MERCHANT.value,
        )

    async def _ask_ignore_pattern(self, session: Session) -> None:
        candidates = self._engine.suggest_ignore_patterns(session.transaction.description)
        if not candidates:
            # Nothing to turn into a pattern; still honour the intent by marking the
            # single transaction processed (FR-8's core effect), without a new rule.
            await self._finish_ignore(session, pattern=None)
            return
        session.step = Step.IGNORE
        session.options = candidates
        await self._presenter.send_options(
            self._chat_id,
            "Which word should become the ignore pattern?",
            candidates,
            tag=Step.IGNORE.value,
        )

    # --- terminal actions ---

    async def _finish_categorize(self, session: Session, *, substring: str | None) -> None:
        """FR-7.5→9: update Support, refresh cache, write expense, mark processed."""
        txn = session.transaction
        assert session.primary is not None and session.secondary is not None

        if substring is not None:
            await self._sheets.add_merchant_substring(session.primary, session.secondary, substring)  # FR-11
            await self._cache.refresh()  # FR-14

        await self._sheets.append_expense(  # FR-12
            ExpenseRow(
                name=txn.description,
                date=txn.booking_date,
                amount=txn.amount,
                primary=session.primary,
                secondary=session.secondary,
            )
        )
        self._state.mark_processed(txn.id)  # FR-13 (after the write, DD-3)
        self._clear(session)

        rule_line = f"Rule added: “{substring}”" if substring else "No reusable rule was added."
        await self._safe_notify(
            f"✅ Categorized “{txn.description}”\n"
            f"Category: {session.primary} / {session.secondary}\n{rule_line}"
        )

    async def _finish_ignore(self, session: Session, *, pattern: str | None) -> None:
        """FR-8.4→6: append pattern, refresh cache, mark processed (no expense written)."""
        txn = session.transaction
        if pattern is not None:
            await self._sheets.add_ignore_pattern(pattern)  # FR-8.4
            await self._cache.refresh()  # FR-14

        self._state.mark_processed(txn.id)  # FR-8.6
        self._clear(session)

        pattern_line = f"Pattern added: “{pattern}”" if pattern else "No reusable pattern was added."
        await self._safe_notify(f"🚫 Ignored “{txn.description}”\n{pattern_line}")

    async def _abort(self, session: Session, reason: str) -> None:
        """Give up on a session without marking processed (it will be retried)."""
        logger.warning("aborting conversation for %s: %s", session.transaction.id, reason)
        self._clear(session)
        await self._safe_notify(f"⚠️ {reason}\nLeaving this transaction for later.")

    def _clear(self, session: Session) -> None:
        if self._active is session:
            self._active = None

    async def _safe_notify(self, text: str) -> None:
        try:
            await self._presenter.send_message(self._chat_id, text)
        except Exception:  # noqa: BLE001 - an informational message must not break the flow
            logger.exception("failed to send conversation notification (ignored)")

    # --- queue draining ---

    async def _drain(self) -> None:
        """Start/handle the next queued transaction(s). Runs without the lock held so
        re-processing (which re-enters ``handle_unknown``) cannot deadlock."""
        if self._reprocess is None:  # pragma: no cover - wiring guarantees this is set
            return
        while True:
            async with self._lock:
                if self._active is not None or not self._queue:
                    return
                transaction = self._queue.popleft()
                self._queued_ids.discard(transaction.id)
            # A rule added moments ago may now match this one → full pipeline re-check.
            await self._reprocess(transaction)
            # If re-processing opened a new conversation, stop; the next callback drives on.
            if self._active is not None:
                return
