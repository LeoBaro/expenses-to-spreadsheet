"""The Cache Manager: holds an immutable snapshot, rebuilt from the source (TR-4)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol, runtime_checkable

from expenses.cache.models import CacheSnapshot, CategoryEntry

logger = logging.getLogger(__name__)


@runtime_checkable
class SupportSource(Protocol):
    """What the cache needs from the Google Sheets Client (TR-4)."""

    async def load_support(self) -> list: ...
    async def load_ignore_patterns(self) -> list[str]: ...


class CacheManager:
    def __init__(self, source: SupportSource) -> None:
        self._source = source
        self._snapshot = CacheSnapshot(entries=(), ignore_patterns=())
        self._lock = asyncio.Lock()

    @property
    def snapshot(self) -> CacheSnapshot:
        """The current snapshot. Reading the reference is atomic, so concurrent
        readers always see a complete, consistent view (never a half-built one)."""
        return self._snapshot

    async def refresh(self) -> CacheSnapshot:
        """Full rebuild from the source (FR-2 startup, FR-14 after writes).

        Loads new data first, then swaps the snapshot in a single assignment. The
        lock prevents two refreshes from doing redundant concurrent loads.
        """
        async with self._lock:
            support = await self._source.load_support()
            ignore = await self._source.load_ignore_patterns()
            entries = tuple(
                CategoryEntry(
                    primary=row.primary,
                    secondary=row.secondary,
                    substrings=tuple(row.substrings),
                )
                for row in support
            )
            self._snapshot = CacheSnapshot(entries=entries, ignore_patterns=tuple(ignore))
            logger.info(
                "cache refreshed: %d category rows, %d ignore patterns",
                len(entries),
                len(self._snapshot.ignore_patterns),
            )
            return self._snapshot
