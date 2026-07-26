"""Candidate tokenization for substring/ignore suggestions (FR-9/FR-10)."""

from __future__ import annotations

import string

_PUNCTUATION = string.punctuation


def candidate_tokens(description: str) -> list[str]:
    """Split on whitespace, strip surrounding punctuation, uppercase; then drop
    tokens shorter than 2 chars or containing any digit (dates, amounts, IBANs,
    card refs, transaction codes). Order preserved; duplicates NOT removed here."""
    tokens: list[str] = []
    for raw in description.split():
        token = raw.strip(_PUNCTUATION).upper()
        if len(token) < 2:
            continue
        if any(ch.isdigit() for ch in token):
            continue
        tokens.append(token)
    return tokens
