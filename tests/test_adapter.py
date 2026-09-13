"""Adapter tests — these encode the answers to TR-1's schema open questions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expenses.domain.transaction import Direction, TransactionStatus
from expenses.poller.enable_banking import adapter


def test_maps_booked_debit_fields(booked_debit):
    t = adapter.to_transaction(booked_debit)
    assert t.id == "tx-1001"
    assert t.id_is_derived is False
    assert t.amount == Decimal("12.90")
    assert t.currency == "EUR"
    assert t.booking_date == date(2026, 7, 20)
    assert t.direction is Direction.DEBIT
    assert t.status is TransactionStatus.BOOKED
    assert t.description == "PAGAMENTO CARTA STARBUCKS MILANO"


def test_amount_is_non_negative_direction_from_indicator(booked_debit):
    # Enable Banking never signs the amount; direction is carried separately.
    t = adapter.to_transaction(booked_debit)
    assert t.amount > 0
    assert t.direction is Direction.DEBIT


def test_settled_debit_filter(booked_debit, pending_debit, booked_credit):
    assert adapter.is_expense(adapter.to_transaction(booked_debit)) is True
    # Pending is not settled.
    assert adapter.is_expense(adapter.to_transaction(pending_debit)) is False
    # Credit is not an expense.
    assert adapter.is_expense(adapter.to_transaction(booked_credit)) is False


def test_zero_amount_settled_debit_is_not_an_expense(zero_amount_debit):
    # DD-6: a zero-amount settled debit (e.g. an authorization hold) is not an expense.
    t = adapter.to_transaction(zero_amount_debit)
    assert t.amount == Decimal("0")
    assert adapter.is_expense(t) is False


def test_maps_dbit_to_debit(debit_without_id):
    # DBIT is Enable Banking's canonical debit indicator (it rejects DRWT).
    t = adapter.to_transaction(debit_without_id)
    assert t.direction is Direction.DEBIT


def test_derives_stable_id_when_provider_id_missing(debit_without_id):
    t1 = adapter.to_transaction(debit_without_id)
    t2 = adapter.to_transaction(dict(debit_without_id))
    assert t1.id_is_derived is True
    assert t1.id.startswith("derived:")
    # Deterministic: same payload -> same id (idempotency for TR-7).
    assert t1.id == t2.id


def test_unknown_indicator_becomes_unknown_and_is_not_expense(booked_debit):
    booked_debit["credit_debit_indicator"] = "WAT"
    t = adapter.to_transaction(booked_debit)
    assert t.direction is Direction.UNKNOWN
    assert adapter.is_expense(t) is False


def test_booking_date_falls_back_to_value_date():
    raw = {
        "transaction_id": "tx-x",
        "value_date": "2026-07-11",
        "transaction_amount": {"currency": "EUR", "amount": "1.00"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "remittance_information": ["X"],
    }
    t = adapter.to_transaction(raw)
    assert t.booking_date == date(2026, 7, 11)


def test_malformed_amount_raises_mapping_error(booked_debit):
    booked_debit["transaction_amount"] = {"currency": "EUR", "amount": "not-a-number"}
    try:
        adapter.to_transaction(booked_debit)
    except adapter.TransactionMappingError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected TransactionMappingError")
