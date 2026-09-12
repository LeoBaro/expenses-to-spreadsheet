"""expenses-poll window resolution: default lookback, --month, --from/--to."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import pytest

from expenses.config import Settings
from expenses.poller.cli import _resolve_window


def _args(**overrides) -> argparse.Namespace:
    defaults = {"month": None, "date_from": None, "date_to": None}
    return argparse.Namespace(**{**defaults, **overrides})


def test_default_window_is_lookback_from_today():
    settings = Settings(poll_lookback_days=7)
    date_from, date_to = _resolve_window(_args(), settings)
    assert date_to == date.today()
    assert date_from == date.today() - timedelta(days=7)


def test_month_resolves_to_full_calendar_month():
    date_from, date_to = _resolve_window(_args(month="2026-02"), Settings())
    assert (date_from, date_to) == (date(2026, 2, 1), date(2026, 2, 28))


def test_month_handles_31_day_month():
    date_from, date_to = _resolve_window(_args(month="2026-01"), Settings())
    assert (date_from, date_to) == (date(2026, 1, 1), date(2026, 1, 31))


def test_explicit_range():
    date_from, date_to = _resolve_window(
        _args(date_from="2026-03-10", date_to="2026-03-20"), Settings()
    )
    assert (date_from, date_to) == (date(2026, 3, 10), date(2026, 3, 20))


def test_month_and_range_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _resolve_window(_args(month="2026-02", date_from="2026-02-01"), Settings())


def test_from_requires_to():
    with pytest.raises(SystemExit):
        _resolve_window(_args(date_from="2026-02-01"), Settings())


def test_bad_month_format_raises():
    with pytest.raises(SystemExit):
        _resolve_window(_args(month="not-a-month"), Settings())
