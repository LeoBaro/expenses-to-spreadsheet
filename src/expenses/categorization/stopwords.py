"""Configurable stop-word list (FR-9/FR-10).

Generic bank-transaction vocabulary that must never be offered as a merchant
substring or ignore pattern (e.g. picking "PAGAMENTO" would match nearly every card
transaction). Tuned to Italian bank phrasing — **edit this set** as you spot noise
words in real suggestions. Compared case-insensitively (stored/compared uppercase).
"""

from __future__ import annotations

DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        # payment / transaction mechanics
        "PAGAMENTO", "PAGAMENTI", "ADDEBITO", "ADDEBITI", "ACCREDITO", "ACCREDITI",
        "BONIFICO", "VERSAMENTO", "PRELIEVO", "INCASSO", "RIMBORSO", "STORNO",
        "COMMISSIONE", "COMMISSIONI", "CANONE", "IMPOSTA", "BOLLO", "SPESE",
        # cards / instruments
        "CARTA", "CARTE", "MASTERCARD", "VISA", "MAESTRO", "BANCOMAT",
        "PAGOBANCOMAT", "POS",
        # SEPA / direct debit / invoicing
        "SEPA", "DD", "SDD", "RID", "MANDATO", "FATTURA", "FATTURE", "BOLLETTA",
        # company forms (as they survive tokenization)
        "S.P.A", "S.P.A.", "S.R.L", "S.R.L.", "S.N.C", "S.N.C.",
        # Italian articles / prepositions (2+ chars; 1-char ones are dropped anyway)
        "DEL", "DELLA", "DELLO", "DEI", "DEGLI", "DELLE", "DI", "DA", "DAL",
        "DALLA", "IL", "LO", "LA", "GLI", "LE", "PER", "CON", "SU", "TRA", "FRA",
        "ED", "AL", "ALLA", "AI", "AGLI", "NEL", "NELLA",
        # misc noise
        "NR", "EUR", "USD", "GBP", "ECOMMERCE", "E-COMMERCE", "ONLINE",
        "VOSTRO", "NOSTRO", "CARICO",
    }
)
