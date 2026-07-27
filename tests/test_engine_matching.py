"""Categorization Engine — matching + category queries (FR-3/4/5/7)."""

from __future__ import annotations

from expenses.cache.models import CacheSnapshot, CategoryEntry
from expenses.categorization.engine import CategorizationEngine


class _StubCache:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    @property
    def snapshot(self):
        return self._snapshot


def _engine(entries, ignore=()):
    snapshot = CacheSnapshot(entries=tuple(entries), ignore_patterns=tuple(ignore))
    return CategorizationEngine(_StubCache(snapshot))


def test_match_merchant_longest_substring_wins():
    engine = _engine(
        [
            CategoryEntry("Groceries", "General", ("coop",)),
            CategoryEntry("Groceries", "Supermarket", ("coop supermercato",)),
        ]
    )
    result = engine.match_merchant("SPESA COOP SUPERMERCATO MILANO")
    assert result.secondary == "Supermarket"
    assert result.substring == "coop supermercato"


def test_match_merchant_tie_break_is_sheet_order():
    engine = _engine(
        [
            CategoryEntry("Cat1", "A", ("abcd",)),
            CategoryEntry("Cat2", "B", ("wxyz",)),
        ]
    )
    result = engine.match_merchant("... abcd ... wxyz ...")  # both len 4
    assert result.primary == "Cat1"  # first defined wins


def test_match_merchant_case_insensitive_and_trimmed():
    engine = _engine([CategoryEntry("Housing", "Electricity", ("  Sorgenia  ",))])
    result = engine.match_merchant("addebito sorgenia spa")
    assert result.primary == "Housing"


def test_match_merchant_no_match_returns_none():
    engine = _engine([CategoryEntry("Housing", "Gas", ("edison",))])
    assert engine.match_merchant("random description") is None


def test_and_combination_requires_all_parts():
    engine = _engine([CategoryEntry("Transport", "Parking", ("apcoa+parcheggio",))])
    # Both words present (position-independent) → matches.
    assert engine.match_merchant("APCOA PARCHEGGIO PIAZZ").secondary == "Parking"
    assert engine.match_merchant("PARCHEGGIO ... APCOA").secondary == "Parking"
    # Only one part present → no match.
    assert engine.match_merchant("APCOA GENOVA") is None
    assert engine.match_merchant("PARCHEGGIO CENTRO") is None


def test_and_combination_outranks_single_word():
    engine = _engine(
        [
            CategoryEntry("Transport", "Generic", ("apcoa",)),
            CategoryEntry("Transport", "Parking", ("apcoa+parcheggio",)),
        ]
    )
    # Combined length (5+10) beats the single "apcoa" (5), so the combination wins.
    result = engine.match_merchant("APCOA PARCHEGGIO PIAZZA MANIN")
    assert result.secondary == "Parking"
    assert result.substring == "apcoa+parcheggio"


def test_single_word_still_wins_when_combination_incomplete():
    engine = _engine(
        [
            CategoryEntry("Transport", "Generic", ("apcoa",)),
            CategoryEntry("Transport", "Parking", ("apcoa+parcheggio",)),
        ]
    )
    # "parcheggio" absent → combination doesn't fire; single word still matches.
    result = engine.match_merchant("APCOA GENOVA SRL")
    assert result.secondary == "Generic"


def test_find_ignore_match():
    engine = _engine([], ignore=["Revolut", "amazon prime"])
    assert engine.find_ignore_match("Top-up from REVOLUT account") == "Revolut"
    assert engine.find_ignore_match("grocery store") is None


def test_list_primaries_and_secondaries_ordered_unique():
    engine = _engine(
        [
            CategoryEntry("Housing", "Rent", ()),
            CategoryEntry("Housing", "Gas", ()),
            CategoryEntry("Groceries", "General", ()),
            CategoryEntry("Housing", "Rent", ()),  # duplicate
        ]
    )
    assert engine.list_primaries() == ["Housing", "Groceries"]
    assert engine.list_secondaries("Housing") == ["Rent", "Gas"]
    assert engine.list_secondaries("Groceries") == ["General"]
