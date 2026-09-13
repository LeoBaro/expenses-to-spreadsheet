---
name: tr
description: Translate functional/non-functional requirements into a Technical Requirement (TR) document for one architecture component.
---

Technical requirements live one-per-component under @docs/technical-requirements/,
indexed by @docs/technical-requirements.md, and translate @docs/functional-requirements.md
+ @docs/non-functional-requirements.md into implementation-oriented specs against
@docs/architecture.md. This skill does **not** write code — that is the `impl` skill.

## Input

* The caller must say which FR(s)/NFR(s) or component they want translated, or which
  existing TR-ID to revise. If it's ambiguous or unstated, ask.
* Read for context before writing anything: @docs/functional-requirements.md,
  @docs/non-functional-requirements.md, @docs/architecture.md, and the index +
  "Cross-cutting design decisions" section in @docs/technical-requirements.md.
* Open one or two existing files under @docs/technical-requirements/ (e.g.
  `TR-2-transaction-processor.md`) and use them as the literal structural and
  stylistic template — section order, heading names, mermaid conventions, tone.
  Don't reinvent the shape from scratch.

## Disambiguate before writing

Requirements routinely leave things open on purpose. Before drafting, ask the caller
about anything the FR/NFR doesn't pin down: component boundaries and ownership, who
holds state, ordering/concurrency, error-handling/failure semantics, what's a "decided"
design choice vs. a genuine unknown. Do not silently invent an answer to something
undetermined — record it under "Open Questions" instead, exactly like existing TRs do
(e.g. TR-2's DD-3 ordering, DD-5 concurrency — each started as an open question the
user resolved).

## Producing the TR

1. If this introduces a **new component**, add it to @docs/architecture.md first: a
   numbered subsection under "Components" plus a node in the top-level mermaid diagram
   (blue = internal component, purple = external system).
2. Write or update `docs/technical-requirements/TR-<N>-<slug>.md` with every section
   below, even when a section is legitimately "—":
   - **Status** line — `Skeleton` or `Specified`. Never `Implemented`; that belongs to
     the `impl` skill.
   - **Traceability** — FR-ids, NFR-ids, link to the relevant architecture section.
   - **Purpose & Scope**
   - **System Decomposition** — a mermaid flowchart scoped to this component: a
     subgraph framing its own internal parts, blue nodes for other components it talks
     to, purple for any external system, solid arrows for runtime interaction, dashed
     for wiring-only. Always follow it with the same kind of Legend paragraph the
     existing TRs use.
   - **Responsibilities**
   - **Design Decisions** — numbered `DD-N (decided)` or `DD-N (open)` bullets with the
     rationale, continuing the numbering already used in that file if revising one.
   - **Data Model / Contracts**
   - **Interfaces** — inbound / outbound, named per the component that owns each side.
   - **Dependencies** — the other TR-ids this one relies on.
   - **Risks & Assumptions**
   - **Open Questions** — mark resolved ones with ✅ and a one-line answer.
   - Do **not** add an "Implementation" section — the `impl` skill owns that once code
     exists.
3. Update @docs/technical-requirements.md: the index table row (link, component,
   FR/NFR columns) and, if this TR introduces or resolves a cross-cutting concern,
   the "Cross-cutting design decisions" list.

## Constraints

* Do not write code.
* Do not decompose the work into a step-by-step implementation task list — stay at the
  level where a developer implementing it still has to make coding decisions.
* Do not skip a section for brevity; use "—" instead of omitting it, so the TR stays a
  complete, comparable artifact against the others in the index.
* If real open questions remain after asking the caller, leave them open rather than
  guessing — say so explicitly when you report back.

## When done

Tell the caller the TR is ready, and that the `impl` skill is the next step to turn it
into code, tests, and the doc's "Implementation" section.
