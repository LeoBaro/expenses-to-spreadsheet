# Technical Requirements

Technical requirements translate the [functional requirements](functional-requirements.md)
and the [architecture](architecture.md) into implementation-oriented specifications.

Each technical requirement corresponds to one architecture component and is defined
in its own file under [technical-requirements/](technical-requirements/).

> Status: **Skeleton** — structure and traceability are defined; design decisions,
> data models, and interface contracts are still to be completed per file.

## Index

| TR | Component | Functional Requirements | Non-functional |
|----|-----------|-------------------------|----------------|
| [TR-0](technical-requirements/TR-0-app-bootstrap-and-configuration.md) | Application Bootstrap & Configuration | FR-2 | NFR-1, NFR-7, NFR-8 |
| [TR-1](technical-requirements/TR-1-transaction-poller.md) ✅ | Transaction Poller | FR-1 | NFR-6, NFR-7 |
| [TR-2](technical-requirements/TR-2-transaction-processor.md) | Transaction Processor | FR-1, FR-4, FR-5, FR-6 | — |
| [TR-3](technical-requirements/TR-3-categorization-engine.md) | Categorization Engine | FR-3, FR-4, FR-5, FR-9, FR-10 | NFR-5 |
| [TR-4](technical-requirements/TR-4-google-sheets-client.md) | Google Sheets Client | FR-2, FR-11, FR-12 | NFR-2, NFR-4 |
| [TR-5](technical-requirements/TR-5-cache-manager.md) | Cache Manager | FR-2, FR-14 | NFR-4, NFR-5 |
| [TR-6](technical-requirements/TR-6-telegram-bot-and-conversation.md) | Telegram Bot & Conversation | FR-5, FR-6, FR-7, FR-8 | NFR-6 |
| [TR-7](technical-requirements/TR-7-state-manager.md) ✅ | State Manager | FR-13 | NFR-3, NFR-7 |

## Cross-cutting design decisions

These decisions span multiple components and should be resolved before or alongside
the individual TRs. Each is expanded in the relevant file's _Open Questions_.

- **Internal `Transaction` model** — the canonical shape passed between Poller,
  Processor, Engine, Sheets Client and State Manager (owned by [TR-1](technical-requirements/TR-1-transaction-poller.md)).
- **Cache data structures** — how categories, merchant rules and ignore patterns are
  indexed to satisfy FR-3 "longest match wins" cheaply (owned by [TR-5](technical-requirements/TR-5-cache-manager.md)).
- **Conversation state** — how multi-step Telegram flows (FR-6→7→8) are held, keyed and
  expired (owned by [TR-6](technical-requirements/TR-6-telegram-bot-and-conversation.md)).
- **Write / mark-processed ordering** — the crash-consistency contract behind FR-13
  idempotency (shared by [TR-2](technical-requirements/TR-2-transaction-processor.md) and [TR-7](technical-requirements/TR-7-state-manager.md)).
