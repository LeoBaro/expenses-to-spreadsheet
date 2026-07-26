"""The Categorization Engine: matching, suggestion and category queries (TR-3)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from expenses.cache.models import CacheSnapshot
from expenses.categorization.models import MatchResult
from expenses.categorization.stopwords import DEFAULT_STOP_WORDS
from expenses.categorization.tokens import candidate_tokens


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
        """FR-3: the longest merchant substring contained in the description wins;
        ties resolved by sheet order (first defined). None if nothing matches."""
        haystack = description.lower()
        best: MatchResult | None = None
        best_len = 0
        for entry in self._cache.snapshot.entries:
            for substring in entry.substrings:
                needle = substring.strip().lower()
                if needle and needle in haystack and len(needle) > best_len:
                    best = MatchResult(entry.primary, entry.secondary, substring)
                    best_len = len(needle)
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
            substring.strip().upper()
            for entry in self._cache.snapshot.entries
            for substring in entry.substrings
            if substring.strip()
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
