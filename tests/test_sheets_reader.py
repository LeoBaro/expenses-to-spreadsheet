"""SheetsReader tests (mocked Google API resource).

The real Support and Ignore sheets have no header rows — every row is data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from expenses.sheets.reader import SheetsReader


def _api_returning(values):
    api = MagicMock()
    api.values.return_value.get.return_value.execute.return_value = {"values": values}
    return api


def test_load_support_parses_all_rows_no_header():
    api = _api_returning(
        [
            ["Housing", "Electricity", "nwg, sorgenia"],
            ["Groceries", "Groceries general", "coop, conad, carrefour"],
            ["", "", ""],  # blank spacer row (skipped)
            ["Relax", "Subscriptions"],  # no Column C
        ]
    )
    reader = SheetsReader(api, "sid")

    rows = reader.load_support()

    assert len(rows) == 3
    assert rows[0].primary == "Housing"
    assert rows[0].secondary == "Electricity"
    assert rows[0].substrings == ["nwg", "sorgenia"]
    assert rows[1].substrings == ["coop", "conad", "carrefour"]
    assert rows[2].primary == "Relax"
    assert rows[2].substrings == []  # empty Column C


def test_load_ignore_patterns_keeps_all_rows_drops_empties():
    # "Revolut" is a real ignore pattern, not a header.
    api = _api_returning([["Revolut"], ["amazon prime"], [""], ["netflix"]])
    reader = SheetsReader(api, "sid")

    assert reader.load_ignore_patterns() == ["Revolut", "amazon prime", "netflix"]
