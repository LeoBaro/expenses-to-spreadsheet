"""Google Sheets CLI.

- ``uv run expenses-sheets check``       read-only: validate auth + reads.
- ``uv run expenses-sheets write-test``  writes ONE clearly-labelled test expense to
  the current month sheet (FR-12 write-path check). Safe to delete afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date
from decimal import Decimal

from expenses.config import Settings
from expenses.sheets.client import GoogleSheetsClient
from expenses.sheets.models import ExpenseRow
from expenses.sheets.months import month_sheet_name

logger = logging.getLogger(__name__)


async def _check(settings: Settings) -> None:
    client = GoogleSheetsClient.from_settings(settings)

    support = await client.load_support()
    ignore = await client.load_ignore_patterns()

    primaries = sorted({row.primary for row in support if row.primary})
    rules_with_substrings = sum(1 for row in support if row.substrings)

    print("=== Support sheet ===")
    print(f"rows                : {len(support)}")
    print(f"primary categories  : {len(primaries)}  {primaries}")
    print(f"rows with substrings: {rules_with_substrings}")
    for row in support[:10]:
        print(f"  {row.primary} / {row.secondary}: {row.substrings}")
    if len(support) > 10:
        print(f"  … and {len(support) - 10} more")

    print("\n=== Ignore ===")
    print(f"patterns            : {len(ignore)}  {ignore}")


async def _write_test(settings: Settings) -> None:
    client = GoogleSheetsClient.from_settings(settings)
    today = date.today()
    expense = ExpenseRow(
        name="TEST — expenses_to_spreadsheet write check (safe to delete)",
        date=today,
        amount=Decimal("0.01"),
        primary="Housing",
        secondary="Rent",
    )
    print(f"Appending test expense to sheet {month_sheet_name(today)!r}: {expense}")
    await client.append_expense(expense)
    print("Done. Check the month sheet and delete the row if you wish.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="expenses-sheets", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="read Support + Ignore sheets and print a summary (no writes)")
    sub.add_parser("write-test", help="append ONE labelled test expense to the current month (writes!)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.command == "check":
        asyncio.run(_check(Settings()))
    elif args.command == "write-test":
        asyncio.run(_write_test(Settings()))


if __name__ == "__main__":
    main()
