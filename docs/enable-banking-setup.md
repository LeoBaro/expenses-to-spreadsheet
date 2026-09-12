# Linking your bank via Enable Banking

A step-by-step runbook for connecting a real bank account (e.g. **Revolut, Italy**) to
this app through Enable Banking. This is a **one-time setup** per consent period; you
repeat only the *Authorize* step when the consent expires.

> **Sandbox vs production:** the sandbox environment only exposes the *Mock ASPSP* and a
> few bank test sandboxes — **real banks like Revolut are production-only**. You must
> register a **production** application to see and link Revolut.

---

## 1. Register a production application

In the [Enable Banking Control Panel](https://enablebanking.com/cp/), create an
application and choose **production**. You will be asked for:

| Field | What to enter |
|-------|---------------|
| Email for data-protection matters | your own email |
| Privacy URL | `https://leobaro.github.io/expenses-to-spreadsheet/privacy.html` |
| Terms URL | `https://leobaro.github.io/expenses-to-spreadsheet/terms.html` |
| Redirect URL | `https://leobaro.github.io/expenses-to-spreadsheet/callback.html` |

**All URLs must be HTTPS and publicly reachable** — production rejects `http://` and
`localhost`. These three pages are served by GitHub Pages from this repo (`docs/`); see
[`privacy.html`](privacy.html), [`terms.html`](terms.html), [`callback.html`](callback.html).

Production access may require Enable Banking to approve your go-live (KYB / accepting the
AIS terms). Complete that before continuing.

When the application is created you get:
- an **Application ID** (a UUID), and
- a **private key** (`.pem`) you download once — Enable Banking keeps only the public half.

## 2. Configure `.env`

Put the key somewhere gitignored (e.g. `secrets/`) and point the app at it:

```dotenv
EXPENSES_EB_APPLICATION_ID=<your production application id>
EXPENSES_EB_PRIVATE_KEY_PATH=./secrets/enablebanking_private_key.pem
EXPENSES_EB_REDIRECT_URL=https://leobaro.github.io/expenses-to-spreadsheet/callback.html
EXPENSES_EB_CONSENT_VALID_DAYS=90
```

`EXPENSES_EB_REDIRECT_URL` **must exactly match** a redirect URL whitelisted on the
application, or the authorization request is rejected.

> Keep your sandbox `application_id` + key around too, so you can switch back for testing.

## 3. Find the bank

List the ASPSPs available for your country (Revolut Italy → `IT`):

```bash
uv run expenses-consent banks --country IT
```

Copy the exact `name` of the Revolut entry from the output — you pass it verbatim next.

## 4. Authorize (the interactive consent)

```bash
uv run expenses-consent authorize --aspsp "<exact Revolut name>" --country IT
```

Optional: `--valid-days N` overrides `EXPENSES_EB_CONSENT_VALID_DAYS` for this run. Banks
cap the lifetime (Revolut ~90 days); if authorization is rejected, lower it.

Then:

1. The CLI prints a URL — open it in your browser and authenticate with Revolut (this is
   a real **SCA**: approve in the Revolut app).
2. Revolut redirects you to the **callback page**, which displays the `code` with a
   **Copy** button.
3. Copy the code (or the whole address-bar URL) and paste it at the CLI prompt.
4. The CLI exchanges it for a session and prints your **account(s)**:
   ```
   Set this in your .env:
     EXPENSES_EB_ACCOUNT_UID=<uid>
   ```
5. Put that `EXPENSES_EB_ACCOUNT_UID` in `.env`.

## 5. Verify

```bash
uv run expenses-poll                   # one-shot: fetches, maps, and reports findings
uv run expenses-poll --month 2026-02   # or inspect a specific past month instead
uv run expenses-poll --from 2026-02-10 --to 2026-02-20   # or an arbitrary range
```

You should see your recent transactions and a `poll cycle complete` summary. This is
read-only diagnostics — it never categorizes, writes to the spreadsheet, notifies over
Telegram, or marks anything processed, even for a past month. Then run the full app
with `uv run expenses-serve`.

---

## When the consent expires

Consents are time-limited (`EXPENSES_EB_CONSENT_VALID_DAYS`, capped by the bank). When it
lapses, Enable Banking returns 401/403 and the app **does not silently stop**: the poll
loop's watchdog sends **one** Telegram message telling you to reconnect (see
[TR-0](technical-requirements/TR-0-app-bootstrap-and-configuration.md), `PollCycle`).

To renew: repeat **Step 4 (Authorize)**, then update `EXPENSES_EB_ACCOUNT_UID` in `.env`
(the UID can change with a new session) and restart the app.

## Notes specific to Revolut

- Revolut returns **no `transaction_id`** — the app derives a stable id from
  `entry_reference` + fields (validated live; idempotency holds). See
  [TR-1](technical-requirements/TR-1-transaction-poller.md).
- Account is **EUR-only** in the validated setup; a currency mismatch is surfaced, not
  silently accepted (`EXPENSES_EXPECTED_CURRENCY`).
