"""Enable Banking API gateway: authenticated transaction retrieval with paging."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx

from expenses.poller.enable_banking.auth import EnableBankingAuth

logger = logging.getLogger(__name__)


class EnableBankingGateway:
    def __init__(self, client: httpx.AsyncClient, auth: EnableBankingAuth, base_url: str) -> None:
        self._client = client
        self._auth = auth
        self._base_url = base_url.rstrip("/")

    async def iter_transactions(
        self,
        account_uid: str,
        date_from: date,
        date_to: date,
        *,
        transaction_status: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw transaction payloads, following ``continuation_key`` paging.

        ``transaction_status`` filters server-side (e.g. "BOOK" for settled only).
        """
        url = f"{self._base_url}/accounts/{account_uid}/transactions"
        params: dict[str, str] = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
        if transaction_status:
            params["transaction_status"] = transaction_status

        page = 0
        while True:
            page += 1
            response = await self._client.get(
                url, params=params, headers={"Authorization": f"Bearer {self._auth.bearer()}"}
            )
            response.raise_for_status()
            body = response.json()

            transactions = body.get("transactions", [])
            logger.debug("page %d: %d transactions", page, len(transactions))
            for raw in transactions:
                yield raw

            continuation_key = body.get("continuation_key")
            if not continuation_key:
                break
            params["continuation_key"] = continuation_key
