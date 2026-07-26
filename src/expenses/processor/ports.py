"""Ports the Processor orchestrates through (kept as Protocols so TR-2 stays decoupled
from the concrete TR-3/4/5/6/7 implementations)."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from expenses.categorization.models import MatchResult
from expenses.domain.transaction import Transaction
from expenses.sheets.models import ExpenseRow

logger = logging.getLogger(__name__)


@runtime_checkable
class Engine(Protocol):
    """Categorization Engine (TR-3) — the parts the automatic path needs."""

    def find_ignore_match(self, description: str) -> str | None: ...
    def match_merchant(self, description: str) -> MatchResult | None: ...


@runtime_checkable
class ExpenseWriter(Protocol):
    """Google Sheets Client (TR-4)."""

    async def append_expense(self, expense: ExpenseRow) -> None: ...


@runtime_checkable
class ProcessedState(Protocol):
    """State Manager (TR-7)."""

    def is_processed(self, transaction_id: str) -> bool: ...
    def mark_processed(self, transaction_id: str) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Sends an informational notification (FR-5). Implemented by a Telegram adapter."""

    async def notify(self, text: str) -> None: ...


@runtime_checkable
class UnknownTransactionHandler(Protocol):
    """Handles a transaction that matched no rule (FR-6 → interactive workflow)."""

    async def handle_unknown(self, transaction: Transaction) -> None: ...


class LoggingNotifier:
    """Default notifier: logs instead of messaging. Replaced by a Telegram adapter."""

    async def notify(self, text: str) -> None:
        logger.info("NOTIFY:\n%s", text)


class LoggingUnknownHandler:
    """Slice-1 placeholder for the interactive workflow. Logs and, crucially, does
    **not** mark the transaction processed — so it is revisited once the FR-6→8
    workflow exists. No notification, to avoid re-spamming every poll cycle."""

    async def handle_unknown(self, transaction: Transaction) -> None:
        logger.info(
            "UNKNOWN transaction (needs manual categorization): %s  %s %s  %s",
            transaction.booking_date,
            transaction.amount,
            transaction.currency,
            transaction.description,
        )
