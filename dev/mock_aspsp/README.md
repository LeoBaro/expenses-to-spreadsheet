# Mock ASPSP dev fixtures

Reusable transaction payloads for Enable Banking's **Mock ASPSP**, used to exercise
the Transaction Poller ([TR-1](../../docs/technical-requirements/TR-1-transaction-poller.md))
against controlled data. They follow the exact schema the Mock ASPSP import accepts.

## How to use
In the Control Panel → **Mock ASPSP** tab, add/import each transaction, then run:

```
uv run expenses-poll
```

## Scenarios and expected classification

| File | indicator / status | Expected | Why |
|------|--------------------|----------|-----|
| [`booked_debit_expense.json`](booked_debit_expense.json) | `DBIT` / `BOOK` | **expense** | settled debit (FR-1) |
| [`booked_debit_with_transaction_id.json`](booked_debit_with_transaction_id.json) | `DBIT` / `BOOK` | **expense** (real id, not derived) | exercises the non-derived id path |
| [`booked_credit_income.json`](booked_credit_income.json) | `CRDT` / `BOOK` | excluded | credit, not an expense |
| [`pending_debit.json`](pending_debit.json) | `DBIT` / `PDNG` | excluded | not settled |

## Notes
- Enable Banking's enum accepts only `CRDT` / `DBIT` — `DRWT` is rejected on import.
- The Mock ASPSP does **not** emit a `transaction_id` unless you set one, so most
  fixtures rely on the adapter's derived-id fallback; `booked_debit_with_transaction_id.json`
  provides one to cover the other branch.
- `booking_date` values must fall inside the poll window (default: last 7 days), so
  bump the dates if these fixtures age out.
