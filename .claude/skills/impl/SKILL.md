---
name: impl
description: Implement a Technical Requirement end-to-end — code, tests, and the TR doc's Implementation section — following this project's clean-architecture conventions.
---

Turns one TR under @docs/technical-requirements/ into working, tested code under
`src/expenses/`. Assumes the TR already exists (if not, use the `tr` skill first).

## Input

* The caller must name a TR-ID. If unstated or ambiguous, ask — check the index in
  @docs/technical-requirements.md for which ones aren't ✅ yet.
* Read, in full, before writing code:
  - the target TR doc, including its Design Decisions and Open Questions;
  - the TR docs of everything it lists under **Dependencies** — you need the
    Protocols/contracts those expose, not their internals;
  - the NFR-ids in its Traceability line, in @docs/non-functional-requirements.md;
  - @docs/architecture.md for how the component fits the whole system.
* Open one already-implemented component under `src/expenses/` (its `ports.py`,
  adapter, and matching `tests/test_*.py`) as the concrete style reference for what
  follows below — copy the shape, don't reinvent it.

## Architecture conventions (established by TR-0 through TR-7 — follow them)

* One package per component: `src/expenses/<component>/`.
* Define the component's inbound/outbound boundary as `Protocol` classes (often
  `@runtime_checkable`) in that package's `ports.py`. Depend on Protocols, never on a
  sibling component's concrete class — that's what keeps components independently
  testable and swappable.
* For any port that talks to an external system (Telegram, Sheets, a notifier), also
  provide a trivial `Logging*` no-op adapter as the default, so the app runs before the
  real adapter is wired in.
* Concrete adapters are wired together in exactly one place: the composition root in
  `src/expenses/bootstrap/` (constructor injection, no DI framework). Components must
  not import each other's concrete classes directly.
* Configuration goes through `expenses.config.Settings` (pydantic-settings); new env
  vars are prefixed `EXPENSES_*`.
* If the component needs a standalone entry point, add an `expenses-<name>` script
  under `[project.scripts]` in `pyproject.toml`, argparse-based, matching the existing
  `*_cli.py` files.
* Keep business logic (matching, suggestion, workflow state) free of I/O; push I/O to
  the edges (gateway/adapter/client modules), matching how TR-3 (pure) and TR-4
  (I/O-only) are split today.

## Tests

Write tests alongside the code, not after, as `tests/test_<component>.py`
(pytest + pytest-asyncio, `asyncio_mode = auto` — no manual event-loop plumbing needed).
Cover:
* the happy path;
* every branch called out in the TR's Responsibilities / Design Decisions (e.g. each
  ordering or fallback the TR decided on);
* the edge and failure cases named in the TR's Risks & Assumptions or Open Questions.

Run `uv run pytest` and get to green before considering the TR done.

## Closing the loop on the docs (don't skip this)

1. Flip the TR doc's **Status** line to `Implemented` — name the scope precisely if
   it's partial (e.g. "Implemented (automatic path); interactive path pending").
2. Add an **## Implementation** section: one bullet per source file (linked, one-line
   description of what it does), then the test file(s) and what they cover.
3. Resolve any **Open Questions** the implementation answered — mark ✅ with a one-line
   answer instead of deleting the question.
4. If a decision got made while coding that the TR didn't anticipate, add it as a new
   numbered **Design Decision** (continue that file's DD-N numbering) rather than
   letting it live only in the code/commit message.
5. Mark the TR ✅ in the index table in @docs/technical-requirements.md.

## Constraints

* Don't reshape another component's internals "in passing" to make this one easier —
  if implementing reveals that a dependency's contract (its TR) is actually wrong,
  stop and say so; that's a `tr` update, not a silent workaround.
* Don't invent behavior the TR doesn't specify and didn't leave as an explicit
  fallback — surface the gap to the caller instead of guessing silently.
* Only propose a commit (message style: `feat: implement <Component> (TR-<N>)`,
  following this repo's history) — never create one unless the caller asks.
