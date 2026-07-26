"""Cache Manager (TR-5).

An in-memory snapshot of the Support + Ignore data, rebuilt from the Google Sheets
Client (TR-4). A **dumb store**: it holds the data but does not interpret it —
category semantics and matching live in the Categorization Engine (TR-3).
"""

from expenses.cache.manager import CacheManager, SupportSource
from expenses.cache.models import CacheSnapshot, CategoryEntry

__all__ = ["CacheManager", "SupportSource", "CacheSnapshot", "CategoryEntry"]
