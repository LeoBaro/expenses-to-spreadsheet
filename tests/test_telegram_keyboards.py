"""Inline-keyboard construction (TR-6)."""

from __future__ import annotations

from expenses.telegram_bot.keyboards import (
    BACK_ACTION,
    DONE_ACTION,
    NEXT_MONTH_ACTION,
    PREV_MONTH_ACTION,
    SKIP_ACTION,
    options_keyboard,
)


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


def test_done_and_skip_buttons_appended_in_order():
    markup = options_keyboard(
        ["APCOA", "PARCHEGGIO"], tag="mer", done_label="✓ Done", skip_label="⏭ Skip"
    )
    rows = markup.inline_keyboard
    assert len(rows) == 4  # two options + Done + Skip
    assert rows[-2][0].callback_data == f"mer:{DONE_ACTION}"
    assert rows[-1][0].text == "⏭ Skip"
    assert rows[-1][0].callback_data == f"mer:{SKIP_ACTION}"


def test_skip_without_done():
    markup = options_keyboard(["A", "B"], tag="mer", skip_label="⏭ Skip")
    rows = markup.inline_keyboard
    assert len(rows) == 3  # two options + Skip (no Done)
    assert rows[-1][0].callback_data == f"mer:{SKIP_ACTION}"


def test_month_navigation_shares_one_row_and_back_is_last():
    markup = options_keyboard(
        ["Categorize", "Ignore"],
        tag="act",
        prev_label="< Prev month",
        next_label="Next month >",
        back_label="↩ Back",
    )
    rows = markup.inline_keyboard
    assert len(rows) == 4  # two options + nav row + Back
    assert [b.callback_data for b in rows[2]] == [f"act:{PREV_MONTH_ACTION}", f"act:{NEXT_MONTH_ACTION}"]
    assert rows[-1][0].callback_data == f"act:{BACK_ACTION}"


def test_single_month_button_when_at_the_edge():
    markup = options_keyboard(["A"], tag="act", next_label="Next month >")
    rows = markup.inline_keyboard
    assert [b.callback_data for b in rows[1]] == [f"act:{NEXT_MONTH_ACTION}"]


def test_back_comes_after_done_and_skip():
    markup = options_keyboard(["A"], tag="mer", done_label="✓", skip_label="⏭", back_label="↩")
    data = [row[0].callback_data for row in markup.inline_keyboard]
    assert data == ["mer:0", f"mer:{DONE_ACTION}", f"mer:{SKIP_ACTION}", f"mer:{BACK_ACTION}"]
