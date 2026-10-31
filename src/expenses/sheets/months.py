"""Monthly-sheet naming (FR-12).

Sheet names are the fixed English three-letter month abbreviations (Jan…Dec), per
spreadsheet-structure.md. Hard-coded rather than derived from ``calendar`` because
``calendar.month_abbr`` is locale-dependent (would yield "lug" under an Italian locale).
"""

from __future__ import annotations

from datetime import date

MONTH_SHEETS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def month_name(month: int) -> str:
    """Sheet name for a month number (1–12)."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1–12, got {month!r}")
    return MONTH_SHEETS[month - 1]


def month_sheet_name(booking_date: date) -> str:
    return month_name(booking_date.month)
