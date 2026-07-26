"""Candidate tokenization (FR-9/FR-10)."""

from __future__ import annotations

from expenses.categorization.tokens import candidate_tokens


def test_uppercases_and_strips_surrounding_punctuation():
    assert candidate_tokens("Starbucks, milano.") == ["STARBUCKS", "MILANO"]


def test_drops_short_and_digit_tokens():
    desc = "PAGAMENTO CARTA *9994 DI EUR 2,99 del 20/07/2025 Google One Dublin"
    tokens = candidate_tokens(desc)
    # digits/short removed; alphabetic words (incl. stop words) kept at this stage
    assert "GOOGLE" in tokens and "ONE" in tokens and "DUBLIN" in tokens
    assert all(not any(c.isdigit() for c in t) for t in tokens)
    assert "DI" not in [t for t in tokens if len(t) < 2]  # 1-char dropped
    assert "*9994" not in tokens and "2,99" not in tokens


def test_iban_and_codes_dropped():
    assert candidate_tokens("da IT340010000012874490159 EFAT034929426") == ["DA"]
