"""
Trading-day calendar utilities.

The NSE trading calendar is not identical to a plain business-day (Mon-Fri)
calendar because of exchange holidays. Rather than hard-coding a holiday
list (which drifts out of date), "trading day" is defined operationally as
"a date for which we have a validated OHLC row in `nifty_daily_prices`".
Business-day generation is used only to *flag* candidate missing dates for
human review, never to assume a date must have traded.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def is_weekday(d: date) -> bool:
    return pd.Timestamp(d).dayofweek < 5


def business_days_between(start_date: date, end_date: date) -> pd.DatetimeIndex:
    """All Mon-Fri calendar dates between start and end (inclusive)."""
    if start_date > end_date:
        return pd.DatetimeIndex([])
    return pd.bdate_range(start=start_date, end=end_date)


def find_missing_business_days(trading_dates: pd.Series | list[date], start_date: date, end_date: date) -> list[date]:
    """
    Business days (Mon-Fri) within [start_date, end_date] that have no
    corresponding row in `trading_dates`. These are *candidates* for missing
    data (exchange holidays will also show up here) and must be surfaced to
    the user rather than silently dropped or silently assumed to be holidays.
    """
    observed = pd.to_datetime(pd.Series(list(trading_dates))).dt.normalize()
    observed_set = set(observed)
    candidates = business_days_between(start_date, end_date)
    missing = [d.date() for d in candidates if d not in observed_set]
    return missing


def add_trading_day_index(df: pd.DataFrame, date_col: str = "trade_date") -> pd.DataFrame:
    """Attach a sequential trading_day_index column (0-based), sorted ascending by date."""
    out = df.sort_values(date_col).reset_index(drop=True).copy()
    out["trading_day_index"] = np.arange(len(out))
    return out


def get_next_trading_day(current_date: date, available_dates: pd.Series | list[date]) -> date | None:
    """
    Return the first available trading date strictly after current_date, or
    None. `current_date` is coerced via `to_date()` because callers often pass
    a value straight out of a Supabase row (e.g. `latest_signal["signal_date"]`),
    which PostgREST serializes as an ISO date *string*, not a `datetime.date`.
    """
    current_date = to_date(current_date)
    dates = sorted(pd.to_datetime(pd.Series(list(available_dates))).dt.date.unique())
    for d in dates:
        if d > current_date:
            return d
    return None


def get_previous_trading_day(current_date: date, available_dates: pd.Series | list[date]) -> date | None:
    """
    Return the last available trading date strictly before current_date, or
    None. `current_date` is coerced via `to_date()` for the same reason as
    `get_next_trading_day` above.
    """
    current_date = to_date(current_date)
    dates = sorted(pd.to_datetime(pd.Series(list(available_dates))).dt.date.unique())
    prev = None
    for d in dates:
        if d >= current_date:
            break
        prev = d
    return prev


def to_date(value) -> date:
    """Coerce strings/Timestamps/datetimes to a plain date object."""
    return pd.Timestamp(value).date()
