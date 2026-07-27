"""The Categorization Engine: matching, suggestion and category queries (TR-3)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from expenses.cache.models import CacheSnapshot
from expenses.categorization.models import MatchResult
from expenses.categorization.stopwords import DEFAULT_STOP_WORDS
from expenses.categorization.tokens import candidate_tokens

# A merchant rule entry may be an AND-combination of words joined by this separator,
# e.g. "apcoa+parcheggio" fires only when *all* parts are present in the description
# (position-independent). A plain entry with no separator is a single-word rule.
AND_SEPARATOR = "+"


def _rule_parts(substring: str) -> list[str]:
    """Split a merchant-rule entry into its AND parts (trimmed, lowercased, non-empty)."""
    return [part.strip().lower() for part in substring.split(AND_SEPARATOR) if part.strip()]


class CacheView(Protocol):
    """The read side of the Cache Manager (TR-5)."""

    @property
    def snapshot(self) -> CacheSnapshot: ...


class CategorizationEngine:
    def __init__(self, cache: CacheView, stop_words: Iterable[str] = DEFAULT_STOP_WORDS) -> None:
        self._cache = cache
        self._stop_words = {word.strip().upper() for word in stop_words}

    # --- Matching (FR-3, FR-4) ---

    def find_ignore_match(self, description: str) -> str | None:
        """FR-4: the first ignore pattern contained in the description
        (case-insensitive, trimmed), or None."""
        haystack = description.lower()
        for pattern in self._cache.snapshot.ignore_patterns:
            needle = pattern.strip().lower()
            if needle and needle in haystack:
                return pattern
        return None

    def match_merchant(self, description: str) -> MatchResult | None:
        """FR-3: the longest merchant rule matching the description wins; ties resolved
        by sheet order (first defined). None if nothing matches.

        A rule entry may be a single word ("apcoa") or an AND-combination
        ("apcoa+parcheggio"), which fires only when *every* part is contained in the
        description (position-independent, case-insensitive). A combination's length —
        for the longest-wins comparison — is the sum of its parts' lengths, so a more
        specific combination outranks either of its words alone."""
        haystack = description.lower()
        best: MatchResult | None = None
        best_len = 0
        for entry in self._cache.snapshot.entries:
            for substring in entry.substrings:
                parts = _rule_parts(substring)
                if not parts or not all(part in haystack for part in parts):
                    continue
                length = sum(len(part) for part in parts)
                if length > best_len:
                    best = MatchResult(entry.primary, entry.secondary, substring)
                    best_len = length
        return best

    # --- Category query (FR-7) ---

    def list_primaries(self) -> list[str]:
        """Primary categories in sheet order, de-duplicated."""
        result: list[str] = []
        for entry in self._cache.snapshot.entries:
            if entry.primary and entry.primary not in result:
                result.append(entry.primary)
        return result

    def list_secondaries(self, primary: str) -> list[str]:
        """Secondary categories for a given Primary, in sheet order, de-duplicated."""
        result: list[str] = []
        for entry in self._cache.snapshot.entries:
            if entry.primary == primary and entry.secondary and entry.secondary not in result:
                result.append(entry.secondary)
        return result

    # --- Suggestions (FR-9, FR-10) ---

    def suggest_merchant_substrings(self, description: str) -> list[str]:
        """FR-9: candidate substrings, excluding stop words and any word already used
        as a merchant substring in ANY rule (global scope)."""
        taken = {
            part.upper()
            for entry in self._cache.snapshot.entries
            for substring in entry.substrings
            for part in _rule_parts(substring)
        }
        return self._suggest(description, taken)

    def suggest_ignore_patterns(self, description: str) -> list[str]:
        """FR-10: same algorithm, excluding stop words and existing ignore patterns."""
        existing = {
            pattern.strip().upper()
            for pattern in self._cache.snapshot.ignore_patterns
            if pattern.strip()
        }
        return self._suggest(description, existing)

    def _suggest(self, description: str, exclude: set[str]) -> list[str]:
        result: list[str] = []
        for token in candidate_tokens(description):
            if token in self._stop_words or token in exclude or token in result:
                continue
            result.append(token)
        return result
