"""Inline-keyboard helpers for option prompts (FR-6/7/8)."""

from __future__ import annotations

from collections.abc import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Telegram limits callback_data to 64 bytes.
CALLBACK_DATA_MAX = 64


def options_keyboard(options: Iterable[str], *, prefix: str = "") -> InlineKeyboardMarkup:
    """One button per option, stacked vertically. ``callback_data`` is
    ``prefix + option`` truncated to Telegram's 64-byte limit."""
    rows = [
        [InlineKeyboardButton(text=option, callback_data=f"{prefix}{option}"[:CALLBACK_DATA_MAX])]
        for option in options
    ]
    return InlineKeyboardMarkup(rows)
