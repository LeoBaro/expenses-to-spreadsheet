"""Anti-corruption layer: Enable Banking payload -> internal Transaction (TR-1 DD-2).

Field mappings are grounded in the Enable Banking API reference. Values flagged
here as "confirm" in TR-1 are handled defensively and logged so the first real run
against the API validates them (see scripts entrypoint ``expenses.poller.cli``).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from expenses.domain.transaction import Direction, Transaction, TransactionStatus

logger = logging.getLogger(__name__)

# Enable Banking's validated enum is exactly CRDT / DBIT (ISO 20022); it rejects
# other values on both read and write. Anything unexpected maps to UNKNOWN below
# and is excluded, so classification fails safe.
_DEBIT_INDICATORS = {"DBIT"}
_CREDIT_INDICATORS = {"CRDT"}

_BOOKED_STATUSES = {"BOOK", "BOOKED"}
_PENDING_STATUSES = {"PDNG", "PENDING"}


class TransactionMappingError(ValueError):
    """Raised when a payload cannot be mapped (e.g. no usable date/amount)."""


def to_transaction(raw: dict[str, Any]) -> Transaction:
    direction = _map_direction(raw.get("credit_debit_indicator"))
    status = _map_status(raw.get("status"))
    amount, currency = _map_amount(raw.get("transaction_amount"))
    booking_date = _map_booking_date(raw)
    description = _map_description(raw)
    transaction_id, id_is_derived = _identity(raw, booking_date, amount, currency, direction, description)

    return Transaction(
        id=transaction_id,
        description=description,
        amount=amount,
        currency=currency,
        booking_date=booking_date,
        status=status,
        direction=direction,
        id_is_derived=id_is_derived,
        raw=raw,
    )


def is_settled_debit(transaction: Transaction) -> bool:
    """FR-1: only settled (BOOKED) debit transactions are processed."""
    return transaction.is_settled_debit


def _map_direction(indicator: Any) -> Direction:
    if indicator in _DEBIT_INDICATORS:
        return Direction.DEBIT
    if indicator in _CREDIT_INDICATORS:
        return Direction.CREDIT
    logger.warning("unknown credit_debit_indicator %r; treating as UNKNOWN", indicator)
    return Direction.UNKNOWN


def _map_status(status: Any) -> TransactionStatus:
    if status in _BOOKED_STATUSES:
        return TransactionStatus.BOOKED
    if status in _PENDING_STATUSES:
        return TransactionStatus.PENDING
    logger.warning("unknown transaction status %r; treating as OTHER", status)
    return TransactionStatus.OTHER


def _map_amount(amount_obj: Any) -> tuple[Decimal, str]:
    if not isinstance(amount_obj, dict):
        raise TransactionMappingError(f"transaction_amount missing or malformed: {amount_obj!r}")
    try:
        # Enable Banking returns a non-negative decimal string; direction is separate.
        amount = Decimal(str(amount_obj["amount"]))
    except (KeyError, InvalidOperation) as exc:
        raise TransactionMappingError(f"invalid amount: {amount_obj!r}") from exc
    currency = amount_obj.get("currency", "")
    if amount < 0:
        # Unexpected per the docs; normalise and record it.
        logger.warning("negative amount %s encountered; using absolute value", amount)
        amount = -amount
    return amount, currency


def _map_booking_date(raw: dict[str, Any]) -> date:
    # FR-12 routes expenses by booking date; fall back to value/transaction date.
    for key in ("booking_date", "value_date", "transaction_date"):
        value = raw.get(key)
        if value:
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                logger.warning("unparseable %s %r", key, value)
                continue
            if key != "booking_date":
                logger.warning("booking_date missing; falling back to %s (%s)", key, parsed)
            return parsed
    raise TransactionMappingError("no usable date on transaction")


def _map_description(raw: dict[str, Any]) -> str:
    remittance = raw.get("remittance_information")
    if isinstance(remittance, list) and remittance:
        text = " ".join(str(part).strip() for part in remittance if str(part).strip())
        if text:
            return text
    # Fall back to the counterparty name, then the entry reference.
    creditor = raw.get("creditor")
    if isinstance(creditor, dict) and creditor.get("name"):
        return str(creditor["name"]).strip()
    entry_reference = raw.get("entry_reference")
    if entry_reference:
        return str(entry_reference).strip()
    logger.warning("transaction has no description-like field")
    return ""


def _identity(
    raw: dict[str, Any],
    booking_date: date,
    amount: Decimal,
    currency: str,
    direction: Direction,
    description: str,
) -> tuple[str, bool]:
    """Prefer the provider's transaction_id; derive a stable hash when absent.

    Not all ASPSPs return a stable ``transaction_id`` (Enable Banking documents
    this), which directly affects the idempotency key relied on by TR-7.
    """
    provider_id = raw.get("transaction_id")
    if provider_id:
        return str(provider_id), False

    seed = "|".join(
        [
            str(raw.get("entry_reference") or ""),
            booking_date.isoformat(),
            f"{amount}",
            currency,
            direction.value,
            description,
        ]
    )
    derived = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    logger.info("no provider transaction_id; derived id %s from %r", derived[:12], seed)
    return f"derived:{derived}", True
