---
name: arch
description: Bootstrap docs/architecture.md — derive the system's top-down architecture (components, interfaces, abstraction gaps, core processing flows, runtime data) from the full set of requirements, before any TR translation begins.
---

@docs/architecture.md is the whole-system design that @docs/technical-requirements/ translate
component-by-component (via the `tr` skill) into implementation-oriented specs. This skill
produces that document directly from @docs/functional-requirements.md +
@docs/non-functional-requirements.md — a one-time bootstrap step run once a requirement set
is stable enough to design against, before any TR exists. It does not write TRs (`tr`) or
code (`impl`).

## When to use this

Only when @docs/architecture.md does not yet reflect the requirements being designed
against — normally once, right after the initial requirements pass, before the first `tr`
invocation. If @docs/architecture.md already exists and covers the current requirement set,
a requirement change that stays inside one component's existing boundary is a `tr` update,
not an architecture re-bootstrap (see the `req` skill's update flow). If asked to run this
against an existing architecture.md anyway, treat it as a deliberate re-derivation: confirm
scope with the caller first and say which components/interfaces would change and why, since
it can invalidate TRs already built against the previous shape.

## Input

* Read in full before writing anything: @docs/functional-requirements.md and
  @docs/non-functional-requirements.md — the whole set, not one requirement, since
  architecture is a whole-system concern — plus any doc describing an external system the
  requirements integrate with (e.g. @docs/spreadsheet-structure.md).
* If @docs/architecture.md already exists, read it too and use it as the literal structural
  and stylistic template (section order, mermaid conventions, tone). Don't reinvent the shape.

## Disambiguate before writing

Deriving components from a flat requirement list means making boundary calls the requirements
don't make explicit. Before drafting, ask the caller about:
* where one component's responsibility ends and another's begins, when a requirement could
  plausibly sit in either;
* which components own state vs. are stateless pass-throughs;
* what's external (third-party API, user-facing surface) vs. internal to the system;
* anything that reads as a genuine unresolved design question rather than an implementation
  detail worth deciding now.

Do not silently resolve these — record them as abstraction gaps (below) instead.

## Producing the architecture doc

Write (or replace, per "When to use this") `docs/architecture.md` with:

1. **Overview** — one short paragraph: what the system does, and the one or two defining
   constraints that shape everything else (e.g. "no database", "single user").
2. **High-level architecture diagram** — a mermaid flowchart: one node per component (blue)
   and one per external system (purple), edges labelled with intent, not implementation.
   Follow it with a legend paragraph explaining the color convention and naming the sole
   orchestrator, if the design has one.
3. **Components** — one numbered subsection per component: Responsibilities, Inputs,
   Outputs. Stay at "what it does", not "how" — the "how" is the owning TR's job.
4. **Abstraction gaps** — an explicit list of interface/boundary questions the requirements
   leave open that a TR will need to resolve (e.g. exact contract shape across a boundary,
   who owns idempotency, error-handling ownership when two components meet). This is the
   architecture-level analogue of a TR's "Open Questions" — name each one so the `tr` skill
   picks it up as a starting open question for the component(s) it touches, rather than it
   getting silently decided later inside one TR without the other side noticing.
5. **System of record** — the shape of whatever holds persisted business data, if the
   requirements centre on one (e.g. what sheets/tables exist and what each contains).
6. **Processing flows** — one flow per core process, covering only the main path through
   the components (text step-diagrams or mermaid, whichever stays easiest to keep in sync).
   Branch-level detail belongs in the owning TR, not here.
7. **Runtime data** — non-persisted state the system carries (caches, queues, run state) and
   why each exists, distinguished clearly from the system of record in (5).
8. **Design principles** — the handful of system-wide invariants every later TR must respect
   (e.g. "X is append-only", "Y is the single source of truth").

## Constraints

* Do not write TRs or code — this stops at the architecture doc.
* Do not decompose a component into internal implementation detail; if it's something a
  single TR would own alone, it belongs in that TR, not here.
* Do not silently resolve an abstraction gap — list it so `tr` inherits it as a named open
  question for the component(s) it touches.
* Treat a second invocation against an existing architecture.md as a deliberate
  re-bootstrap, never a routine edit — confirm scope with the caller first.

## When done

Tell the caller the architecture is ready: which components exist, what open abstraction
gaps remain, and that `tr` is the next step to translate each component into a Technical
Requirement — suggest an order if some components' TRs depend on others being resolved
first.
