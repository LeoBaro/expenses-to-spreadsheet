"""Trivial in-process implementations of the poller's ports, for the standalone
poll CLI and tests. Real implementations arrive with TR-7 and TR-2."""

from __future__ import annotations

import logging

from expenses.domain.transaction import Transaction

logger = logging.getLogger(__name__)


class InMemoryProcessedStore:
    """Stand-in for the State Manager (TR-7). Nothing persisted."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_processed(self, transaction_id: str) -> bool:
        return transaction_id in self._seen

    def mark_processed(self, transaction_id: str) -> None:
        self._seen.add(transaction_id)


class LoggingSink:
    """Stand-in for the Transaction Processor (TR-2). Prints what it receives."""

    async def handle(self, transaction: Transaction) -> None:
        logger.info(
            "NEW EXPENSE  %s  %s %s  %s%s",
            transaction.booking_date,
            transaction.amount,
            transaction.currency,
            transaction.description,
            "  [derived-id]" if transaction.id_is_derived else "",
        )
