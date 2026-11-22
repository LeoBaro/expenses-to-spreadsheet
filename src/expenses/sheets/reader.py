"""Reads the Support and Ignore sheets (FR-2), feeding the cache (TR-5).

Synchronous — the Google API client is sync; the async facade
(``GoogleSheetsClient``) bridges it off the event loop.
"""

from __future__ import annotations

import logging

from expenses.sheets._api import get_values
from expenses.sheets.a1 import a1_range
from expenses.sheets.models import SupportRow

logger = logging.getLogger(__name__)


def _split_substrings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _cell(row: list[str], index: int) -> str:
    return (row[index] if len(row) > index else "").strip()


def support_table(values: list[list[str]]) -> list[list[str]]:
    """The category table at the top of the Support sheet: every row up to (not
    including) the first row whose Primary and Secondary cells are both blank.

    The sheet holds other tables further down (e.g. a Necessary / Lifestyle /
    Investments grouping of the Primary Categories), separated from the category table
    by blank rows. Reading past the first blank row would turn those into bogus
    categories and merchant rules. Row indices are preserved (only the tail is cut), so
    callers can still map an index back to a sheet row.
    """
    for index, row in enumerate(values):
        if not _cell(row, 0) and not _cell(row, 1):
            ignored = sum(1 for r in values[index:] if _cell(r, 0) or _cell(r, 1))
            if ignored:
                logger.debug(
                    "Support category table ends at row %d; ignoring %d non-blank rows below it",
                    index,
                    ignored,
                )
            return values[:index]
    return values


class SheetsReader:
    def __init__(
        self,
        spreadsheets,
        spreadsheet_id: str,
        *,
        support_sheet: str = "Support",
        ignore_sheet: str = "Ignore",
    ) -> None:
        self._api = spreadsheets  # a googleapiclient spreadsheets() resource
        self._sid = spreadsheet_id
        self._support_sheet = support_sheet
        self._ignore_sheet = ignore_sheet

    def load_support(self) -> list[SupportRow]:
        """Read Support!A:C → one SupportRow per row of the category table (which ends
        at the first blank row — see ``support_table``)."""
        values = self._get(a1_range(self._support_sheet, "A:C"))
        rows: list[SupportRow] = []
        for row in support_table(values):
            rows.append(
                SupportRow(
                    primary=_cell(row, 0),
                    secondary=_cell(row, 1),
                    substrings=_split_substrings(row[2] if len(row) > 2 else ""),
                )
            )
        return rows

    def load_ignore_patterns(self) -> list[str]:
        """Read the single-column Ignore sheet → list of non-empty patterns."""
        values = self._get(a1_range(self._ignore_sheet, "A:A"))
        patterns: list[str] = []
        for row in values:
            pattern = (row[0] if row else "").strip()
            if pattern:
                patterns.append(pattern)
        return patterns

    def _get(self, cell_range: str) -> list[list[str]]:
        return get_values(self._api, self._sid, cell_range)
