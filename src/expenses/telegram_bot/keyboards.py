"""Inline-keyboard helpers for option prompts (FR-6/7/8)."""

from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Telegram limits callback_data to 64 bytes.
CALLBACK_DATA_MAX = 64

# Callback suffix for the "Done" button of a multi-select step (e.g. building an
# AND-combination merchant rule). Distinct from the numeric option indices.
DONE_ACTION = "done"


def options_keyboard(
    options: Sequence[str], *, tag: str = "", done_label: str | None = None
) -> InlineKeyboardMarkup:
    """One button per option, stacked vertically.

    ``callback_data`` encodes the step ``tag`` and the option's **index** —
    ``f"{tag}:{i}"`` — never the option text. Indices keep callback data tiny and
    robust: category names can be long or contain colons, and Telegram caps
    callback_data at 64 bytes. The receiver (the Processor's conversation
    orchestrator) maps the index back to the option it presented.

    When ``done_label`` is given, a final confirm button is appended with
    ``callback_data = f"{tag}:{DONE_ACTION}"`` — used by the additive multi-select
    step to finalize a selection. Only the callback data is length-constrained; the
    label text (which may preview the built rule) is not.
    """
    rows = [
        [InlineKeyboardButton(text=option, callback_data=f"{tag}:{index}")]
        for index, option in enumerate(options)
    ]
    if done_label is not None:
        rows.append([InlineKeyboardButton(text=done_label, callback_data=f"{tag}:{DONE_ACTION}")])
    return InlineKeyboardMarkup(rows)
