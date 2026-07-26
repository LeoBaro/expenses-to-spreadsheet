"""Transaction Processor (TR-2).

The sole orchestrator. This module implements the **automatic path** (FR-1/4/5):
idempotency check → ignore-pattern check → merchant match → write expense + mark
processed + notify. Unknown transactions are delegated to an
``UnknownTransactionHandler`` (the interactive FR-6→8 workflow arrives in a later slice).
"""

from expenses.processor.ports import (
    Engine,
    ExpenseWriter,
    LoggingNotifier,
    LoggingUnknownHandler,
    Notifier,
    ProcessedState,
    UnknownTransactionHandler,
)
from expenses.processor.processor import TransactionProcessor, format_categorized

__all__ = [
    "TransactionProcessor",
    "format_categorized",
    "Engine",
    "ExpenseWriter",
    "ProcessedState",
    "Notifier",
    "UnknownTransactionHandler",
    "LoggingNotifier",
    "LoggingUnknownHandler",
]
