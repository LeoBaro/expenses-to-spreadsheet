"""Cache Manager tests (TR-5)."""

from __future__ import annotations

import dataclasses

import pytest

from expenses.cache.manager import CacheManager
from expenses.sheets.models import SupportRow


class _FakeSource:
    def __init__(self, support, ignore):
        self._support = support
        self._ignore = ignore
        self.support_calls = 0
        self.ignore_calls = 0

    async def load_support(self):
        self.support_calls += 1
        return self._support

    async def load_ignore_patterns(self):
        self.ignore_calls += 1
        return self._ignore


async def test_snapshot_empty_before_refresh():
    cache = CacheManager(_FakeSource([], []))
    assert cache.snapshot.entries == ()
    assert cache.snapshot.ignore_patterns == ()


async def test_refresh_builds_snapshot_from_source():
    source = _FakeSource(
        [
            SupportRow("Housing", "Electricity", ["nwg", "sorgenia"]),
            SupportRow("Groceries", "Groceries general", ["coop"]),
        ],
        ["revolut", "amazon"],
    )
    cache = CacheManager(source)

    snap = await cache.refresh()

    assert cache.snapshot is snap  # stored
    assert len(snap.entries) == 2
    assert snap.entries[0].primary == "Housing"
    assert snap.entries[0].secondary == "Electricity"
    assert snap.entries[0].substrings == ("nwg", "sorgenia")  # tuple, not list
    assert snap.ignore_patterns == ("revolut", "amazon")


async def test_refresh_replaces_snapshot_and_keeps_old_one_intact():
    source = _FakeSource([SupportRow("A", "B", [])], ["x"])
    cache = CacheManager(source)
    old = await cache.refresh()

    source._support = [SupportRow("C", "D", ["z"])]
    source._ignore = []
    new = await cache.refresh()

    assert [e.primary for e in new.entries] == ["C"]
    assert new.ignore_patterns == ()
    # The previously handed-out snapshot is unchanged (immutable swap).
    assert [e.primary for e in old.entries] == ["A"]
    assert old.ignore_patterns == ("x",)


async def test_snapshot_is_immutable():
    cache = CacheManager(_FakeSource([SupportRow("A", "B", [])], []))
    snap = await cache.refresh()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.entries = ()  # type: ignore[misc]
