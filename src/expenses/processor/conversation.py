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

**One live prompt per conversation:** the first prompt (FR-6) is sent as a new message;
every later step — forward, Back, or a month change — edits that same message in place,
so the chat only ever has one set of live buttons for the transaction. Each prompt
repeats the transaction details so they stay visible on every step.

**Undo (Back):** every step before the final one carries a Back button that returns to
the previous question and forgets the choice made there (Primary → Categorize/Ignore,
Secondary → Primary, merchant rule → Secondary, ignore pattern → Categorize/Ignore).
Nothing is written until the final step, so Back never has anything to roll back. The
final choice — a rule/pattern (Done or a pattern tap) or Skip — cannot be undone.

**Month override:** the Categorize/Ignore prompt has "< Prev month" / "Next month >"
buttons that move the expense to another month's sheet (Jan–Dec only: one spreadsheet
per year). The row's Date column keeps the booking date.

**Callback protocol:** each prompt is sent with an inline keyboard whose buttons carry
``f"{step}:{index}"`` or ``f"{step}:{action}"`` (see ``keyboards``). A tap is accepted
only when it comes from the conversation's live prompt message and its step tag
matches the current step, which rejects stale taps on superseded prompts.
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
from expenses.sheets.months import month_name
from expenses.telegram_bot.keyboards import (
    BACK_ACTION,
    DONE_ACTION,
    NEXT_MONTH_ACTION,
    PREV_MONTH_ACTION,
    SKIP_ACTION,
)

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
_BACK_LABEL = "↩ Back"
_PREV_MONTH_LABEL = "< Prev month"
_NEXT_MONTH_LABEL = "Next month >"


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
        back_label: str | None = None,
        prev_label: str | None = None,
        next_label: str | None = None,
    ) -> int | None:
        """Send a prompt; returns the sent message id (``None`` if unknown)."""
        ...
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
        back_label: str | None = None,
        prev_label: str | None = None,
        next_label: str | None = None,
    ) -> None: ...


