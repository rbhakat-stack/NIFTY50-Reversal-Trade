"""
Benchmark comparison.

Benchmark A (matched cashflow): every time the strategy deploys or withdraws
cash, the benchmark does the same INR amount in NIFTY at the same next-day
open price. This isolates "did the trend/deviation timing rule beat simply
buying/selling NIFTY on the same cashflow schedule".

Benchmark B (lump sum): the strategy's total net invested capital is
assumed fully invested in NIFTY from the first execution date onward. This
isolates "did timing add value versus a simple buy-and-hold of the same
capital".
"""
from __future__ import annotations

import pandas as pd

from src import config


def _first_execution_price(trades_df: pd.DataFrame, price_df: pd.DataFrame) -> tuple[pd.Timestamp, float] | None:
    if trades_df.empty:
        return None
    first_date = trades_df["execution_date"].min()
    row = price_df.loc[price_df["trade_date"] == first_date]
    if row.empty:
        return None
    return first_date, float(row["open_price"].iloc[0])


def compute_matched_cashflow_benchmark(price_df: pd.DataFrame, trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a DataFrame [trade_date, benchmark_units_held, benchmark_market_value]
    covering the same date range as trades_df's execution dates onward.
    """
    if trades_df.empty:
        return pd.DataFrame(columns=["trade_date", "benchmark_units_held", "benchmark_market_value"])

    price_df = price_df.sort_values("trade_date").reset_index(drop=True)
    start_date = trades_df["execution_date"].min()
    daily = price_df[price_df["trade_date"] >= start_date].reset_index(drop=True)

    trades_by_date = trades_df.groupby("execution_date")
    units_held = 0.0
    rows = []
    for _, price_row in daily.iterrows():
        trade_date = price_row["trade_date"]
        if trade_date in trades_by_date.groups:
            for _, t in trades_by_date.get_group(trade_date).iterrows():
                exec_price = float(t["execution_open_price"])
                amount = float(t["trade_amount_inr"])
                if t["signal_type"] == config.SIGNAL_BUY:
                    units_held += amount / exec_price
                else:
                    units_to_sell = min(amount / exec_price, units_held)
                    units_held -= units_to_sell
        rows.append(
            {
                "trade_date": trade_date,
                "benchmark_units_held": units_held,
                "benchmark_market_value": units_held * float(price_row["close_price"]),
            }
        )
    return pd.DataFrame(rows)


def compute_lump_sum_benchmark(price_df: pd.DataFrame, trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Invests the strategy's peak net capital deployed as a single lump sum in
    NIFTY at the first execution date's open price, then marks it to market
    daily. Net capital deployed is recomputed from trades to keep this
    reproducible from data alone.
    """
    first = _first_execution_price(trades_df, price_df)
    if first is None:
        return pd.DataFrame(columns=["trade_date", "benchmark_units_held", "benchmark_market_value"])
    first_date, first_open_price = first

    net_capital = float(trades_df.loc[trades_df["signal_type"] == config.SIGNAL_BUY, "trade_amount_inr"].sum())
    if net_capital <= 0:
        return pd.DataFrame(columns=["trade_date", "benchmark_units_held", "benchmark_market_value"])

    units_held = net_capital / first_open_price
    price_df = price_df.sort_values("trade_date").reset_index(drop=True)
    daily = price_df[price_df["trade_date"] >= first_date].reset_index(drop=True)

    rows = [
        {
            "trade_date": row["trade_date"],
            "benchmark_units_held": units_held,
            "benchmark_market_value": units_held * float(row["close_price"]),
        }
        for _, row in daily.iterrows()
    ]
    return pd.DataFrame(rows)


def compute_benchmark(price_df: pd.DataFrame, trades_df: pd.DataFrame, method: str) -> pd.DataFrame:
    if method == config.BENCHMARK_MATCHED_CASHFLOW:
        return compute_matched_cashflow_benchmark(price_df, trades_df)
    if method == config.BENCHMARK_LUMP_SUM:
        return compute_lump_sum_benchmark(price_df, trades_df)
    raise ValueError(f"Unknown benchmark method: {method}")
