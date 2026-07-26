# TR-6. Telegram Bot & Conversation

> Status: **Implemented.** Transport plumbing (send + long-poll + callback routing) and
> the FR-6→8 interactive workflows are live. Per the design, the workflow *state* lives
> in the Processor (TR-2, `conversation.py`); the Bot stays pure UI — it renders prompts
> and relays taps. Callback keying was finalized here as `f"{step}:{index}"`.

## Traceability
- Functional requirements: FR-5 (auto-categorization notification), FR-6 (unknown-merchant workflow), FR-7 (categorize workflow), FR-8 (ignore workflow)
- Non-functional requirements: NFR-6 (interactions complete within seconds)
- Architecture: [Telegram Bot](../architecture.md) (§6)

## Purpose & Scope
All user interaction, and **nothing else**. The Bot is a pure messaging surface: it
renders notifications and prompts, and reports the user's raw selections back to the
**Transaction Processor (TR-2)**, which is the sole orchestrator of every
Engine/Sheets/Cache/State call. The Bot performs no business logic and never touches
the spreadsheet, cache, engine or state directly. *(Decided — see
[architecture.md](../architecture.md); the alternative of a Bot-driven workflow was
rejected.)*

## System Decomposition
Two internal parts: a **presenter/sender** (renders notifications and option prompts)
and a **callback router** (maps a Telegram button tap back to the pending interaction
and relays the raw selection). Its only internal-system counterpart is the Processor;
it holds no workflow state beyond callback routing (that state lives in TR-2).

```mermaid
flowchart TB
    TR2["Transaction Processor<br/>(TR-2)"]

    subgraph TR6["TR-6 · Telegram Bot"]
        direction TB
        PRES["Presenter / sender<br/><i>notifications (FR-5) &<br/>option prompts (FR-6→8)</i>"]
        ROUTER["Callback router<br/><i>maps Telegram callback →<br/>pending interaction</i>"]
    end

    TG(["Telegram user"])
    TR0["Bootstrap / Config<br/>(TR-0)"]

    TR2 -->|"present options · notify"| PRES
    PRES -->|"send message · keyboard"| TG
    TG -->|"button tap"| ROUTER
    ROUTER -->|"relay user selection"| TR2
    TR0 -.->|"bot token · integration mode"| TR6

    classDef ext fill:#f5f0ff,stroke:#7c3aed,stroke-width:1px,color:#000;
    classDef other fill:#eef6ff,stroke:#2563eb,stroke-width:1px,color:#000;
    class TG ext;
    class TR2,TR0 other;
```

**Legend:** boxes inside the *TR-6* frame are the Bot's internal parts; **blue** is the
Processor; **purple** is the external Telegram user. Solid arrows are conceptual
interactions; the dashed arrow is config wiring. There are **no arrows to Engine,
Sheets, Cache or State** — the Bot is pure UI and talks only to the Processor and the
user.

## Responsibilities
- Send informational notification on automatic categorization (FR-5).
- On unknown transaction, present amount/date/description + Categorize/Ignore actions (FR-6).
- Categorize flow (FR-7): present Primary → Secondary → merchant-substring options and return each selection to the Processor (the Processor performs the Support update, cache refresh, expense write and mark-processed).
- Ignore flow (FR-8): present ignore-pattern candidates and return the selection to the Processor (which appends the pattern, refreshes cache, marks processed).

## Design Decisions
- **Library (decided): python-telegram-bot (PTB v22).** Async; the bot wires PTB
  handlers (`CommandHandler`, `CallbackQueryHandler`, `MessageHandler`) that **delegate**
  to a `TelegramUpdateHandler` (the Processor). **No `ConversationHandler`** — that would
  put workflow state in the bot, which we rejected.
- **Delivery (decided): long polling.** No public URL required (works on a laptop /
  home server). Standalone via `run_polling()`; when embedded in the FastAPI app (TR-0)
  the Application's `initialize`/`start`/`updater.start_polling` will be used in the
  existing loop.