@dataclass
class Session:
    """The in-flight workflow state for one unknown transaction."""

    transaction: Transaction
    step: Step
    month: int  # destination month sheet, 1–12 (starts at the booking month)
    options: list[str] = field(default_factory=list)  # currently presented (index → value)
    primary: str | None = None
    secondary: str | None = None
    selected: list[str] = field(default_factory=list)  # additive multi-select (MERCHANT step)
    message_id: int | None = None  # the conversation's live prompt (None if unknown)

    @property
    def moved(self) -> bool:
        """True when the user moved the expense away from its booking month."""
        return self.month != self.transaction.booking_date.month


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
        """FR-6: notify + show amount/date/description with Categorize / Ignore. This is
        the only prompt sent as a new message; later steps edit it in place."""
        self._active = Session(transaction, Step.ACTION, month=transaction.booking_date.month)
        await self._ask_action(self._active, message_id=None)

    # --- TelegramUpdateHandler (called by the Bot) ---

    async def on_callback(self, chat_id: int, message_id: int, data: str, callback_id: str) -> None:
        ended = False
        async with self._lock:
            session = self._active
            if session is None:
                logger.debug("callback %r with no active conversation; ignoring", data)
                return
            if session.message_id is not None and message_id != session.message_id:
                logger.info(
                    "callback %r from superseded message %s (live prompt is %s); ignoring",
                    data,
                    message_id,
                    session.message_id,
                )
                return
            tag, _, arg = data.partition(":")
            if tag != session.step.value:
                logger.info(
                    "stale/wrong-step callback %r (step is %s); ignoring", data, session.step.value
                )
                return
            await self._handle_step(session, arg, message_id)
            # The session may have finished directly (Done/Skip/Ignore) OR indirectly —
            # an abort (misconfigured Support sheet) completes it from inside a helper. Keying
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
        if arg == BACK_ACTION and step is not Step.ACTION:
            await self._go_back(session, message_id)
            return
        if step is Step.ACTION:
            if arg in (PREV_MONTH_ACTION, NEXT_MONTH_ACTION):
                await self._shift_month(session, -1 if arg == PREV_MONTH_ACTION else 1, message_id)
                return
            choice = self._option_at(session, arg)
            if choice is None:
                return
            if choice == _ACTION_CATEGORIZE:
                await self._ask_primary(session, message_id)
            else:
                await self._ask_ignore_pattern(session, message_id)
        elif step is Step.PRIMARY:
            choice = self._option_at(session, arg)
            if choice is None:
                return
            session.primary = choice
            await self._ask_secondary(session, message_id)
        elif step is Step.SECONDARY:
            choice = self._option_at(session, arg)
            if choice is None:
                return
            session.secondary = choice
            await self._ask_merchant_substring(session, message_id)
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

    async def _go_back(self, session: Session, message_id: int) -> None:
        """Undo the previous choice: re-ask the previous question in place and forget
        what was picked there. Nothing has been written yet, so there is nothing to
        roll back."""
        step = session.step
        session.selected = []
        if step in (Step.PRIMARY, Step.IGNORE):
            session.primary = session.secondary = None
            await self._ask_action(session, message_id)
        elif step is Step.SECONDARY:
            session.primary = session.secondary = None
            await self._ask_primary(session, message_id)
        elif step is Step.MERCHANT:
            session.secondary = None
            await self._ask_secondary(session, message_id)

    async def _shift_month(self, session: Session, delta: int, message_id: int) -> None:
        """Move the expense to the previous/next month's sheet (Jan–Dec only)."""
        month = session.month + delta
        if not 1 <= month <= 12:
            # The button isn't offered at the edges; this is a stale/duplicate tap.
            logger.info("month change to %s out of range; ignoring", month)
            return
        session.month = month
        await self._ask_action(session, message_id)

    # --- prompts ---

    async def _show(
        self,
        session: Session,
        step: Step,
        text: str,
        options: list[str],
        message_id: int | None,
        **labels: str | None,
    ) -> None:
        """Make ``step`` current and render it: a new message when ``message_id`` is
        ``None`` (first prompt only), otherwise an in-place edit of the live prompt."""
        session.step = step
        session.options = options
        if message_id is None:
            session.message_id = await self._presenter.send_options(
                self._chat_id, text, options, tag=step.value, **labels
            )
        else:
            await self._presenter.edit_options(
                self._chat_id, message_id, text, options, tag=step.value, **labels
            )

    def _details(self, session: Session, *, with_month: bool = True) -> str:
        """Transaction header repeated on every prompt (FR-6.2)."""
        txn = session.transaction
        lines = [
            "🆕 Unknown transaction",
            f"Amount: {txn.amount} {txn.currency}",
            f"Date: {txn.booking_date.isoformat()}",
            f"Description: {txn.description}",
        ]
        if with_month:
            lines.append(self._month_line(session))
        return "\n".join(lines)

    def _month_line(self, session: Session) -> str:
        line = f"Month: {month_name(session.month)}"
        if session.moved:
            line += f" (booked in {month_name(session.transaction.booking_date.month)})"
        return line

    async def _ask_action(self, session: Session, message_id: int | None) -> None:
        """FR-6: Categorize / Ignore, plus month navigation for the destination sheet."""
        await self._show(
            session,
            Step.ACTION,
            f"{self._details(session)}\n\nWhat should I do?",
            [_ACTION_CATEGORIZE, _ACTION_IGNORE],
            message_id,
            prev_label=_PREV_MONTH_LABEL if session.month > 1 else None,
            next_label=_NEXT_MONTH_LABEL if session.month < 12 else None,
        )

    async def _ask_primary(self, session: Session, message_id: int) -> None:
        primaries = self._engine.list_primaries()
        if not primaries:
            await self._abort(session, "No Primary Categories are configured in the Support sheet.")
            return
        await self._show(
            session,
            Step.PRIMARY,
            f"{self._details(session)}\n\nPick a Primary Category:",
            primaries,
            message_id,
            back_label=_BACK_LABEL,
        )

    async def _ask_secondary(self, session: Session, message_id: int) -> None:
        assert session.primary is not None
        secondaries = self._engine.list_secondaries(session.primary)
        if not secondaries:
            await self._abort(session, f"No Secondary Categories under {session.primary!r}.")
            return
        await self._show(
            session,
            Step.SECONDARY,
            f"{self._details(session)}\n\nPrimary: {session.primary}\nPick a Secondary Category:",
            secondaries,
            message_id,
            back_label=_BACK_LABEL,
        )

    async def _ask_merchant_substring(self, session: Session, message_id: int) -> None:
        # With no candidates the prompt still appears (Skip + Back only), so the
        # Secondary choice can be undone like every other non-final step.
        candidates = self._engine.suggest_merchant_substrings(session.transaction.description)
        session.selected = []
        await self._show(
            session,
            Step.MERCHANT,
            self._merchant_text(session, candidates),
            candidates,
            message_id,
            done_label=None,  # Done appears only once ≥1 word is picked
            skip_label=_MERCHANT_SKIP_LABEL,
            back_label=_BACK_LABEL,
        )

    async def _render_merchant(self, session: Session, message_id: int) -> None:
        """Re-draw the merchant prompt in place after a word is toggled."""
        done_label = None
        if session.selected:
            done_label = f"✓ Done → {AND_SEPARATOR.join(w.lower() for w in session.selected)}"
        await self._presenter.edit_options(
            self._chat_id,
            message_id,
            self._merchant_text(session, session.options),
            self._merchant_labels(session),
            tag=Step.MERCHANT.value,
            done_label=done_label,
            skip_label=_MERCHANT_SKIP_LABEL,
            back_label=_BACK_LABEL,
        )

    def _merchant_labels(self, session: Session) -> list[str]:
        """Candidate words, checkmarked when selected. Order matches ``session.options``
        so callback indices stay stable across re-renders (safe against stale taps)."""
        return [f"✓ {word}" if word in session.selected else word for word in session.options]

    def _merchant_text(self, session: Session, candidates: list[str]) -> str:
        header = f"{self._details(session)}\n\n{session.primary} / {session.secondary}"
        if not candidates:
            return (
                f"{header}\nNo word in the description can become a rule. "
                "Skip to categorize this one without a rule — or Back."
            )
        if session.selected:
            rule = AND_SEPARATOR.join(w.lower() for w in session.selected)
            return f"{header}\nRule so far: {rule}\nTap words to add/remove, then Done — or Skip."
        return (
            f"{header}\nTap the word(s) that identify this merchant, then Done — "
            "or Skip to categorize this one without a rule."
        )

    async def _ask_ignore_pattern(self, session: Session, message_id: int) -> None:
        # With no candidates the prompt still appears (Skip + Back only), so the
        # Ignore choice can be undone.
        candidates = self._engine.suggest_ignore_patterns(session.transaction.description)
        if candidates:
            question = "Pick a word to ignore on future transactions — or Skip to ignore just this one."
        else:
            question = (
                "No word in the description can become an ignore pattern. "
                "Skip to ignore just this one — or Back."
            )
        await self._show(
            session,
            Step.IGNORE,
            f"{self._details(session, with_month=False)}\n\n{question}",
            candidates,
            message_id,
            skip_label=_IGNORE_SKIP_LABEL,
            back_label=_BACK_LABEL,
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
                sheet_month=session.month if session.moved else None,
            )
        )
        self._state.mark_processed(txn.id)  # FR-13 (after the write, DD-3)
        self._clear(session)

        rule_line = f"Rule added: “{substring.lower()}”" if substring else "No reusable rule was added."
        await self._safe_notify(
            f"✅ Categorized “{txn.description}”\n"
            f"Category: {session.primary} / {session.secondary}\n"
            f"{self._month_line(session)}\n{rule_line}"
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
