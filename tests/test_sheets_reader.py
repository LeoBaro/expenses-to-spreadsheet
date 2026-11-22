"""SheetsReader tests (mocked Google API resource).

The real Support and Ignore sheets have no header rows — every row is data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from expenses.sheets.reader import SheetsReader, support_table


def _api_returning(values):
    api = MagicMock()
    api.values.return_value.get.return_value.execute.return_value = {"values": values}
    return api


def test_load_support_parses_all_rows_no_header():
    api = _api_returning(
        [
            ["Housing", "Electricity", "nwg, sorgenia"],
            ["Groceries", "Groceries general", "coop, conad, carrefour"],
            ["Relax", "Subscriptions"],  # no Column C
            ["Relax"],  # unused Secondary slot in the block
        ]
    )
    reader = SheetsReader(api, "sid")

    rows = reader.load_support()

    assert len(rows) == 4
    assert rows[0].primary == "Housing"
    assert rows[0].secondary == "Electricity"
    assert rows[0].substrings == ["nwg", "sorgenia"]
    assert rows[1].substrings == ["coop", "conad", "carrefour"]
    assert rows[2].primary == "Relax"
    assert rows[2].substrings == []  # empty Column C
    assert (rows[3].primary, rows[3].secondary) == ("Relax", "")


def test_load_support_stops_at_first_blank_row():
    # Mirrors the real sheet: the category table, a gap of blank rows, then a
    # Necessary / Lifestyle / Investments grouping table that is NOT categories.
    api = _api_returning(
        [
            ["Housing", "Rent", "ferrari"],
            ["Out", "Bar/Restaurants", "bar"],
            [],
            [],
            ["Necessary", "Lifestyle", "Investments"],
            ["Housing", "Out", "Savings"],
            ["Health", "Travel"],
        ]
    )
    rows = SheetsReader(api, "sid").load_support()

    assert [(r.primary, r.secondary) for r in rows] == [("Housing", "Rent"), ("Out", "Bar/Restaurants")]


def test_support_table_treats_whitespace_only_row_as_blank():
    values = [["Housing", "Rent"], ["  ", " ", "stray"], ["Housing", "Out"]]
    assert support_table(values) == [["Housing", "Rent"]]


def test_support_table_without_blank_row_keeps_everything():
    values = [["Housing", "Rent"], ["Out", "Bar"]]
    assert support_table(values) == values


def test_load_ignore_patterns_keeps_all_rows_drops_empties():
    # "Revolut" is a real ignore pattern, not a header.
    api = _api_returning([["Revolut"], ["amazon prime"], [""], ["netflix"]])
    reader = SheetsReader(api, "sid")

    assert reader.load_ignore_patterns() == ["Revolut", "amazon prime", "netflix"]
