"""Shared Sheets read helper that turns Google's cryptic range-parse 400 into a
clear error naming the likely cause (a missing/mis-named tab)."""

from __future__ import annotations

from expenses.sheets.errors import SheetNotFoundError


def get_values(spreadsheets, spreadsheet_id: str, cell_range: str) -> list[list[str]]:
    from googleapiclient.errors import HttpError

    try:
        response = (
            spreadsheets.values().get(spreadsheetId=spreadsheet_id, range=cell_range).execute()
        )
    except HttpError as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if status == 400 and "Unable to parse range" in str(exc):
            raise SheetNotFoundError(
                f"Could not read {cell_range!r}: no tab with that name exists in the "
                f"spreadsheet. Check the exact tab name (case/space-sensitive) and the "
                f"matching EXPENSES_*_SHEET_NAME setting in your .env."
            ) from exc
        raise
    return response.get("values", [])
