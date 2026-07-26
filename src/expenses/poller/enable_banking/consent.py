"""Enable Banking one-time consent / session bootstrap (setup, not the poll path).

Belongs to the Enable Banking integration because it speaks EB endpoints and field
names. Used by the ``expenses-consent`` CLI to obtain an account UID, which the
poller then reuses on every cycle until consent expires.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from expenses.poller.enable_banking.auth import EnableBankingAuth


class ConsentClient:
    def __init__(self, client: httpx.AsyncClient, auth: EnableBankingAuth, base_url: str) -> None:
        self._client = client
        self._auth = auth
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._auth.bearer()}"}

    async def list_aspsps(self, country: str) -> list[dict[str, Any]]:
        """GET /aspsps?country=XX — banks available for the (sandbox) environment."""
        response = await self._client.get(
            f"{self._base_url}/aspsps", params={"country": country}, headers=self._headers()
        )
        response.raise_for_status()
        return response.json().get("aspsps", [])

    async def start_authorization(
        self,
        *,
        aspsp_name: str,
        aspsp_country: str,
        redirect_url: str,
        psu_type: str = "personal",
        valid_days: int = 10,
        state: str | None = None,
    ) -> dict[str, str]:
        """POST /auth — returns the URL to which the end user must be redirected."""
        state = state or str(uuid.uuid4())
        valid_until = (
            (datetime.now(timezone.utc) + timedelta(days=valid_days))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": aspsp_name, "country": aspsp_country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": psu_type,
        }
        response = await self._client.post(f"{self._base_url}/auth", json=body, headers=self._headers())
        response.raise_for_status()
        return {"url": response.json()["url"], "state": state}

    async def create_session(self, code: str) -> dict[str, Any]:
        """POST /sessions — exchanges the redirect ``code`` for a session + accounts."""
        response = await self._client.post(
            f"{self._base_url}/sessions", json={"code": code}, headers=self._headers()
        )
        response.raise_for_status()
        return response.json()
