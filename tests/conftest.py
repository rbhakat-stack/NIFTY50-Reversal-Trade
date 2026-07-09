"""Shared fixtures: a synthetic NIFTY-like price history for deterministic tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_price_series(start_date: str, num_days: int, start_price: float = 1000.0, daily_drift: float = 0.0004, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start_date, periods=num_days)
    noise = rng.normal(0, 0.01, size=num_days)
    log_returns = daily_drift + noise
    log_prices = np.log(start_price) + np.cumsum(log_returns)
    close = np.exp(log_prices)
    open_price = close * (1 + rng.normal(0, 0.002, size=num_days))
    high = np.maximum(open_price, close) * (1 + np.abs(rng.normal(0, 0.003, size=num_days)))
    low = np.minimum(open_price, close) * (1 - np.abs(rng.normal(0, 0.003, size=num_days)))
    volume = rng.integers(1_000_000, 5_000_000, size=num_days)

    return pd.DataFrame(
        {
            "trade_date": [d.date() for d in dates],
            "open_price": open_price,
            "high_price": high,
            "low_price": low,
            "close_price": close,
            "volume": volume,
            "data_source": "SYNTHETIC",
        }
    )


@pytest.fixture
def synthetic_price_history() -> pd.DataFrame:
    """~6 years of synthetic daily OHLC data with a mild upward drift and noise."""
    return _make_price_series("2018-01-01", 1500)


@pytest.fixture
def small_price_history() -> pd.DataFrame:
    return _make_price_series("2020-01-01", 40)
