"""Inline-keyboard helpers for option prompts (FR-6/7/8)."""

from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Telegram limits callback_data to 64 bytes.
CALLBACK_DATA_MAX = 64


def options_keyboard(options: Sequence[str], *, tag: str = "") -> InlineKeyboardMarkup:
    """One button per option, stacked vertically.

    ``callback_data`` encodes the step ``tag`` and the option's **index** —
    ``f"{tag}:{i}"`` — never the option text. Indices keep callback data tiny and
    robust: category names can be long or contain colons, and Telegram caps
    callback_data at 64 bytes. The receiver (the Processor's conversation
    orchestrator) maps the index back to the option it presented.
    """
    rows = [
        [InlineKeyboardButton(text=option, callback_data=f"{tag}:{index}")]
        for index, option in enumerate(options)
    ]
    return InlineKeyboardMarkup(rows)
