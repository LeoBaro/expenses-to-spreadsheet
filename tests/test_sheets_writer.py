"""SheetsWriter tests (mocked Google API resource)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from expenses.sheets.errors import RuleRowNotFoundError, SheetNotFoundError
from expenses.sheets.models import ExpenseRow
from expenses.sheets.writer import SheetsWriter


def _api(titles=("Jan", "Jul", "Dec"), support_values=None):
    api = MagicMock()
    api.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in titles]
    }
    api.values.return_value.get.return_value.execute.return_value = {"values": support_values or []}
    api.values.return_value.append.return_value.execute.return_value = {}
    api.values.return_value.update.return_value.execute.return_value = {}
    return api


def test_append_expense_writes_numeric_amount_and_iso_date():
    api = _api()
    writer = SheetsWriter(api, "sid")

    writer.append_expense(
        ExpenseRow(
            name="PAGAMENTO CARTA ESSELUNGA MILANO",
            date=date(2026, 7, 25),
            amount=Decimal("12.90"),
            primary="Groceries",
            secondary="Groceries general",
        )
    )

    _, kwargs = api.values.return_value.append.call_args
    assert kwargs["range"] == "'Jul'!A:E"
    assert kwargs["valueInputOption"] == "USER_ENTERED"
    row = kwargs["body"]["values"][0]
    assert row == ["PAGAMENTO CARTA ESSELUNGA MILANO", "2026-07-25", 12.9, "Groceries", "Groceries general"]
    # Amount is a number, not a string (locale-proof).
    assert isinstance(row[2], float)


def test_append_expense_missing_month_sheet_raises():
    api = _api(titles=("Jan", "Feb"))
    writer = SheetsWriter(api, "sid")

    with pytest.raises(SheetNotFoundError):
        writer.append_expense(
            ExpenseRow("x", date(2026, 7, 25), Decimal("1.00"), "P", "S")
        )
    api.values.return_value.append.assert_not_called()


# No header row in the real Support sheet.
_SUPPORT = [
    ["Housing", "Electricity", "nwg, sorgenia"],
    ["Groceries", "Groceries general", "coop, conad"],
]


def test_add_merchant_substring_appends_lowercase_to_column_c():
    api = _api(support_values=_SUPPORT)
    writer = SheetsWriter(api, "sid")

    writer.add_merchant_substring("Groceries", "Groceries general", "Esselunga")

    _, kwargs = api.values.return_value.update.call_args
    assert kwargs["range"] == "'Support'!C2"  # row index 1 → sheet row 2
    assert kwargs["valueInputOption"] == "RAW"
    assert kwargs["body"]["values"] == [["coop, conad, esselunga"]]


def test_add_merchant_substring_dedupes_case_insensitively():
    api = _api(support_values=_SUPPORT)
    writer = SheetsWriter(api, "sid")

    writer.add_merchant_substring("Groceries", "Groceries general", "COOP")

    api.values.return_value.update.assert_not_called()


def test_add_merchant_substring_unknown_category_raises():
    api = _api(support_values=_SUPPORT)
    writer = SheetsWriter(api, "sid")

    with pytest.raises(RuleRowNotFoundError):
        writer.add_merchant_substring("Nope", "Missing", "x")
