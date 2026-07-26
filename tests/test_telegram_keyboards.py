"""Inline-keyboard construction (TR-6)."""

from __future__ import annotations

from expenses.telegram_bot.keyboards import CALLBACK_DATA_MAX, options_keyboard


def test_one_button_per_option_stacked():
    markup = options_keyboard(["Categorize", "Ignore"])
    rows = markup.inline_keyboard
    assert len(rows) == 2
    assert [row[0].text for row in rows] == ["Categorize", "Ignore"]
    assert rows[0][0].callback_data == "Categorize"


def test_prefix_applied_to_callback_data():
    markup = options_keyboard(["Housing"], prefix="primary:")
    assert markup.inline_keyboard[0][0].callback_data == "primary:Housing"


def test_callback_data_truncated_to_limit():
    long_option = "X" * 100
    markup = options_keyboard([long_option])
    assert len(markup.inline_keyboard[0][0].callback_data) == CALLBACK_DATA_MAX
