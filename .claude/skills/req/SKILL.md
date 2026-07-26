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
* Analyze the impact of this update on the @docs/technical-requirements, summarize the changes to the user and ask for confirmation.

