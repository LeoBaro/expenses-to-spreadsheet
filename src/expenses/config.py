"""Runtime configuration (seed for TR-0).

Only the settings needed by the Transaction Poller are defined here for now; other
components will extend this as they are implemented.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EXPENSES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Enable Banking ---
    eb_api_base_url: str = "https://api.enablebanking.com"
    eb_application_id: str = ""
    eb_private_key_path: Path | None = None
    # Account UID obtained from the one-time consent/session flow (POST /sessions).
    eb_account_uid: str = ""
    # Server-side status filter; "BOOK" returns only settled transactions.
    eb_transaction_status: str = "BOOK"
    # Whitelisted redirect URL registered with the application; used by the
    # one-time consent flow (expenses-consent). For a manual bootstrap a
    # non-served localhost URL is fine — you copy the code out of the browser.
    eb_redirect_url: str = "http://localhost:8000/callback"

    # --- Polling ---
    poll_interval_seconds: int = Field(default=900, ge=30)
    poll_lookback_days: int = Field(default=7, ge=1)
    # Expected account currency; mismatches are surfaced, not silently accepted.
    expected_currency: str = "EUR"

    # --- Google Sheets ---
    google_credentials_path: Path | None = None
    # The current-year spreadsheet id (from the sheet URL). Not a secret.
    google_spreadsheet_id: str = ""
    support_sheet_name: str = "Support"
    ignore_sheet_name: str = "Ignore"

    def private_key(self) -> str:
        if self.eb_private_key_path is None:
            raise ValueError("EXPENSES_EB_PRIVATE_KEY_PATH is not configured")
        return Path(self.eb_private_key_path).read_text()
