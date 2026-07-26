"""A1-notation range helpers.

Sheet names containing spaces or special characters must be single-quoted in A1
notation (e.g. ``'Ignore'!A:A``); internal single quotes are escaped by
doubling. Quoting names that don't need it is harmless, so we always quote.
"""

from __future__ import annotations


def a1_range(sheet_name: str, cells: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!{cells}"
