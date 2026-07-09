"""
Portfolio accounting: turns a stream of BUY/SELL/HOLD signals into executed
trades (next trading day open) and a day-by-day portfolio state.

Execution rules enforced here (see spec section 19 / 26):
  - Signal generated on close of day t -> executed on open of day t+1.
  - If day t+1 has no data, the signal is marked PENDING (not silently
    dropped).
  - SELL never exceeds current holdings; no short-selling.
  - BUY/SELL amounts are configurable (default INR 10,000).
  - Transaction cost and slippage are applied consistently to every trade.
  - Optional cooldown / max-capital / max-units / no-repeat-direction
    controls can suppress a trade (execution_status = NOT_REQUIRED).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src import config
from src.config import StrategyConfig
from src.utils.date_utils import get_next_trading_day
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class PortfolioState:
    units_held: float = 0.0
    avg_buy_price: float = 0.0
    cumulative_buy_amount: float = 0.0
    cumulative_sell_amount: float = 0.0
    realized_pnl: float = 0.0
    last_trade_date: date | None = None
    last_signal_direction: str | None = None


@dataclass
class ExecutionOutcome:
    trades: list[dict] = field(default_factory=list)
    signal_execution_status: dict = field(default_factory=dict)  # signal_date -> status
    signal_execution_date: dict = field(default_factory=dict)  # signal_date -> execution_date
    final_state: PortfolioState = field(default_factory=PortfolioState)


def _within_cooldown(execution_date: date, last_trade_date: date | None, cooldown_days: int) -> bool:
    if cooldown_days <= 0 or last_trade_date is None:
        return False
    return (execution_date - last_trade_date).days < cooldown_days


def execute_signals(
    signals_df: pd.DataFrame,
    price_df: pd.DataFrame,
    strategy_config: StrategyConfig,
) -> ExecutionOutcome:
    price_df = price_df.sort_values("trade_date").reset_index(drop=True)
    price_by_date = price_df.set_index("trade_date")
    available_dates = price_df["trade_date"]

    state = PortfolioState()
    outcome = ExecutionOutcome()

    for _, sig in signals_df.sort_values("signal_date").iterrows():
        signal_date = sig["signal_date"]
        signal_type = sig["signal_type"]

        if signal_type == config.SIGNAL_HOLD:
            outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
            continue

        execution_date = get_next_trading_day(signal_date, available_dates)
        if execution_date is None:
            outcome.signal_execution_status[signal_date] = config.EXEC_PENDING
            logger.info("Signal %s on %s is PENDING: no next trading day available yet.", signal_type, signal_date)
            continue

        if execution_date not in price_by_date.index or pd.isna(price_by_date.loc[execution_date, "open_price"]):
            outcome.signal_execution_status[signal_date] = config.EXEC_FAILED
            logger.warning("Signal %s on %s FAILED: no open price for %s.", signal_type, signal_date, execution_date)
            continue

        if _within_cooldown(execution_date, state.last_trade_date, strategy_config.cooldown_days):
            outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
            continue

        if (
            strategy_config.disable_repeated_same_direction_signals
            and state.last_signal_direction == signal_type
        ):
            outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
            continue

        execution_open_price = float(price_by_date.loc[execution_date, "open_price"])
        trade_amount = strategy_config.trade_amount_inr

        if signal_type == config.SIGNAL_BUY:
            if strategy_config.max_capital_deployed_inr is not None:
                remaining_capacity = strategy_config.max_capital_deployed_inr - state.cumulative_buy_amount + state.cumulative_sell_amount
                if remaining_capacity <= 0:
                    outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
                    continue
                trade_amount = min(trade_amount, remaining_capacity)

            exec_price = execution_open_price * (1 + strategy_config.slippage_pct)
            units_bought = trade_amount / exec_price

            if strategy_config.max_units is not None and state.units_held + units_bought > strategy_config.max_units:
                units_bought = max(strategy_config.max_units - state.units_held, 0.0)
                trade_amount = units_bought * exec_price
                if units_bought <= 0:
                    outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
                    continue

            transaction_cost = trade_amount * strategy_config.transaction_cost_pct
            slippage_cost = units_bought * (exec_price - execution_open_price)

            new_units_held = state.units_held + units_bought
            state.avg_buy_price = (
                (state.avg_buy_price * state.units_held + exec_price * units_bought) / new_units_held
                if new_units_held > 0
                else 0.0
            )
            state.units_held = new_units_held
            state.cumulative_buy_amount += trade_amount
            cash_flow = -(trade_amount + transaction_cost)
            net_units_change = units_bought
            realized_pnl_delta = 0.0

        else:  # SELL
            if state.units_held <= 0:
                outcome.signal_execution_status[signal_date] = config.EXEC_NOT_REQUIRED
                continue

            exec_price = execution_open_price * (1 - strategy_config.slippage_pct)
            desired_units = trade_amount / exec_price
            units_sold = min(desired_units, state.units_held)  # never sell more than held; no short-selling
            trade_amount = units_sold * exec_price

            transaction_cost = trade_amount * strategy_config.transaction_cost_pct
            slippage_cost = units_sold * (execution_open_price - exec_price)
            realized_pnl_delta = units_sold * (exec_price - state.avg_buy_price) - transaction_cost
            state.realized_pnl += realized_pnl_delta

            state.units_held -= units_sold
            state.cumulative_sell_amount += trade_amount
            cash_flow = trade_amount - transaction_cost
            net_units_change = -units_sold

        outcome.trades.append(
            {
                "signal_date": signal_date,
                "execution_date": execution_date,
                "signal_type": signal_type,
                "signal_close_price": float(sig["actual_close"]),
                "predicted_trend_price": float(sig["predicted_trend_price"]),
                "deviation_pct": float(sig["deviation_pct"]),
                "execution_open_price": execution_open_price,
                "trade_amount_inr": float(trade_amount),
                "units_traded": float(abs(net_units_change)),
                "transaction_cost": float(transaction_cost),
                "slippage_cost": float(slippage_cost),
                "net_units_change": float(net_units_change),
                "portfolio_units_after_trade": float(state.units_held),
                "cash_flow": float(cash_flow),
                # In-memory only for win/loss metrics; not a strategy_trades column.
                "realized_pnl_impact": float(realized_pnl_delta),
            }
        )
        outcome.signal_execution_status[signal_date] = config.EXEC_EXECUTED
        outcome.signal_execution_date[signal_date] = execution_date
        state.last_trade_date = execution_date
        state.last_signal_direction = signal_type

    outcome.final_state = state
    return outcome


def build_daily_portfolio_state(
    price_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    signals_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    One row per trading day from the first signal date onward, tracking
    running units held, market value, cumulative capital, and P&L. Merges
    in the same-day signal (if any); a trade that executes on day t is
    reflected in that day's units_held.
    """
    price_df = price_df.sort_values("trade_date").reset_index(drop=True)
    if signals_df.empty:
        return pd.DataFrame()

    start_date = signals_df["signal_date"].min()
    daily = price_df[price_df["trade_date"] >= start_date].reset_index(drop=True).copy()

    signals_indexed = signals_df.set_index("signal_date")
    trades_by_exec_date = (
        trades_df.groupby("execution_date").agg(
            units_delta=("net_units_change", "sum"),
            buy_amount=("trade_amount_inr", lambda s: s[trades_df.loc[s.index, "signal_type"] == config.SIGNAL_BUY].sum()),
            sell_amount=("trade_amount_inr", lambda s: s[trades_df.loc[s.index, "signal_type"] == config.SIGNAL_SELL].sum()),
        )
        if not trades_df.empty
        else pd.DataFrame(columns=["units_delta", "buy_amount", "sell_amount"])
    )

    # Replay trades once to get realized P&L and average buy price as of each
    # execution date (both cumulative, carried forward to non-trading days).
    realized_pnl_by_date: dict = {}
    avg_buy_price_by_date: dict = {}
    if not trades_df.empty:
        running_realized = 0.0
        avg_buy_price = 0.0
        units_running = 0.0
        for _, t in trades_df.sort_values("execution_date").iterrows():
            if t["signal_type"] == config.SIGNAL_BUY:
                new_units = units_running + t["units_traded"]
                avg_buy_price = (
                    (avg_buy_price * units_running + t["execution_open_price"] * t["units_traded"]) / new_units
                    if new_units > 0
                    else 0.0
                )
                units_running = new_units
            else:
                running_realized += t["units_traded"] * (t["execution_open_price"] - avg_buy_price) - (t["transaction_cost"] or 0.0)
                units_running -= t["units_traded"]
            realized_pnl_by_date[t["execution_date"]] = running_realized
            avg_buy_price_by_date[t["execution_date"]] = avg_buy_price

    rows = []
    units_held = 0.0
    cumulative_buy = 0.0
    cumulative_sell = 0.0
    realized_pnl = 0.0
    avg_buy_price = 0.0

    for _, price_row in daily.iterrows():
        trade_date = price_row["trade_date"]
        close_price = float(price_row["close_price"])

        if trade_date in trades_by_exec_date.index:
            units_held += float(trades_by_exec_date.loc[trade_date, "units_delta"])
            cumulative_buy += float(trades_by_exec_date.loc[trade_date, "buy_amount"] or 0.0)
            cumulative_sell += float(trades_by_exec_date.loc[trade_date, "sell_amount"] or 0.0)
        if trade_date in realized_pnl_by_date:
            realized_pnl = realized_pnl_by_date[trade_date]
        if trade_date in avg_buy_price_by_date:
            avg_buy_price = avg_buy_price_by_date[trade_date]

        market_value = units_held * close_price
        unrealized_pnl = units_held * (close_price - avg_buy_price) if units_held > 0 else 0.0
        net_capital_deployed = cumulative_buy - cumulative_sell
        total_pnl = realized_pnl + unrealized_pnl

        signal_row = signals_indexed.loc[trade_date] if trade_date in signals_indexed.index else None

        rows.append(
            {
                "trade_date": trade_date,
                "actual_close": close_price,
                "predicted_trend_price": float(signal_row["predicted_trend_price"]) if signal_row is not None else None,
                "deviation_pct": float(signal_row["deviation_pct"]) if signal_row is not None else None,
                "signal_type": signal_row["signal_type"] if signal_row is not None else None,
                "total_units_held": units_held,
                "portfolio_market_value": market_value,
                "cumulative_buy_amount": cumulative_buy,
                "cumulative_sell_amount": cumulative_sell,
                "net_capital_deployed": net_capital_deployed,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": total_pnl,
            }
        )

    return pd.DataFrame(rows)
