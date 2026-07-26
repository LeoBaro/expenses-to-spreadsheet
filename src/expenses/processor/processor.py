"""The Transaction Processor — automatic path (TR-2)."""

from __future__ import annotations

import logging

from expenses.categorization.models import MatchResult
from expenses.domain.transaction import Transaction
from expenses.processor.ports import (
    Engine,
    ExpenseWriter,
    Notifier,
    ProcessedState,
    UnknownTransactionHandler,
)
from expenses.sheets.models import ExpenseRow

logger = logging.getLogger(__name__)


def format_categorized(transaction: Transaction, match: MatchResult) -> str:
    """FR-5 notification content."""
    return (
        "✅ Expense categorized\n"
        f"Amount: {transaction.amount} {transaction.currency}\n"
        f"Date: {transaction.booking_date.isoformat()}\n"
        f"Description: {transaction.description}\n"
        f"Category: {match.primary} / {match.secondary}"
    )


class TransactionProcessor:
    """Orchestrates one transaction. Implements the poller's ``TransactionSink``
    (`handle`), so the poller forwards directly to it."""

    def __init__(
        self,
        engine: Engine,
        sheets: ExpenseWriter,
        state: ProcessedState,
        notifier: Notifier,
        unknown_handler: UnknownTransactionHandler,
    ) -> None:
        self._engine = engine
        self._sheets = sheets
        self._state = state
        self._notifier = notifier
        self._unknown = unknown_handler

    async def handle(self, transaction: Transaction) -> None:
        # Authoritative idempotency guard (the poller's check is only an optimization).
        if self._state.is_processed(transaction.id):
            logger.debug("already processed, skipping: %s", transaction.id)
            return

        # FR-4: ignore patterns are evaluated before merchant rules.
        ignore_pattern = self._engine.find_ignore_match(transaction.description)
        if ignore_pattern is not None:
            logger.info("ignore pattern %r matched → skipping %s", ignore_pattern, transaction.id)
            self._state.mark_processed(transaction.id)  # no write, no notification (FR-4)
            return

        # FR-5: automatic categorization on a merchant-rule match.
        match = self._engine.match_merchant(transaction.description)
        if match is not None:
            await self._categorize(transaction, match)
            return

        # FR-6: unknown merchant → interactive workflow (delegated).
        await self._unknown.handle_unknown(transaction)

    async def _categorize(self, transaction: Transaction, match: MatchResult) -> None:
        expense = ExpenseRow(
            name=transaction.description,
            date=transaction.booking_date,
            amount=transaction.amount,
            primary=match.primary,
            secondary=match.secondary,
        )
        # Ordering (DD-3): write the expense, then mark processed. A crash in between
        # re-processes the transaction next cycle (accepted at-least-once window).
        await self._sheets.append_expense(expense)  # FR-12
        self._state.mark_processed(transaction.id)  # FR-13
        logger.info(
            "categorized %s → %s / %s", transaction.id, match.primary, match.secondary
        )

        # FR-5 notification is best-effort and happens after mark, so a failure never
        # causes reprocessing.
        try:
            await self._notifier.notify(format_categorized(transaction, match))
        except Exception:  # noqa: BLE001 - informational notification must not break the flow
            logger.exception("notification failed (ignored)")
