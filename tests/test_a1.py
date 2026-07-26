"""A1 range quoting."""

from __future__ import annotations

from expenses.sheets.a1 import a1_range


def test_quotes_sheet_name():
    assert a1_range("Support", "A:C") == "'Support'!A:C"


def test_quotes_names_with_spaces():
    assert a1_range("Ignore", "A:A") == "'Ignore'!A:A"


def test_escapes_internal_single_quotes():
    assert a1_range("O'Brien", "A1") == "'O''Brien'!A1"
