"""Standalone one-shot poll, used to validate TR-1's open questions against the
real Enable Banking API.

Run (after configuring .env):  ``uv run expenses-poll``

By default it fetches the same rolling lookback window the scheduler uses. Pass
``--month YYYY-MM`` to inspect a specific calendar month instead, or ``--from``/``--to``
(``YYYY-MM-DD``, both required together) for an arbitrary range — e.g. to check what
the provider has for a past month before deciding whether/how to backfill it.

This is read-only diagnostics: it prints what Enable Banking returns and does **not**
go through the Transaction Processor — nothing is categorized, written to a sheet,
notified over Telegram, or marked processed.

Besides exercising the full poll path, it reports the *distinct* raw values of the
fields TR-1 left to confirm — credit/debit indicators, statuses, currencies — and
how many transactions lacked a stable provider id. That output is exactly what
answers the open questions.
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import logging
from collections import Counter
from datetime import date, timedelta

import httpx

from expenses.config import Settings
from expenses.poller.enable_banking import adapter
from expenses.poller.enable_banking.auth import EnableBankingAuth
from expenses.poller.enable_banking.gateway import EnableBankingGateway

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Fetch this calendar month instead of the rolling lookback window.",
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        metavar="YYYY-MM-DD",
        help="Range start (inclusive). Must be given together with --to.",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        metavar="YYYY-MM-DD",
        help="Range end (inclusive). Must be given together with --from.",
    )
    return parser.parse_args()


def _resolve_window(args: argparse.Namespace, settings: Settings) -> tuple[date, date]:
    if args.month and (args.date_from or args.date_to):
        raise SystemExit("--month cannot be combined with --from/--to.")

    if args.month:
        try:
            year, month = (int(part) for part in args.month.split("-", 1))
        except ValueError:
            raise SystemExit("--month must be in YYYY-MM format.") from None
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            raise SystemExit("--from and --to must be given together.")
        return date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)

    today = date.today()
    return today - timedelta(days=settings.poll_lookback_days), today


async def _run(args: argparse.Namespace) -> None:
    settings = Settings()
    if not settings.eb_account_uid:
        raise SystemExit(
            "EXPENSES_EB_ACCOUNT_UID is not set. Complete the one-time consent flow "
            "(POST /sessions) to obtain an account UID first."
        )

    auth = EnableBankingAuth(settings.eb_application_id, settings.private_key())
    date_from, date_to = _resolve_window(args, settings)

    indicators: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    fetched = derived_ids = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        gateway = EnableBankingGateway(client, auth, settings.eb_api_base_url)
        # No server-side status filter here so we can observe every status value.
        async for raw in gateway.iter_transactions(settings.eb_account_uid, date_from, date_to):
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
    print(f"window                 : {date_from} .. {date_to}")
    print(f"transactions fetched   : {fetched}")
    print(f"credit_debit_indicator : {dict(indicators)}")
    print(f"status values          : {dict(statuses)}")
    print(f"currencies             : {dict(currencies)}")
    print(f"expected currency      : {settings.expected_currency}")
    print(f"missing provider id    : {derived_ids} (used derived ids)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
