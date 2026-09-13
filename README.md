# Expense Categorization Assistant

## Goal

Automatically categorize expenses retrieved from a Revolut Personal account using merchant rules stored in a Google Spreadsheet. When a transaction cannot be categorized automatically, ask the user through Telegram and persist the new merchant rule into the spreadsheet.

## Running

```
uv run expenses-serve
```

Starts the FastAPI app (TR-0): builds the object graph, loads processed-transaction
state, refreshes the Support/Ignore cache, starts Telegram long-polling, and starts
the Enable Banking poll scheduler. See [docs/enable-banking-setup.md](docs/enable-banking-setup.md)
for one-time bank-linking setup and `.env.example` for required configuration.

## Docker

Build:

```
docker build -t expenses .
```

Run, mounting the same `secrets/` and `.env` used for local development plus your
existing `state/` directory:

```
docker run -d \
  --name expenses \
  --env-file .env \
  -v "$(pwd)/secrets:/app/secrets:ro" \
  -v "$(pwd)/state:/app/state" \
  expenses
```

- `secrets/` and `.env` are **never** baked into the image — they're mounted at
  runtime, at the same relative paths `.env.example` already uses
  (`./secrets/...`, resolved against the container's `/app` working directory).
- `state/` backs `state/processed_transactions.log` (FR-13 idempotency, TR-7) — the
  file is created by the app itself at runtime, not supplied from outside; the mount
  only controls where that write physically lands. Bind-mounting your **existing**
  project `state/` directory (rather than a fresh named volume) carries over the
  processed-transaction history from any prior `uv run expenses-serve` runs, so
  switching to Docker doesn't reprocess everything still inside the lookback window
  (which would otherwise duplicate sheet rows and Telegram notifications). The
  container runs as uid 1000, so make sure the host directory is writable by it, e.g.
  `chown -R 1000:1000 state/` (or `chmod -R o+w state/` if you'd rather not change
  ownership). A named volume (`-v expenses-state:/app/state`) also works and is
  auto-writable by uid 1000 on first use, but starts empty — only use it for a
  deployment that never ran locally, or you're fine reprocessing the lookback window
  once.
- No port needs to be published: the image's built-in `HEALTHCHECK` polls `/health`
  from inside the container. Add `-p 8000:8000` only if something outside the
  container needs to reach `/health` directly.

### Versioned build & push to Docker Hub

The project version in `pyproject.toml` is the single source of truth for the image
tag — no separate versioning scheme to maintain:

```
VERSION=$(uv version --short)              # e.g. 0.1.0
docker build -t leofaber/expenses-to-spreadsheet:"$VERSION" -t leofaber/expenses-to-spreadsheet:latest .
```

Bumping the version first (creates a new commit-worthy change to `pyproject.toml`/`uv.lock`):

```
uv version --bump patch   # or --bump minor / --bump major
```

Push (requires `docker login` once per machine):

```
docker login
docker push leofaber/expenses-to-spreadsheet:"$VERSION"
docker push leofaber/expenses-to-spreadsheet:latest
```

The `leofaber/expenses-to-spreadsheet` repository is created automatically on Docker
Hub on first push if it doesn't exist yet.

Full packaging rationale: [TR-0](docs/technical-requirements/TR-0-app-bootstrap-and-configuration.md).