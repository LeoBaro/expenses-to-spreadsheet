"""Ports the poller depends on, kept as Protocols so TR-1 stays decoupled from
TR-7 (State Manager) and TR-2 (Transaction Processor)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from expenses.domain.transaction import Transaction


@runtime_checkable
class ProcessedStore(Protocol):
    """Provided by the State Manager (TR-7)."""

    def is_processed(self, transaction_id: str) -> bool: ...


@runtime_checkable
class TransactionSink(Protocol):
    """Provided by the Transaction Processor (TR-2). Receives new transactions."""

    async def handle(self, transaction: Transaction) -> None: ...
