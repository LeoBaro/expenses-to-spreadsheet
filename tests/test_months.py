"""Month-sheet naming (FR-12)."""

from __future__ import annotations

from datetime import date

import pytest

from expenses.sheets.months import month_name, month_sheet_name


def test_month_sheet_names():
    assert month_sheet_name(date(2026, 1, 1)) == "Jan"
    assert month_sheet_name(date(2026, 7, 25)) == "Jul"
    assert month_sheet_name(date(2026, 12, 31)) == "Dec"


def test_month_name_by_number():
    assert month_name(1) == "Jan" and month_name(12) == "Dec"
    with pytest.raises(ValueError):
        month_name(13)
