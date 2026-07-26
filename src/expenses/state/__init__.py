"""State Manager (TR-7).

Guarantees idempotent processing (FR-13): tracks processed transaction identifiers in
an append-only local file, mirrored by an in-memory set for O(1) membership checks.
Runtime state, not business data.
"""

from expenses.state.manager import StateManager

__all__ = ["StateManager"]
