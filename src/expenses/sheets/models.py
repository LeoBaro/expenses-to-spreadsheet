"""Read/write contracts for the Google Sheets Client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SupportRow:
    """One row of the Support sheet: a (Primary, Secondary) category and its
    merchant substrings (Column C, comma-separated)."""

    primary: str
    secondary: str
    substrings: list[str]


@dataclass(frozen=True, slots=True)
class ExpenseRow:
    """A row to append to a monthly sheet (FR-12), columns A–E."""

    name: str  # A — original transaction description
    date: date  # B — booking date
    amount: Decimal  # C — positive amount
    primary: str  # D
    secondary: str  # E
