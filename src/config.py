"""
Central configuration for the NIFTY Trend Alpha research product.

All values here are defaults for a research/backtesting tool. Nothing in
this module constitutes investment advice.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str | None = None) -> str | None:
    """Read a secret from environment first, then Streamlit secrets if available."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Supabase / environment configuration
# ---------------------------------------------------------------------------
SUPABASE_URL: str | None = _get_secret("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str | None = _get_secret("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_ANON_KEY: str | None = _get_secret("SUPABASE_ANON_KEY")

EMAIL_SENDER: str | None = _get_secret("EMAIL_SENDER")
EMAIL_PASSWORD: str | None = _get_secret("EMAIL_PASSWORD")
ALERT_RECIPIENT_EMAIL: str | None = _get_secret("ALERT_RECIPIENT_EMAIL")
SMTP_HOST: str = _get_secret("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com"
SMTP_PORT: int = int(_get_secret("SMTP_PORT", "587") or "587")
ALERT_WEBHOOK_URL: str | None = _get_secret("ALERT_WEBHOOK_URL")

# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------
TABLE_PRICES = "nifty_daily_prices"
TABLE_SIGNALS = "strategy_signals"
TABLE_TRADES = "strategy_trades"
TABLE_STATE = "daily_strategy_state"
TABLE_MODEL_RUNS = "model_runs"
TABLE_ALERTS = "alert_events"

# Canonical strategy_trades columns; used to strip in-memory-only fields
# (e.g. realized_pnl_impact, used for metrics) before persisting to Supabase.
STRATEGY_TRADES_COLUMNS = [
    "signal_date",
    "execution_date",
    "signal_type",
    "signal_close_price",
    "predicted_trend_price",
    "deviation_pct",
    "execution_open_price",
    "trade_amount_inr",
    "units_traded",
    "transaction_cost",
    "slippage_cost",
    "net_units_change",
    "portfolio_units_after_trade",
    "cash_flow",
]

# ---------------------------------------------------------------------------
# Market / data defaults
# ---------------------------------------------------------------------------
YFINANCE_SYMBOL = "^NSEI"
HISTORICAL_START_DATE = date(2000, 4, 1)
INITIAL_TRAINING_END_DATE = date(2020, 3, 31)
SIGNAL_START_DATE = date(2020, 4, 1)

DATA_SOURCE_YFINANCE = "YFINANCE"
DATA_SOURCE_NSE = "NSE"
DATA_SOURCE_CSV = "CSV_UPLOAD"

# ---------------------------------------------------------------------------
# Strategy defaults (all configurable via UI / StrategyConfig overrides)
# ---------------------------------------------------------------------------
MODEL_TYPE_LOG_LINEAR = "log_linear"
MODEL_TYPE_POLY_LOG = "polynomial_log"
MODEL_TYPE_ROLLING_EXP = "rolling_exponential"

DEFAULT_MODEL_TYPE = MODEL_TYPE_LOG_LINEAR
DEFAULT_BUY_THRESHOLD = -0.10
DEFAULT_SELL_THRESHOLD = 0.10
DEFAULT_TRADE_AMOUNT_INR = 10_000.0
DEFAULT_TRANSACTION_COST_PCT = 0.0005  # 0.05%
DEFAULT_SLIPPAGE_PCT = 0.0
DEFAULT_RISK_FREE_RATE = 0.06  # annualized, for Sharpe/Sortino

SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"

EXEC_PENDING = "PENDING"
EXEC_EXECUTED = "EXECUTED"
EXEC_NOT_REQUIRED = "NOT_REQUIRED"
EXEC_FAILED = "FAILED"

BENCHMARK_MATCHED_CASHFLOW = "matched_cashflow"
BENCHMARK_LUMP_SUM = "lump_sum"

TRADING_DAYS_PER_YEAR = 252


@dataclass
class StrategyConfig:
    """Configurable parameters for backtest / live signal generation."""

    training_start_date: date = HISTORICAL_START_DATE
    initial_training_end_date: date = INITIAL_TRAINING_END_DATE
    signal_start_date: date = SIGNAL_START_DATE
    backtest_end_date: date | None = None

    model_type: str = DEFAULT_MODEL_TYPE
    buy_threshold: float = DEFAULT_BUY_THRESHOLD
    sell_threshold: float = DEFAULT_SELL_THRESHOLD
    trade_amount_inr: float = DEFAULT_TRADE_AMOUNT_INR
    transaction_cost_pct: float = DEFAULT_TRANSACTION_COST_PCT
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE
    benchmark_method: str = BENCHMARK_MATCHED_CASHFLOW

    # Optional trade controls
    cooldown_days: int = 0
    max_capital_deployed_inr: float | None = None
    max_units: float | None = None
    disable_repeated_same_direction_signals: bool = False

    # Model-specific extra params
    polynomial_degree: int = 2
    rolling_window_days: int = 252

    extra: dict = field(default_factory=dict)
