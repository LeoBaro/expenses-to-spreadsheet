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