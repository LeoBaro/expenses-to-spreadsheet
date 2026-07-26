"""Append-only processed-transaction store (TR-7).

Layers (per the spec):
- an in-memory ``set`` for O(1) ``is_processed`` (no I/O);
- an append-only file, one identifier per line, that is the durable source of truth.

``mark_processed`` appends + fsyncs *before* updating the in-memory set (DD-2), so
"immediately persisted" (FR-13) is a real guarantee. Synchronous by design: reads are
pure memory, and a local append + fsync is fast; within the single asyncio loop a sync
call runs to completion, so no locking is needed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._ids: set[str] = set()

    def load(self) -> None:
        """Replay the state file into memory (call once at startup, before processing).

        Tolerates a missing file and blank/partial trailing lines (DD-5): every
        non-empty line is simply added as an id, so a truncated crash-time line becomes
        a harmless bogus id that never matches a real transaction.
        """
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                identifier = line.strip()
                if identifier:
                    self._ids.add(identifier)
        logger.info("loaded %d processed transaction ids from %s", len(self._ids), self._path)

    def is_processed(self, transaction_id: str) -> bool:
        """Pure in-memory membership check."""
        return transaction_id in self._ids

    def mark_processed(self, transaction_id: str) -> None:
        """Durably record an id, then remember it. No-op if already recorded."""
        if transaction_id in self._ids:
            return
        self._append(transaction_id)  # durable first (DD-2)
        self._ids.add(transaction_id)

    def _append(self, transaction_id: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(f"{transaction_id}\n")
            handle.flush()
            os.fsync(handle.fileno())
