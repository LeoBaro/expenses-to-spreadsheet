"""Service-account authentication and the async GoogleSheetsClient facade."""

from __future__ import annotations

import asyncio
from pathlib import Path

from expenses.sheets.models import ExpenseRow, SupportRow
from expenses.sheets.reader import SheetsReader
from expenses.sheets.writer import SheetsWriter

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def build_sheets_resource(credentials_path: str | Path):
    """Build an authenticated googleapiclient ``spreadsheets()`` resource.

    NOTE: the spreadsheet must be *shared* with the service account's client_email
    (Editor); a project IAM role alone does not grant document access.
    """
    from google.oauth2 import service_account  # imported lazily to keep import cost low
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return service.spreadsheets()


class GoogleSheetsClient:
    """Async facade over the synchronous Reader/Writer.

    The Google API client is blocking, so every call is dispatched to a worker
    thread — the FastAPI event loop is never blocked.
    """

    def __init__(self, reader: SheetsReader, writer: SheetsWriter) -> None:
        self._reader = reader
        self._writer = writer

    @classmethod
    def from_settings(cls, settings) -> "GoogleSheetsClient":
        if settings.google_credentials_path is None:
            raise ValueError("EXPENSES_GOOGLE_CREDENTIALS_PATH is not configured")
        if not settings.google_spreadsheet_id:
            raise ValueError("EXPENSES_GOOGLE_SPREADSHEET_ID is not configured")

        spreadsheets = build_sheets_resource(settings.google_credentials_path)
        reader = SheetsReader(
            spreadsheets,
            settings.google_spreadsheet_id,
            support_sheet=settings.support_sheet_name,
            ignore_sheet=settings.ignore_sheet_name,
        )
        writer = SheetsWriter(
            spreadsheets,
            settings.google_spreadsheet_id,
            support_sheet=settings.support_sheet_name,
            ignore_sheet=settings.ignore_sheet_name,
        )
        return cls(reader, writer)

    async def load_support(self) -> list[SupportRow]:
        return await asyncio.to_thread(self._reader.load_support)

    async def load_ignore_patterns(self) -> list[str]:
        return await asyncio.to_thread(self._reader.load_ignore_patterns)

    async def append_expense(self, expense: ExpenseRow) -> None:
        await asyncio.to_thread(self._writer.append_expense, expense)

    async def add_merchant_substring(self, primary: str, secondary: str, substring: str) -> None:
        await asyncio.to_thread(self._writer.add_merchant_substring, primary, secondary, substring)

    async def add_ignore_pattern(self, pattern: str) -> None:
        await asyncio.to_thread(self._writer.add_ignore_pattern, pattern)
