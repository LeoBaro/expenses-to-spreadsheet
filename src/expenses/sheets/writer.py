"""Writes expenses (FR-12) and merchant substrings (FR-11) to Google Sheets.

Append-only, except the Support Column C read-modify-write for FR-11. Synchronous;
the async facade bridges it off the event loop.
"""

from __future__ import annotations

import logging

from expenses.sheets._api import get_values
from expenses.sheets.a1 import a1_range
from expenses.sheets.errors import RuleRowNotFoundError, SheetNotFoundError
from expenses.sheets.models import ExpenseRow
from expenses.sheets.months import month_sheet_name

logger = logging.getLogger(__name__)


class SheetsWriter:
    def __init__(self, spreadsheets, spreadsheet_id: str, *, support_sheet: str = "Support") -> None:
        self._api = spreadsheets
        self._sid = spreadsheet_id
        self._support_sheet = support_sheet
        self._sheet_titles: set[str] | None = None

    def append_expense(self, expense: ExpenseRow) -> None:
        """Append a row to the monthly sheet derived from the booking date (FR-12)."""
        sheet = month_sheet_name(expense.date)
        self._ensure_sheet_exists(sheet)
        # USER_ENTERED so the ISO date parses to a real date; amount is sent as a
        # numeric value (locale-proof — a number is stored as a number).
        row = [
            expense.name,
            expense.date.isoformat(),
            float(expense.amount),
            expense.primary,
            expense.secondary,
        ]
        self._api.values().append(
            spreadsheetId=self._sid,
            range=a1_range(sheet, "A:E"),
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info("appended expense to %s: %s %s", sheet, expense.amount, expense.name[:40])

    def add_merchant_substring(self, primary: str, secondary: str, substring: str) -> None:
        """Append a substring to the Support row's Column C list (FR-11).

        Stored lowercase; duplicates (case-insensitive) are not inserted.
        """
        normalized = substring.strip().lower()
        if not normalized:
            raise ValueError("substring is empty")

        values = self._get(a1_range(self._support_sheet, "A:C"))
        row_index = self._find_rule_row(values, primary, secondary)  # 0-based

        raw_c = values[row_index][2] if len(values[row_index]) > 2 else ""
        existing = [part.strip() for part in raw_c.split(",") if part.strip()]
        if normalized in {part.lower() for part in existing}:
            logger.info("substring %r already present for %s/%s", normalized, primary, secondary)
            return

        existing.append(normalized)
        cell = a1_range(self._support_sheet, f"C{row_index + 1}")  # +1: sheet rows 1-based
        self._api.values().update(
            spreadsheetId=self._sid,
            range=cell,
            valueInputOption="RAW",
            body={"values": [[", ".join(existing)]]},
        ).execute()
        logger.info("added substring %r to %s/%s", normalized, primary, secondary)

    def _find_rule_row(self, values: list[list[str]], primary: str, secondary: str) -> int:
        target_primary, target_secondary = primary.strip(), secondary.strip()
        for index, row in enumerate(values):
            row_primary = (row[0] if len(row) > 0 else "").strip()
            row_secondary = (row[1] if len(row) > 1 else "").strip()
            if row_primary == target_primary and row_secondary == target_secondary:
                return index
        raise RuleRowNotFoundError(f"no Support row for {primary!r} / {secondary!r}")

    def _ensure_sheet_exists(self, title: str) -> None:
        if self._sheet_titles is None or title not in self._sheet_titles:
            self._sheet_titles = self._load_sheet_titles()  # refresh once on miss
        if title not in self._sheet_titles:
            raise SheetNotFoundError(f"month sheet {title!r} does not exist")

    def _load_sheet_titles(self) -> set[str]:
        meta = self._api.get(spreadsheetId=self._sid, fields="sheets.properties.title").execute()
        return {s["properties"]["title"] for s in meta.get("sheets", [])}

    def _get(self, cell_range: str) -> list[list[str]]:
        return get_values(self._api, self._sid, cell_range)
