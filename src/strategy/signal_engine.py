"""
Daily signal generation.

CRITICAL no-look-ahead rule: for every signal date `t`, the trend model is
refit using ONLY rows with trade_date <= t (i.e. `price_df[price_df.trade_date
<= t]`). The model is never given data from t+1 onward when scoring day t.
Signals are generated from the close of day t; execution happens on the
open of the next trading day (handled in portfolio_engine), never on day t
itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src import config
from src.config import StrategyConfig
from src.models.trend_model import TrendFitResult, get_model
from src.utils.date_utils import add_trading_day_index
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class DailySignal:
    signal_date: date
    actual_close: float
    predicted_trend_price: float
    deviation_pct: float
    signal_type: str
    model_type: str
    buy_threshold: float
    sell_threshold: float


def classify_signal(deviation_pct: float, buy_threshold: float, sell_threshold: float) -> str:
    if deviation_pct <= buy_threshold:
        return config.SIGNAL_BUY
    if deviation_pct >= sell_threshold:
        return config.SIGNAL_SELL
    return config.SIGNAL_HOLD


def generate_signal_for_date(
    price_history_up_to_t: pd.DataFrame,
    strategy_config: StrategyConfig,
) -> tuple[DailySignal, TrendFitResult]:
    """
    price_history_up_to_t must already be filtered to trade_date <= t and
    sorted ascending. Refits the model on this slice only, then scores the
    last row (day t).
    """
    model = get_model(
        strategy_config.model_type,
        degree=strategy_config.polynomial_degree,
        window_days=strategy_config.rolling_window_days,
    )
    fit_result = model.fit(price_history_up_to_t)

    signal_type = classify_signal(
        fit_result.latest_deviation_pct,
        strategy_config.buy_threshold,
        strategy_config.sell_threshold,
    )

    signal = DailySignal(
        signal_date=price_history_up_to_t["trade_date"].iloc[-1],
        actual_close=fit_result.latest_actual_close,
        predicted_trend_price=fit_result.latest_predicted_price,
        deviation_pct=fit_result.latest_deviation_pct,
        signal_type=signal_type,
        model_type=strategy_config.model_type,
        buy_threshold=strategy_config.buy_threshold,
        sell_threshold=strategy_config.sell_threshold,
    )
    return signal, fit_result


def generate_signals(
    full_price_history: pd.DataFrame,
    strategy_config: StrategyConfig,
) -> pd.DataFrame:
    """
    Walk-forward signal generation from `strategy_config.signal_start_date`
    through the last available trade_date in `full_price_history`. On each
    iteration the model is refit from scratch using only data up to and
    including that day (no look-ahead). Returns a DataFrame of one row per
    signal date, matching the `strategy_signals` table schema (minus
    execution_status, which is set later by portfolio_engine).
    """
    df = full_price_history.sort_values("trade_date").reset_index(drop=True)
    df = df[df["trade_date"] >= strategy_config.training_start_date].reset_index(drop=True)

    if strategy_config.backtest_end_date:
        df = df[df["trade_date"] <= strategy_config.backtest_end_date].reset_index(drop=True)

    signal_dates = df.loc[df["trade_date"] >= strategy_config.signal_start_date, "trade_date"].tolist()

    rows = []
    for t in signal_dates:
        history_slice = df[df["trade_date"] <= t]
        try:
            signal, _fit = generate_signal_for_date(history_slice, strategy_config)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", t, exc)
            continue
        rows.append(
            {
                "signal_date": signal.signal_date,
                "actual_close": signal.actual_close,
                "predicted_trend_price": signal.predicted_trend_price,
                "deviation_pct": signal.deviation_pct,
                "signal_type": signal.signal_type,
                "model_type": signal.model_type,
                "buy_threshold": signal.buy_threshold,
                "sell_threshold": signal.sell_threshold,
            }
        )

    return pd.DataFrame(rows)
