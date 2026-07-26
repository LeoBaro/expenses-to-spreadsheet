"""The canonical internal Transaction model (owned by TR-1).

This is the shape passed between the Poller, Processor, Categorization Engine,
Sheets Client and State Manager. It is deliberately free of any Enable Banking or
framework types: the mapping from the provider payload lives in the adapter
(``expenses.poller.enable_banking.adapter``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class Direction(Enum):
    """Whether money left (DEBIT) or entered (CREDIT) the account."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    UNKNOWN = "UNKNOWN"


class TransactionStatus(Enum):
    """Settlement status. BOOKED == settled (FR-1)."""

    BOOKED = "BOOKED"
    PENDING = "PENDING"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class Transaction:
    """A single bank transaction in the application's own vocabulary.

    ``amount`` is always non-negative; the sign/direction is carried by
    ``direction`` (matching Enable Banking, which never returns negative amounts).
    """

    id: str
    description: str
    amount: Decimal
    currency: str
    booking_date: date
    status: TransactionStatus
    direction: Direction
    # True when ``id`` was derived by us because the provider gave no stable
    # transaction id. Relevant to idempotency (TR-7).
    id_is_derived: bool = False
    # Original provider payload, kept for debugging/observability only.
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_settled_debit(self) -> bool:
        """FR-1: only settled debit transactions represent processable expenses."""
        return self.status is TransactionStatus.BOOKED and self.direction is Direction.DEBIT
