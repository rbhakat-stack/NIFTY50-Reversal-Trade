import pandas as pd

from src import config
from src.config import StrategyConfig
from src.strategy.signal_engine import classify_signal, generate_signal_for_date, generate_signals


def test_classify_signal_buy():
    assert classify_signal(-0.15, config.DEFAULT_BUY_THRESHOLD, config.DEFAULT_SELL_THRESHOLD) == config.SIGNAL_BUY


def test_classify_signal_sell():
    assert classify_signal(0.15, config.DEFAULT_BUY_THRESHOLD, config.DEFAULT_SELL_THRESHOLD) == config.SIGNAL_SELL


def test_classify_signal_hold():
    assert classify_signal(0.02, config.DEFAULT_BUY_THRESHOLD, config.DEFAULT_SELL_THRESHOLD) == config.SIGNAL_HOLD


def test_classify_signal_boundary_is_buy():
    assert classify_signal(-0.10, -0.10, 0.10) == config.SIGNAL_BUY


def test_classify_signal_boundary_is_sell():
    assert classify_signal(0.10, -0.10, 0.10) == config.SIGNAL_SELL


def test_generate_signal_for_date_matches_manual_deviation(synthetic_price_history):
    strategy_config = StrategyConfig()
    history = synthetic_price_history.iloc[:600].reset_index(drop=True)
    signal, fit_result = generate_signal_for_date(history, strategy_config)

    expected_deviation = (fit_result.latest_actual_close - fit_result.latest_predicted_price) / fit_result.latest_predicted_price
    assert abs(signal.deviation_pct - expected_deviation) < 1e-9
    assert signal.signal_date == history["trade_date"].iloc[-1]


def test_generate_signals_no_look_ahead(synthetic_price_history):
    """The signal for a given date must be identical whether computed from
    the full history or from a history truncated right after that date."""
    strategy_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[300],
    )

    full_signals = generate_signals(synthetic_price_history, strategy_config)

    cutoff_date = synthetic_price_history["trade_date"].iloc[600]
    truncated_history = synthetic_price_history[synthetic_price_history["trade_date"] <= cutoff_date].reset_index(drop=True)
    truncated_signals = generate_signals(truncated_history, strategy_config)

    full_row = full_signals[full_signals["signal_date"] == cutoff_date].iloc[0]
    truncated_row = truncated_signals[truncated_signals["signal_date"] == cutoff_date].iloc[0]

    assert full_row["predicted_trend_price"] == truncated_row["predicted_trend_price"]
    assert full_row["deviation_pct"] == truncated_row["deviation_pct"]
    assert full_row["signal_type"] == truncated_row["signal_type"]


def test_generate_signals_covers_expected_date_range(synthetic_price_history):
    strategy_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[300],
    )
    signals_df = generate_signals(synthetic_price_history, strategy_config)
    expected_dates = set(synthetic_price_history["trade_date"].iloc[300:])
    assert set(signals_df["signal_date"]) == expected_dates
