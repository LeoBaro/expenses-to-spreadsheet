"""Standalone one-shot poll, used to validate TR-1's open questions against the
real Enable Banking API.

Run (after configuring .env):  ``uv run expenses-poll``

Besides exercising the full poll path, it reports the *distinct* raw values of the
fields TR-1 left to confirm — credit/debit indicators, statuses, currencies — and
how many transactions lacked a stable provider id. That output is exactly what
answers the open questions.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, timedelta

import httpx

from expenses.config import Settings
from expenses.poller.enable_banking import adapter
from expenses.poller.enable_banking.auth import EnableBankingAuth
from expenses.poller.enable_banking.gateway import EnableBankingGateway

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = Settings()
    if not settings.eb_account_uid:
        raise SystemExit(
            "EXPENSES_EB_ACCOUNT_UID is not set. Complete the one-time consent flow "
            "(POST /sessions) to obtain an account UID first."
        )

    auth = EnableBankingAuth(settings.eb_application_id, settings.private_key())
    today = date.today()
    date_from = today - timedelta(days=settings.poll_lookback_days)

    indicators: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    fetched = derived_ids = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        gateway = EnableBankingGateway(client, auth, settings.eb_api_base_url)
        # No server-side status filter here so we can observe every status value.
        async for raw in gateway.iter_transactions(settings.eb_account_uid, date_from, today):
            fetched += 1
            indicators[str(raw.get("credit_debit_indicator"))] += 1
            statuses[str(raw.get("status"))] += 1
            amount_obj = raw.get("transaction_amount") or {}
            currencies[str(amount_obj.get("currency"))] += 1

            transaction = adapter.to_transaction(raw)
            if transaction.id_is_derived:
                derived_ids += 1
            print(
                f"{transaction.booking_date}  {transaction.direction.value:<7} "
                f"{transaction.status.value:<7} {transaction.amount} {transaction.currency}  "
                f"{transaction.description}"
            )

    print("\n=== TR-1 open-question findings ===")
    print(f"window                 : {date_from} .. {today}")
    print(f"transactions fetched   : {fetched}")
    print(f"credit_debit_indicator : {dict(indicators)}")
    print(f"status values          : {dict(statuses)}")
    print(f"currencies             : {dict(currencies)}")
    print(f"expected currency      : {settings.expected_currency}")
    print(f"missing provider id    : {derived_ids} (used derived ids)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
