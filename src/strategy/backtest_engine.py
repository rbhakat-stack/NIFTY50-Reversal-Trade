"""
Top-level backtest orchestration. Ties together signal_engine ->
portfolio_engine -> benchmark_engine, computes summary metrics, and
optionally persists everything to Supabase.

This is the single entry point the "Run Backtest" button in Streamlit
should call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src import config
from src.config import StrategyConfig
from src.strategy import benchmark_engine, portfolio_engine, signal_engine
from src.utils.metrics import (
    absolute_return,
    average_holding_period,
    cagr,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    win_loss_ratio,
)


@dataclass
class BacktestResult:
    signals_df: pd.DataFrame
    trades_df: pd.DataFrame
    daily_state_df: pd.DataFrame
    metrics: dict = field(default_factory=dict)


def run_backtest(price_df: pd.DataFrame, strategy_config: StrategyConfig) -> BacktestResult:
    """
    Full walk-forward backtest. `price_df` must contain the entire available
    history (from training_start_date onward); slicing for the no-look-ahead
    rule happens inside signal_engine.generate_signals.
    """
    price_df = price_df.sort_values("trade_date").reset_index(drop=True)

    signals_df = signal_engine.generate_signals(price_df, strategy_config)
    if signals_df.empty:
        return BacktestResult(signals_df=signals_df, trades_df=pd.DataFrame(), daily_state_df=pd.DataFrame(), metrics={})

    execution_outcome = portfolio_engine.execute_signals(signals_df, price_df, strategy_config)
    trades_df = pd.DataFrame(execution_outcome.trades)

    signals_df = signals_df.copy()
    signals_df["execution_status"] = signals_df["signal_date"].map(execution_outcome.signal_execution_status)

    daily_state_df = portfolio_engine.build_daily_portfolio_state(price_df, trades_df, signals_df)

    benchmark_df = benchmark_engine.compute_benchmark(price_df, trades_df, strategy_config.benchmark_method)
    if not benchmark_df.empty and not daily_state_df.empty:
        daily_state_df = daily_state_df.merge(benchmark_df, on="trade_date", how="left")
        daily_state_df["benchmark_market_value"] = daily_state_df["benchmark_market_value"].ffill().fillna(0.0)
    else:
        daily_state_df["benchmark_market_value"] = 0.0

    daily_state_df = _attach_return_and_drawdown_columns(daily_state_df, strategy_config)

    metrics = _compute_summary_metrics(signals_df, trades_df, daily_state_df, strategy_config)

    return BacktestResult(
        signals_df=signals_df,
        trades_df=trades_df,
        daily_state_df=daily_state_df,
        metrics=metrics,
    )


def _attach_return_and_drawdown_columns(daily_state_df: pd.DataFrame, strategy_config: StrategyConfig) -> pd.DataFrame:
    if daily_state_df.empty:
        return daily_state_df

    df = daily_state_df.copy()
    net_capital = df["net_capital_deployed"].replace(0, np.nan)
    df["strategy_return_pct"] = (df["total_pnl"] / net_capital).fillna(0.0)

    benchmark_start_value = df["benchmark_market_value"].replace(0, np.nan).bfill().iloc[0] if not df.empty else np.nan
    if pd.notna(benchmark_start_value) and benchmark_start_value > 0:
        df["benchmark_return_pct"] = (df["benchmark_market_value"] - benchmark_start_value) / benchmark_start_value
    else:
        df["benchmark_return_pct"] = 0.0

    df["alpha_pct"] = df["strategy_return_pct"] - df["benchmark_return_pct"]

    _, drawdown_series = max_drawdown(df["portfolio_market_value"])
    df["drawdown_pct"] = drawdown_series.values if len(drawdown_series) == len(df) else 0.0

    return df


def _compute_summary_metrics(
    signals_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    daily_state_df: pd.DataFrame,
    strategy_config: StrategyConfig,
) -> dict:
    metrics: dict = {}

    num_buy = int((signals_df["signal_type"] == config.SIGNAL_BUY).sum())
    num_sell = int((signals_df["signal_type"] == config.SIGNAL_SELL).sum())
    metrics["number_of_buy_signals"] = num_buy
    metrics["number_of_sell_signals"] = num_sell
    metrics["number_of_trades"] = int(len(trades_df))

    if daily_state_df.empty:
        return metrics

    first_row = daily_state_df.iloc[0]
    last_row = daily_state_df.iloc[-1]
    num_years = max((pd.Timestamp(last_row["trade_date"]) - pd.Timestamp(first_row["trade_date"])).days / 365.25, 1e-6)

    net_capital_deployed = float(last_row["net_capital_deployed"])
    total_capital_deployed = float(last_row["cumulative_buy_amount"])
    final_portfolio_value = float(last_row["portfolio_market_value"])
    # Return-on-capital is measured against total capital ever committed (cumulative
    # buys), not net capital deployed (buys - sells): net capital can drop to zero or
    # negative once a profitable strategy has sold back more than it bought, which
    # would otherwise make begin_value <= 0 and silently zero out the return.
    strategy_end_value = total_capital_deployed + float(last_row["total_pnl"])

    metrics["final_portfolio_value"] = final_portfolio_value
    metrics["net_capital_deployed"] = net_capital_deployed
    metrics["total_capital_deployed"] = total_capital_deployed
    metrics["total_pnl"] = float(last_row["total_pnl"])
    metrics["total_return_pct"] = absolute_return(total_capital_deployed, strategy_end_value)
    metrics["strategy_cagr"] = cagr(total_capital_deployed, strategy_end_value, num_years)

    benchmark_start_value = daily_state_df["benchmark_market_value"].replace(0, np.nan).bfill().iloc[0]
    benchmark_end_value = float(last_row["benchmark_market_value"])
    if pd.notna(benchmark_start_value) and benchmark_start_value > 0:
        metrics["benchmark_cagr"] = cagr(benchmark_start_value, benchmark_end_value, num_years)
        metrics["benchmark_absolute_return_pct"] = absolute_return(benchmark_start_value, benchmark_end_value)
    else:
        metrics["benchmark_cagr"] = 0.0
        metrics["benchmark_absolute_return_pct"] = 0.0

    metrics["alpha_vs_benchmark_cagr"] = metrics["strategy_cagr"] - metrics["benchmark_cagr"]

    max_dd, _ = max_drawdown(daily_state_df["portfolio_market_value"])
    metrics["max_drawdown_pct"] = max_dd

    daily_strategy_returns = (
        daily_state_df["portfolio_market_value"].pct_change().replace([np.inf, -np.inf], 0.0).fillna(0.0)
    )
    metrics["sharpe_ratio"] = sharpe_ratio(daily_strategy_returns, strategy_config.risk_free_rate)
    metrics["sortino_ratio"] = sortino_ratio(daily_strategy_returns, strategy_config.risk_free_rate)

    if not trades_df.empty:
        sell_trades = trades_df[trades_df["signal_type"] == config.SIGNAL_SELL]
        if not sell_trades.empty:
            metrics["win_loss"] = win_loss_ratio(sell_trades["realized_pnl_impact"])
        else:
            metrics["win_loss"] = win_loss_ratio(pd.Series(dtype=float))

        buy_dates = trades_df.loc[trades_df["signal_type"] == config.SIGNAL_BUY, "execution_date"].tolist()
        sell_dates = trades_df.loc[trades_df["signal_type"] == config.SIGNAL_SELL, "execution_date"].tolist()
        metrics["average_holding_period_days"] = average_holding_period(buy_dates, sell_dates)
    else:
        metrics["win_loss"] = win_loss_ratio(pd.Series(dtype=float))
        metrics["average_holding_period_days"] = 0.0

    metrics["current_signal"] = signals_df.iloc[-1]["signal_type"]
    metrics["current_deviation_pct"] = float(signals_df.iloc[-1]["deviation_pct"])
    metrics["current_units_held"] = float(last_row["total_units_held"])

    return metrics
