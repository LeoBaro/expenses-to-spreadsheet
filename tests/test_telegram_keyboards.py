"""Inline-keyboard construction (TR-6)."""

from __future__ import annotations

from expenses.telegram_bot.keyboards import DONE_ACTION, options_keyboard


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


def test_done_label_appends_a_confirm_button():
    markup = options_keyboard(["APCOA", "PARCHEGGIO"], tag="mer", done_label="✓ Done")
    rows = markup.inline_keyboard
    assert len(rows) == 3  # two options + Done
    assert rows[-1][0].text == "✓ Done"
    assert rows[-1][0].callback_data == f"mer:{DONE_ACTION}"


def test_no_done_button_without_label():
    markup = options_keyboard(["A", "B"], tag="mer")
    assert len(markup.inline_keyboard) == 2  # no Done row
