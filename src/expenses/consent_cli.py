"""Interactive one-time consent bootstrap:  ``uv run expenses-consent``

Two subcommands:
  banks      list available (sandbox) banks for a country
  authorize  start the consent flow for a chosen bank and print the account UID

The authorize step prints a URL to open in your browser. After you authenticate at
the bank, it redirects to your whitelisted redirect URL with ``?code=...`` in the
query string. Even if nothing is served there (e.g. localhost), copy that redirected
URL from the address bar and paste it back here; the code is exchanged for a session.
"""

from __future__ import annotations

import argparse
import asyncio
from urllib.parse import parse_qs, urlparse

import httpx

from expenses.config import Settings
from expenses.poller.enable_banking.auth import EnableBankingAuth
from expenses.poller.enable_banking.consent import ConsentClient


def _build(settings: Settings) -> tuple[EnableBankingAuth, str]:
    if not settings.eb_application_id:
        raise SystemExit("EXPENSES_EB_APPLICATION_ID is not set (register the app first).")
    auth = EnableBankingAuth(settings.eb_application_id, settings.private_key())
    return auth, settings.eb_api_base_url


async def _banks(settings: Settings, country: str) -> None:
    auth, base_url = _build(settings)
    async with httpx.AsyncClient(timeout=30.0) as client:
        aspsps = await ConsentClient(client, auth, base_url).list_aspsps(country)
    if not aspsps:
        print(f"No banks returned for country={country}.")
        return
    print(f"Banks available for {country}:")
    for aspsp in aspsps:
        print(f"  - name={aspsp.get('name')!r:40} country={aspsp.get('country')}")
    print("\nRun:  uv run expenses-consent authorize --aspsp <name> --country <country>")


def _extract_code(entered: str) -> str:
    entered = entered.strip()
    if "code=" in entered:
        query = urlparse(entered).query or entered
        codes = parse_qs(query).get("code")
        if codes:
            return codes[0]
    return entered  # assume the user pasted the bare code


async def _authorize(
    settings: Settings, aspsp_name: str, aspsp_country: str, valid_days: int
) -> None:
    auth, base_url = _build(settings)
    async with httpx.AsyncClient(timeout=30.0) as client:
        consent = ConsentClient(client, auth, base_url)
        print(f"Requesting a {valid_days}-day consent (bank may cap this).")
        started = await consent.start_authorization(
            aspsp_name=aspsp_name,
            aspsp_country=aspsp_country,
            redirect_url=settings.eb_redirect_url,
            valid_days=valid_days,
        )
        print("\n1) Open this URL in your browser and authenticate:\n")
        print(f"   {started['url']}\n")
        print(f"   (redirect URL: {settings.eb_redirect_url} — state: {started['state']})")
        print("\n2) After the bank redirects you, paste the full redirect URL (or just the code):\n")
        code = _extract_code(input("   code/url> "))

        session = await consent.create_session(code)

    accounts = session.get("accounts", [])
    print(f"\nSession established (session_id={session.get('session_id')}).")
    if not accounts:
        print("No accounts returned.")
        return
    print("Accounts:")
    for account in accounts:
        print(f"  uid={account.get('uid')}  {account.get('name') or ''}  {account.get('iban') or ''}")
    print(f"\nSet this in your .env:\n  EXPENSES_EB_ACCOUNT_UID={accounts[0].get('uid')}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="expenses-consent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_banks = sub.add_parser("banks", help="list available banks for a country")
    p_banks.add_argument("--country", required=True, help="ISO 3166 two-letter code, e.g. FI")

    p_auth = sub.add_parser("authorize", help="start consent for a bank and print the account UID")
    p_auth.add_argument("--aspsp", required=True, help="bank name from the 'banks' list")
    p_auth.add_argument("--country", required=True, help="bank country (ISO 3166 two-letter code)")
    p_auth.add_argument(
        "--valid-days",
        type=int,
        default=None,
        help="requested consent lifetime in days (default: EXPENSES_EB_CONSENT_VALID_DAYS). "
        "Banks cap this (Revolut ~90); lower it if authorization is rejected.",
    )

    args = parser.parse_args()
    settings = Settings()
    if args.command == "banks":
        asyncio.run(_banks(settings, args.country))
    elif args.command == "authorize":
        valid_days = args.valid_days if args.valid_days is not None else settings.eb_consent_valid_days
        asyncio.run(_authorize(settings, args.aspsp, args.country, valid_days))


if __name__ == "__main__":
    main()
