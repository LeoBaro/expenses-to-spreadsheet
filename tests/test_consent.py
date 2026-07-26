"""ConsentClient tests (mocked HTTP): auth request body and session parsing."""

from __future__ import annotations

import json

import httpx
import respx

from expenses.poller.enable_banking.consent import ConsentClient

BASE = "https://api.enablebanking.test"


class _StubAuth:
    def bearer(self) -> str:
        return "stub-token"


@respx.mock
async def test_start_authorization_builds_expected_body():
    route = respx.post(f"{BASE}/auth").mock(
        return_value=httpx.Response(200, json={"url": "https://bank.example/authorize?x=1"})
    )

    async with httpx.AsyncClient() as client:
        consent = ConsentClient(client, _StubAuth(), BASE)
        result = await consent.start_authorization(
            aspsp_name="Mock ASPSP", aspsp_country="FI", redirect_url="http://localhost:8000/callback"
        )

    assert result["url"] == "https://bank.example/authorize?x=1"
    assert result["state"]  # a state was generated
    sent = json.loads(route.calls[0].request.content)
    assert sent["aspsp"] == {"name": "Mock ASPSP", "country": "FI"}
    assert sent["redirect_url"] == "http://localhost:8000/callback"
    assert sent["psu_type"] == "personal"
    assert sent["state"] == result["state"]
    assert sent["access"]["valid_until"].endswith("Z")


@respx.mock
async def test_create_session_returns_accounts():
    respx.post(f"{BASE}/sessions").mock(
        return_value=httpx.Response(
            200, json={"session_id": "s-1", "accounts": [{"uid": "acc-1", "name": "Main"}]}
        )
    )

    async with httpx.AsyncClient() as client:
        consent = ConsentClient(client, _StubAuth(), BASE)
        session = await consent.create_session("the-code")

    assert session["session_id"] == "s-1"
    assert session["accounts"][0]["uid"] == "acc-1"
