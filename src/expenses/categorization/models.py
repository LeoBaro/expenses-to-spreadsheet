"""Result types for the Categorization Engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A merchant-rule match (FR-3/FR-5)."""

    primary: str
    secondary: str
    substring: str  # the matched merchant substring, as stored in the sheet
