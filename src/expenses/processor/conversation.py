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

from expenses.categorization.engine import AND_SEPARATOR
from expenses.domain.transaction import Transaction
from expenses.processor.ports import ProcessedState
from expenses.sheets.models import ExpenseRow
from expenses.telegram_bot.keyboards import DONE_ACTION, SKIP_ACTION

logger = logging.getLogger(__name__)


class Step(str, Enum):
    """A conversation step; its value is the callback-data tag for that step."""

    ACTION = "act"  # Categorize / Ignore (FR-6)
    PRIMARY = "pri"  # pick Primary Category (FR-7.1)
    SECONDARY = "sec"  # pick Secondary Category (FR-7.2)
    MERCHANT = "mer"  # build merchant rule — additive multi-select (FR-7.3/4)
    IGNORE = "ign"  # pick ignore pattern (FR-8.3)


_ACTION_CATEGORIZE = "Categorize"
_ACTION_IGNORE = "Ignore"

# Labels for the "Skip" buttons that let the user complete a step without creating a
# reusable rule/pattern (just handle this one transaction).
_MERCHANT_SKIP_LABEL = "⏭ Skip — categorize without a rule"
_IGNORE_SKIP_LABEL = "⏭ Skip — ignore without a pattern"


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
    async def send_options(
        self,
        chat_id: int,
        text: str,
        options: list[str],
        *,
        tag: str,
        done_label: str | None = None,
        skip_label: str | None = None,
    ) -> None: ...
    async def edit_options(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        options: list[str],
        *,
        tag: str,
        done_label: str | None = None,
        skip_label: str | None = None,
    ) -> None: ...


@dataclass
class Session:
    """The in-flight workflow state for one unknown transaction."""

    transaction: Transaction
    step: Step
    options: list[str] = field(default_factory=list)  # currently presented (index → value)
    primary: str | None = None
    secondary: str | None = None
    selected: list[str] = field(default_factory=list)  # additive multi-select (MERCHANT step)


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
        ended = False
        async with self._lock:
            session = self._active
            if session is None:
                logger.debug("callback %r with no active conversation; ignoring", data)
                return
            tag, _, arg = data.partition(":")
            if tag != session.step.value:
                logger.info(
                    "stale/wrong-step callback %r (step is %s); ignoring", data, session.step.value
                )
                return
            await self._handle_step(session, arg, message_id)
            # The session may have finished directly (Done/Skip/Ignore) OR indirectly —
            # an empty-candidate step or an abort completes it from inside a helper. Keying
            # the drain off "did the active session end" catches every completion path,
            # so queued transactions are never stranded.
            ended = self._active is None
        # Drain queued transactions outside the lock (re-processing re-enters this handler).
        if ended:
            await self._drain()

    async def on_message(self, chat_id: int, text: str) -> None:
        # This slice is entirely button-driven; free text is not part of any step.
        logger.debug("ignoring free-text message from %s: %r", chat_id, text)

    def _option_at(self, session: Session, arg: str) -> str | None:
        """Resolve a numeric callback ``arg`` to the option the step presented."""
        try:
            index = int(arg)
        except ValueError:
            logger.warning("non-index callback arg %r", arg)
            return None
        if not 0 <= index < len(session.options):
            logger.warning("callback index %r out of range for %r", arg, session.options)
            return None
        return session.options[index]

    # --- step machine (advances or completes the active session in place) ---

    async def _handle_step(self, session: Session, arg: str, message_id: int) -> None:
        step = session.step
        if step is Step.ACTION:
            choice = self._option_at(session, arg)
            if choice is None:
                return
            if choice == _ACTION_CATEGORIZE:
                await self._ask_primary(session)
            else:
                await self._ask_ignore_pattern(session)
        elif step is Step.PRIMARY:
            choice = self._option_at(session, arg)
            if choice is None:
                return
            session.primary = choice
            await self._ask_secondary(session)
        elif step is Step.SECONDARY:
            choice = self._option_at(session, arg)
            if choice is None:
                return
            session.secondary = choice
            await self._ask_merchant_substring(session)
        elif step is Step.MERCHANT:
            await self._handle_merchant(session, arg, message_id)
        elif step is Step.IGNORE:
            if arg == SKIP_ACTION:
                # Ignore this transaction (mark processed, no expense) but add no
                # reusable pattern — FR-8's pattern is optional.
                await self._finish_ignore(session, pattern=None)
                return
            choice = self._option_at(session, arg)
            if choice is None:
                return
            await self._finish_ignore(session, pattern=choice)

    async def _handle_merchant(self, session: Session, arg: str, message_id: int) -> None:
        """Additive multi-select (FR-7.3/4): tapping a word toggles it into the rule;
        Done saves the AND-combination of the selected words; Skip categorizes without
        creating any rule."""
        if arg == SKIP_ACTION:
            # Record the expense with the chosen category, but no reusable rule (FR-7.4
            # is optional — the user may just want this one filed).
            await self._finish_categorize(session, substring=None)
            return
        if arg == DONE_ACTION:
            if not session.selected:
                return  # Done isn't offered until ≥1 word is picked; ignore a stray tap
            rule = AND_SEPARATOR.join(session.selected)  # e.g. "APCOA+PARCHEGGIO" (writer lowercases)
            await self._finish_categorize(session, substring=rule)
            return
        word = self._option_at(session, arg)
        if word is None:
            return
        if word in session.selected:
            session.selected.remove(word)  # tap again to de-select
        else:
            session.selected.append(word)
        await self._render_merchant(session, message_id)

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
        session.selected = []
        # First render: Skip is always available; Done appears only once ≥1 word is
        # picked. Subsequent taps edit this same message in place via _render_merchant.
        await self._presenter.send_options(
            self._chat_id,
            self._merchant_text(session),
            self._merchant_labels(session),
            tag=Step.MERCHANT.value,
            done_label=None,
            skip_label=_MERCHANT_SKIP_LABEL,
        )

    async def _render_merchant(self, session: Session, message_id: int) -> None:
        """Re-draw the merchant prompt in place after a word is toggled."""
        done_label = None
        if session.selected:
            done_label = f"✓ Done → {AND_SEPARATOR.join(w.lower() for w in session.selected)}"
        await self._presenter.edit_options(
            self._chat_id,
            message_id,
            self._merchant_text(session),
            self._merchant_labels(session),
            tag=Step.MERCHANT.value,
            done_label=done_label,
            skip_label=_MERCHANT_SKIP_LABEL,
        )

    def _merchant_labels(self, session: Session) -> list[str]:
        """Candidate words, checkmarked when selected. Order matches ``session.options``
        so callback indices stay stable across re-renders (safe against stale taps)."""
        return [f"✓ {word}" if word in session.selected else word for word in session.options]

    def _merchant_text(self, session: Session) -> str:
        header = f"{session.primary} / {session.secondary}"
        if session.selected:
            rule = AND_SEPARATOR.join(w.lower() for w in session.selected)
            return f"{header}\nRule so far: {rule}\nTap words to add/remove, then Done — or Skip."
        return (
            f"{header}\nTap the word(s) that identify this merchant, then Done — "
            "or Skip to categorize this one without a rule."
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
            "Pick a word to ignore on future transactions — or Skip to ignore just this one.",
            candidates,
            tag=Step.IGNORE.value,
            skip_label=_IGNORE_SKIP_LABEL,
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

        rule_line = f"Rule added: “{substring.lower()}”" if substring else "No reusable rule was added."
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
