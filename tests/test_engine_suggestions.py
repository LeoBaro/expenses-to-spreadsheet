"""Categorization Engine — suggestions (FR-9/FR-10)."""

from __future__ import annotations

from expenses.cache.models import CacheSnapshot, CategoryEntry
from expenses.categorization.engine import CategorizationEngine


class _StubCache:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    @property
    def snapshot(self):
        return self._snapshot


def _engine(entries=(), ignore=()):
    snapshot = CacheSnapshot(entries=tuple(entries), ignore_patterns=tuple(ignore))
    return CategorizationEngine(_StubCache(snapshot))


def test_suggest_merchant_substrings_real_example():
    engine = _engine()
    desc = "PAGAMENTO MASTERCARD E-Commerce del 20/07/2025 CARTA *9994 DI EUR 2,99 Google One Dublin"
    # stop words (PAGAMENTO, MASTERCARD, E-COMMERCE, DEL, CARTA, DI, EUR) + digit/short
    # tokens removed → clean merchant candidates remain.
    assert engine.suggest_merchant_substrings(desc) == ["GOOGLE", "ONE", "DUBLIN"]


def test_suggest_excludes_words_already_used_by_any_rule_global():
    engine = _engine([CategoryEntry("Travel", "Transport", ("milano",))])
    # MILANO is already a substring somewhere → excluded globally.
    assert engine.suggest_merchant_substrings("STARBUCKS MILANO") == ["STARBUCKS"]


def test_suggest_dedupes_preserving_order():
    engine = _engine()
    assert engine.suggest_merchant_substrings("Ikea Ikea Store") == ["IKEA", "STORE"]


def test_suggest_ignore_patterns_excludes_existing_and_stopwords():
    engine = _engine(ignore=["revolut"])
    desc = "PAGAMENTO CARTA Revolut Top-Up Milano"
    # PAGAMENTO/CARTA are stop words; REVOLUT already an ignore pattern → excluded.
    assert engine.suggest_ignore_patterns(desc) == ["TOP-UP", "MILANO"]
