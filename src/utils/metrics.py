"""Performance metric calculations used by the backtest and benchmark engines."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR


def cagr(begin_value: float, end_value: float, num_years: float) -> float:
    """Compound annual growth rate. Returns 0 if inputs are degenerate."""
    if begin_value <= 0 or end_value <= 0 or num_years <= 0:
        return 0.0
    return (end_value / begin_value) ** (1.0 / num_years) - 1.0


def absolute_return(begin_value: float, end_value: float) -> float:
    if begin_value <= 0:
        return 0.0
    return (end_value - begin_value) / begin_value


def daily_returns(values: pd.Series) -> pd.Series:
    return values.pct_change().fillna(0.0)


def max_drawdown(values: pd.Series) -> tuple[float, pd.Series]:
    """
    Returns (max_drawdown_pct, drawdown_series). Drawdown is expressed as a
    negative fraction (e.g. -0.23 for a 23% drawdown) at every point in time.
    """
    if values.empty:
        return 0.0, pd.Series(dtype=float)
    running_max = values.cummax().replace(0, np.nan)
    drawdown = (values - running_max) / running_max
    drawdown = drawdown.fillna(0.0)
    return float(drawdown.min()), drawdown


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    if returns.empty or returns.std(ddof=0) == 0:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    excess = returns - rf_per_period
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=0))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    if returns.empty:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    excess = returns - rf_per_period
    downside = excess[excess < 0]
    downside_std = downside.std(ddof=0)
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / downside_std)


def win_loss_ratio(trade_pnls: pd.Series) -> dict:
    """trade_pnls: realized P&L per closed round-trip or per sell trade."""
    wins = trade_pnls[trade_pnls > 0]
    losses = trade_pnls[trade_pnls < 0]
    total = len(trade_pnls)
    return {
        "num_wins": int(len(wins)),
        "num_losses": int(len(losses)),
        "win_rate_pct": float(len(wins) / total) if total else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
    }


def average_holding_period(buy_dates: list, sell_dates: list) -> float:
    """
    Rough average holding period in days using FIFO pairing of buy and sell
    execution dates. Both lists should already be sorted ascending.
    """
    if not buy_dates or not sell_dates:
        return 0.0
    buys = sorted(pd.Timestamp(d) for d in buy_dates)
    sells = sorted(pd.Timestamp(d) for d in sell_dates)
    holding_days = []
    buy_idx = 0
    for sell_date in sells:
        if buy_idx >= len(buys):
            break
        buy_date = buys[buy_idx]
        holding_days.append((sell_date - buy_date).days)
        buy_idx += 1
    if not holding_days:
        return 0.0
    return float(np.mean(holding_days))


def alpha_pct(strategy_return: float, benchmark_return: float) -> float:
    return strategy_return - benchmark_return
