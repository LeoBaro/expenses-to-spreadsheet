# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user FastAPI service that polls Revolut transactions via the Enable Banking
open-banking API, categorizes them against merchant rules stored in a Google
Spreadsheet, and falls back to a Telegram conversation when a merchant is unknown.
Google Sheets is the system of record; there is no database. See
[docs/architecture.md](docs/architecture.md) for the full component diagram and
[docs/functional-requirements.md](docs/functional-requirements.md) /
[docs/non-functional-requirements.md](docs/non-functional-requirements.md) for the
requirements driving it.

## Commands

```bash
uv sync                     # install deps (Python 3.12, uv-managed)
uv run pytest                              # full test suite
uv run pytest tests/test_processor.py      # one file
uv run pytest tests/test_processor.py::test_name  # one test
uv run expenses-serve       # run the app (poller + processor + Telegram bot)
uv run expenses-poll        # one-shot diagnostic poll (see flags below); never writes anything
uv run expenses-consent     # one-time Enable Banking consent/bank-linking flow
uv run expenses-sheets      # check|write-test — validate Google Sheets auth/read/write
uv run expenses-telegram    # run|send-test — Telegram bot smoke tests
```

`expenses-poll` defaults to a rolling lookback window (`EXPENSES_POLL_LOOKBACK_DAYS`,
default 7, from today); pass `--month YYYY-MM` or `--from`/`--to YYYY-MM-DD` to inspect
an arbitrary window instead. It is always read-only diagnostics — it never runs
transactions through the Processor (no categorization, sheet writes, Telegram, or
processed-state marking), regardless of which window is used.

No linter/formatter is configured in this repo.

Config is `expenses.config.Settings` (pydantic-settings), loaded from `.env` with an
`EXPENSES_` prefix — see `.env.example` for the full list. First-time setup for the
bank connection is [docs/enable-banking-setup.md](docs/enable-banking-setup.md).

## Requirements → design → code workflow

This codebase is built through three chained skills, not ad hoc:

1. **`req`** — create/update an entry in `docs/functional-requirements.md` or
   `docs/non-functional-requirements.md` (disambiguates with the user first).
2. **`tr`** — translate FR(s)/NFR(s) into one Technical Requirement doc under
   `docs/technical-requirements/TR-<N>-<component>.md` (design only, no code).
3. **`impl`** — implement a TR end-to-end: code + tests + the TR doc's Implementation
   section, and flips its status to Implemented in `docs/technical-requirements.md`.

When a requirement changes after a TR is already implemented, both the TR doc and the
code/tests need to be updated to match — `req` hands off to `tr` then `impl` for that.
Treat `docs/technical-requirements.md`'s index (✅ column) as the source of truth for
what's implemented, but verify against `src/` since the doc can lag.

## Architecture conventions (established by TR-0 through TR-7 — follow them for new work)

- One package per component under `src/expenses/<component>/` (`poller`, `processor`,
  `categorization`, `sheets`, `cache`, `telegram_bot`, `state`, `bootstrap`).
- Each component declares its inbound/outbound boundary as `Protocol` classes (often
  `@runtime_checkable`) in that package's `ports.py`. Components depend on Protocols,
  never on a sibling component's concrete class — see `processor/ports.py` for the
  `Notifier`/`UnknownTransactionHandler` protocols the processor depends on.
- Any port touching an external system (Telegram, Sheets, a notifier) also gets a
  trivial `Logging*` no-op adapter as the safe default (e.g. `LoggingNotifier`,
  `LoggingUpdateHandler`) so the app runs before the real adapter is wired in.
- **The composition root is the only place that wires concrete implementations
  together**: `src/expenses/bootstrap/composition.py` (`build_components`), via plain
  constructor injection — no DI framework. New components get wired there, not
  self-assembled.
- Business logic stays free of I/O; I/O lives at the edges (gateway/adapter/client
  modules). `categorization/engine.py` (pure) vs. `sheets/client.py` (I/O-only) is the
  reference split.
- A standalone entry point gets an `expenses-<name>` script in `pyproject.toml`
  (`[project.scripts]`), argparse-based, matching the existing `*_cli.py` files.
- Tests live in `tests/test_<component>.py` (pytest + pytest-asyncio,
  `asyncio_mode = auto`, no manual event-loop plumbing) and are written alongside the
  code, covering the happy path, every branch a TR's Design Decisions calls out, and
  edge/failure cases from its Risks & Assumptions / Open Questions.

## Key flows

- **Automatic categorization**: `TransactionPoller` fetches from Enable Banking →
  filters to settled debits → drops already-processed ids (`StateManager`, TR-7) →
  hands new ones to `TransactionProcessor` (TR-2), which checks ignore patterns, then
  merchant rules (via `CategorizationEngine`, TR-3), writes matches to the current
  month's sheet, and marks them processed.
- **Unknown-merchant fallback**: unmatched transactions go through
  `ConversationOrchestrator` (TR-6), which drives a Telegram conversation (pick
  primary/secondary category or an ignore pattern), appends the new rule to the
  Support/Ignore sheet, refreshes the `CacheManager` (TR-5), then replays the
  transaction through the full processor pipeline.
- **Consent expiry**: `PollCycle` (in `composition.py`) wraps each poll cycle to catch
  401/403 from Enable Banking (the ~90-day consent session lapsing), notifies once via
  Telegram, and keeps looping so recovery is automatic once the user re-runs
  `expenses-consent`.
- Google Sheets is the only persisted business data (Support sheet: categories +
  merchant rules; Ignore sheet; one sheet per month for expenses). The state file
  (`state/processed_transactions.log`) is runtime-only idempotency data, not business
  data — never treat it as a source of truth for what expenses exist.
