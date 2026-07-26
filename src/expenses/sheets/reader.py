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
        """Read Support!A:C → one SupportRow per category row (blank rows skipped)."""
        values = self._get(a1_range(self._support_sheet, "A:C"))
        rows: list[SupportRow] = []
        for row in values:
            primary = (row[0] if len(row) > 0 else "").strip()
            secondary = (row[1] if len(row) > 1 else "").strip()
            if not primary and not secondary:
                continue  # spacer / empty row
            substrings = _split_substrings(row[2] if len(row) > 2 else "")
            rows.append(SupportRow(primary=primary, secondary=secondary, substrings=substrings))
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
