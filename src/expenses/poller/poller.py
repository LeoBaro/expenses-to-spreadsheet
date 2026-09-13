"""Transaction Poller orchestration (TR-1).

One poll cycle: fetch from Enable Banking -> map -> drop non-expense and
already-processed transactions -> hand new ones to the sink (TR-2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from expenses.poller.enable_banking import adapter
from expenses.poller.enable_banking.gateway import EnableBankingGateway
from expenses.poller.ports import ProcessedStore, TransactionSink

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollResult:
    fetched: int = 0
    forwarded: int = 0
    skipped_not_expense: int = 0
    skipped_processed: int = 0
    mapping_errors: int = 0


class TransactionPoller:
    def __init__(
        self,
        gateway: EnableBankingGateway,
        processed: ProcessedStore,
        sink: TransactionSink,
        *,
        account_uid: str,
        lookback_days: int = 7,
        transaction_status: str | None = "BOOK",
    ) -> None:
        self._gateway = gateway
        self._processed = processed
        self._sink = sink
        self._account_uid = account_uid
        self._lookback_days = lookback_days
        self._transaction_status = transaction_status

    async def poll_once(self, *, today: date | None = None) -> PollResult:
        today = today or date.today()
        date_from = today - timedelta(days=self._lookback_days)

        fetched = forwarded = skipped_not_expense = skipped_processed = mapping_errors = 0

        async for raw in self._gateway.iter_transactions(
            self._account_uid, date_from, today, transaction_status=self._transaction_status
        ):
            fetched += 1
            try:
                transaction = adapter.to_transaction(raw)
            except adapter.TransactionMappingError:
                mapping_errors += 1
                logger.exception("skipping unmappable transaction")
                continue

            # FR-1: only settled, debit, positive-amount transactions represent expenses.
            if not adapter.is_expense(transaction):
                skipped_not_expense += 1
                continue

            # Early idempotency drop; TR-2/TR-7 remain the authoritative guard.
            if self._processed.is_processed(transaction.id):
                skipped_processed += 1
                continue

            await self._sink.handle(transaction)
            forwarded += 1

        result = PollResult(
            fetched=fetched,
            forwarded=forwarded,
            skipped_not_expense=skipped_not_expense,
            skipped_processed=skipped_processed,
            mapping_errors=mapping_errors,
        )
        logger.info("poll cycle complete: %s", result)
        return result
