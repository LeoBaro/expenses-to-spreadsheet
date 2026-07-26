"""Google Sheets Client (TR-4).

The only component that talks to Google Sheets. Encapsulates the fixed spreadsheet
layout (Support A/B/C, Ignore, monthly Jan–Dec sheets) behind a typed API.

Internal parts (see TR-4 System Decomposition):
- ``client``  — service-account authenticated Sheets API resource.
- ``reader``  — load Support & Ignore sheets (feeds the Cache, TR-5).
- ``writer``  — append expenses (FR-12) and merchant substrings (FR-11).
- ``GoogleSheetsClient`` — async facade wrapping the sync API off the event loop.
"""

from expenses.sheets.client import GoogleSheetsClient
from expenses.sheets.errors import RuleRowNotFoundError, SheetNotFoundError, SheetsError
from expenses.sheets.models import ExpenseRow, SupportRow

__all__ = [
    "GoogleSheetsClient",
    "ExpenseRow",
    "SupportRow",
    "SheetsError",
    "SheetNotFoundError",
    "RuleRowNotFoundError",
]
