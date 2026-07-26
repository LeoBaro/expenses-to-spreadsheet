---
name: adr
description: Help the user to perform Create/Update operations on Architectural Designment Requirement documents defined in @docs/decisions.
---

For Create operations:
* The template to define new ADR document is in @docs/decisions/README.md.
* Read the project documentation in @docs and understand the new architectural decision described by the user and eventually refine the idea with him asking him questions.
* Then create a new ADR document in @docs/decisions and update the index in @docs/decisions/README.md.

For Update operations:
* The caller must pass a ADR-ID. 
* Read the project documentation in @docs and understand the update described by the user and eventually refine the idea with him asking him questions.
* The caller must tell if the updated ADR *supersedes* or *replace* the old ADR. If not stated, you need to ask the caller.
* If it *supersedes*, create a new ADR document with a new ID and state inside that it supersedes the old one.
* If it *replaces*, ASK THE CALLER FOR A CONFIRMATION and overwrite the old ADR. Remember to change the file name!

