"""Immutable cache data types, deliberately independent of the Sheets layer.

The Categorization Engine (TR-3) reads these; it never sees TR-4's ``SupportRow``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategoryEntry:
    """One (Primary, Secondary) category and its merchant substrings, in sheet order."""

    primary: str
    secondary: str
    substrings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    """A complete, immutable view of the cached data. The Cache swaps the whole
    snapshot atomically on refresh, so any reader holding one sees a consistent view."""

    entries: tuple[CategoryEntry, ...]
    ignore_patterns: tuple[str, ...]
