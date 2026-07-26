"""Categorization Engine (TR-3).

Pure business logic for matching (FR-3/4/5), suggestion (FR-9/10) and category
listing (FR-7). Reads the cache snapshot (TR-5) only — independent of Google Sheets,
Telegram and Enable Banking. Stateless: every call reads the current snapshot.
"""

from expenses.categorization.engine import CacheView, CategorizationEngine
from expenses.categorization.models import MatchResult
from expenses.categorization.stopwords import DEFAULT_STOP_WORDS

__all__ = ["CategorizationEngine", "CacheView", "MatchResult", "DEFAULT_STOP_WORDS"]
