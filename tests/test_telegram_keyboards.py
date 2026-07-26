"""Inline-keyboard construction (TR-6)."""

from __future__ import annotations

from expenses.telegram_bot.keyboards import options_keyboard


def test_one_button_per_option_stacked():
    markup = options_keyboard(["Categorize", "Ignore"])
    rows = markup.inline_keyboard
    assert len(rows) == 2
    assert [row[0].text for row in rows] == ["Categorize", "Ignore"]


def test_callback_data_is_tag_and_index():
    markup = options_keyboard(["Housing", "Food"], tag="pri")
    data = [row[0].callback_data for row in markup.inline_keyboard]
    assert data == ["pri:0", "pri:1"]


def test_index_encoding_is_immune_to_long_or_colon_names():
    long_option = "X" * 100 + ":weird"
    markup = options_keyboard([long_option], tag="sec")
    # Index encoding stays tiny regardless of the option text.
    assert markup.inline_keyboard[0][0].callback_data == "sec:0"
    assert markup.inline_keyboard[0][0].text == long_option
