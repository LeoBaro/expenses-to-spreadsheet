"""Month-sheet naming (FR-12)."""

from __future__ import annotations

from datetime import date

from expenses.sheets.months import month_sheet_name


def test_month_sheet_names():
    assert month_sheet_name(date(2026, 1, 1)) == "Jan"
    assert month_sheet_name(date(2026, 7, 25)) == "Jul"
    assert month_sheet_name(date(2026, 12, 31)) == "Dec"