- **UI mechanics (decided, revised):** inline keyboards, one option per button;
  `callback_data = f"{step}:{index}"` — a step tag plus the option's **index**, not its
  text. (Superseded the earlier `prefix + option` idea: category names can be long or
  contain colons and would risk the 64-byte cap; index encoding is always tiny and the
  Processor maps the index back to the option it presented. See TR-2 DD-6.)
- **Conversation state (decided elsewhere):** the *workflow* state (which transaction,
  step, partial selections) lives in the Processor (TR-2, `conversation.py`); the bot
  only routes a callback back to it.
- **Concurrency (resolved in TR-2 DD-5):** one active conversation at a time; further
  unknown transactions queue FIFO and are drained on completion — so a callback is never
  ambiguous. Abandonment/timeout of an unfinished workflow is **still open** (an
  unanswered prompt simply persists; a later poll won't double-notify because in-flight
  ids are de-duped, but there is no explicit expiry yet).

## Data Model / Contracts
The Bot itself is stateless beyond PTB's own machinery. The conversation/session record
(transaction ref, current step, partial selections) lives in TR-2's
`ConversationOrchestrator` (`Session`), not here. Contracts at the boundary:
`TelegramUpdateHandler` (inbound: `on_callback(chat_id, message_id, data, callback_id)`,
`on_message(chat_id, text)`) and the outbound presenter surface (`send_message`,
`send_options(chat_id, text, options, *, tag)`), where each button's `callback_data` is
`f"{tag}:{index}"`.

## Interfaces
- Inbound: Telegram updates (callbacks) from the user; notification + prompt requests from the Transaction Processor (TR-2).
- Outbound: **Transaction Processor (TR-2) only** — deliver the user's selections. No direct calls to Engine/Sheets/Cache/State.
- External: the Telegram platform (messages to/from the user).

## Dependencies
- TR-2 (its only orchestration counterpart), TR-0 (bot token, integration mode).

## Risks & Assumptions
- Conversation state is the main non-obvious design; FRs describe only the happy path.
- Assumes a single known chat/user (single-user design principle).

## Open Questions
- ✅ Where does conversation state live? In-memory in the Processor (TR-2). **Not**
  persisted: a restart drops in-flight conversations, but the transactions stay
  unprocessed and re-surface on the next poll — acceptable for a single-user app.
- ✅ Does an in-flight unknown transaction block others? Yes — one active conversation,
  the rest queue FIFO (TR-2 DD-5).
- ⏳ Timeout/abandonment behavior for a workflow the user never completes — still open
  (no explicit expiry; the prompt just persists).

## Implementation
Package [`src/expenses/telegram_bot/`](../../src/expenses/telegram_bot/) (named to avoid
clashing with PTB's `telegram` package):
- [`bot.py`](../../src/expenses/telegram_bot/bot.py) — `ExpenseBot`: builds the PTB
  `Application`, registers `/start` + callback + message handlers that delegate to a
  `TelegramUpdateHandler` (the TR-2 orchestrator at runtime); outbound `send_message`
  (FR-5) / `send_options` (FR-6/7/8, index-keyed keyboards); `run_polling()` for
  standalone use (TR-0 drives it in-loop instead).
- [`ports.py`](../../src/expenses/telegram_bot/ports.py) — `TelegramUpdateHandler`
  Protocol (implemented by TR-2's `ConversationOrchestrator`) + `LoggingUpdateHandler`
  fallback used when Telegram is unconfigured.
- [`keyboards.py`](../../src/expenses/telegram_bot/keyboards.py) — index-keyed
  inline-keyboard builder (`callback_data = f"{tag}:{index}"`).
- [`telegram_cli.py`](../../src/expenses/telegram_cli.py) — `expenses-telegram run` (poll;
  `/start` reveals your chat id) and `send-test` (push a two-button prompt).

Tests: [`tests/test_telegram_keyboards.py`](../../tests/test_telegram_keyboards.py) covers
the index-keyed builder; the interactive workflow itself is tested via TR-2's
[`tests/test_conversation.py`](../../tests/test_conversation.py).

Config: `EXPENSES_TELEGRAM_BOT_TOKEN`, `EXPENSES_TELEGRAM_CHAT_ID`. Tests cover the
keyboard builder. The FR-5/6/7/8 message *content* and callback-keying land with TR-2.
