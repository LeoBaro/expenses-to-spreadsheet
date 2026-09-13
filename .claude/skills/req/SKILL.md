---
name: req
description: Help the user to perform Create/Update operations on a requirement.
---

The requirements are defined inside: @docs/non-functional-requirements.md and @docs/functional-requirements.md .

For Create operations:
* Read the project documentation in @docs for context. 
* Understand the new functional requirement described by the user and eventually refine the idea with him asking him questions.
* Then create a new requirement in @docs/non-functional-requirements.md or @docs/functional-requirements.md .

For Update operations:
* The caller must pass a REQ-ID. Otherwise ask him which REQ it refers to.
* Read the project documentation in @docs for context. 
* Understand the update described by the user and eventually refine the idea with him asking him questions.
* Update the requirement.
* Analyze the impact of this update on @docs/architecture.md and @docs/technical-requirements: does it stay inside an existing component's boundary, or does it add/reshape a component, an interface between components, or a responsibility split? Summarize the changes to the user and ask for confirmation.
* Once confirmed:
  - If it reshapes component boundaries or interfaces, offer the `arch` skill first to re-derive the affected part of @docs/architecture.md, then `tr` for the affected component(s).
  - Otherwise, offer to carry the change through with the `tr` skill directly (update the affected TR doc's Design Decisions).
  - Either way, for any TR already marked ✅ in @docs/technical-requirements.md, offer the `impl` skill afterwards (code + tests need to match the new requirement too).

