import pandas as pd

from src import config
from src.strategy.benchmark_engine import compute_benchmark, compute_lump_sum_benchmark, compute_matched_cashflow_benchmark


def _price_df():
    dates = pd.bdate_range("2020-04-01", periods=6)
    return pd.DataFrame(
        {
            "trade_date": [d.date() for d in dates],
            "open_price": [100, 110, 120, 130, 140, 150],
            "close_price": [101, 111, 121, 131, 141, 151],
        }
    )


def _trades_df():
    price_df = _price_df()
    dates = price_df["trade_date"].tolist()
    return pd.DataFrame(
        [
            {
                "signal_date": dates[0],
                "execution_date": dates[1],
                "signal_type": config.SIGNAL_BUY,
                "execution_open_price": 110.0,
                "trade_amount_inr": 10_000.0,
            },
            {
                "signal_date": dates[2],
                "execution_date": dates[3],
                "signal_type": config.SIGNAL_BUY,
                "execution_open_price": 130.0,
                "trade_amount_inr": 10_000.0,
            },
        ]
    )


def test_matched_cashflow_benchmark_buys_same_amount():
    price_df = _price_df()
    trades_df = _trades_df()
    benchmark_df = compute_matched_cashflow_benchmark(price_df, trades_df)

    assert not benchmark_df.empty
    first_exec_date = trades_df["execution_date"].iloc[0]
    row = benchmark_df[benchmark_df["trade_date"] == first_exec_date].iloc[0]
    expected_units = 10_000.0 / 110.0
    assert abs(row["benchmark_units_held"] - expected_units) < 1e-9


def test_matched_cashflow_benchmark_sell_never_negative():
    price_df = _price_df()
    trades_df = _trades_df().copy()
    trades_df.loc[1, "signal_type"] = config.SIGNAL_SELL
    trades_df.loc[1, "trade_amount_inr"] = 1_000_000.0  # oversized sell

    benchmark_df = compute_matched_cashflow_benchmark(price_df, trades_df)
    assert (benchmark_df["benchmark_units_held"] >= 0).all()


def test_lump_sum_benchmark_invests_total_buy_capital_at_first_execution_price():
    price_df = _price_df()
    trades_df = _trades_df()
    benchmark_df = compute_lump_sum_benchmark(price_df, trades_df)

    total_buy = trades_df["trade_amount_inr"].sum()
    first_price = trades_df["execution_open_price"].iloc[0]
    expected_units = total_buy / first_price

    assert abs(benchmark_df["benchmark_units_held"].iloc[0] - expected_units) < 1e-9
    # Units held should be constant (lump sum, no further trading)
    assert benchmark_df["benchmark_units_held"].nunique() == 1


def test_compute_benchmark_dispatches_by_method():
    price_df = _price_df()
    trades_df = _trades_df()

    matched = compute_benchmark(price_df, trades_df, config.BENCHMARK_MATCHED_CASHFLOW)
    lump = compute_benchmark(price_df, trades_df, config.BENCHMARK_LUMP_SUM)

    assert not matched.equals(lump)
