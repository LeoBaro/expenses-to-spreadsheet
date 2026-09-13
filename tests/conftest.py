"""Shared test fixtures: sample Enable Banking transaction payloads.

Shapes follow the Enable Banking API reference. These doubles are what let us
pin the adapter's behaviour without live API access.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def booked_debit() -> dict:
    return {
        "transaction_id": "tx-1001",
        "entry_reference": "5561990681",
        "booking_date": "2026-07-20",
        "value_date": "2026-07-21",
        "transaction_date": "2026-07-19",
        "transaction_amount": {"currency": "EUR", "amount": "12.90"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "remittance_information": ["PAGAMENTO CARTA STARBUCKS MILANO"],
    }


@pytest.fixture
def pending_debit() -> dict:
    return {
        "transaction_id": "tx-1002",
        "booking_date": "2026-07-22",
        "transaction_amount": {"currency": "EUR", "amount": "5.00"},
        "credit_debit_indicator": "DBIT",
        "status": "PDNG",
        "remittance_information": ["BAR ROMA"],
    }


@pytest.fixture
def booked_credit() -> dict:
    return {
        "transaction_id": "tx-1003",
        "booking_date": "2026-07-18",
        "transaction_amount": {"currency": "EUR", "amount": "1500.00"},
        "credit_debit_indicator": "CRDT",
        "status": "BOOK",
        "remittance_information": ["SALARY"],
    }


@pytest.fixture
def zero_amount_debit() -> dict:
    return {
        "transaction_id": "tx-1004",
        "booking_date": "2026-07-23",
        "transaction_amount": {"currency": "EUR", "amount": "0.00"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "remittance_information": ["AUTHORIZATION HOLD"],
    }


@pytest.fixture
def debit_without_id() -> dict:
    return {
        "entry_reference": "REF-XYZ",
        "booking_date": "2026-07-15",
        "transaction_amount": {"currency": "EUR", "amount": "3.40"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "remittance_information": ["EDICOLA"],
    }
