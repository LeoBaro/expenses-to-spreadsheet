"""Errors raised by the Google Sheets Client."""

from __future__ import annotations


class SheetsError(Exception):
    """Base class for Sheets client errors."""


class SheetNotFoundError(SheetsError):
    """The target monthly sheet does not exist (FR-12 fails loudly)."""


class RuleRowNotFoundError(SheetsError):
    """No Support row matches the given (Primary, Secondary) category (FR-11)."""
