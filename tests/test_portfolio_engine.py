import pandas as pd

from src import config
from src.config import StrategyConfig
from src.strategy.portfolio_engine import build_daily_portfolio_state, execute_signals


def _price_df():
    dates = pd.bdate_range("2020-04-01", periods=10)
    return pd.DataFrame(
        {
            "trade_date": [d.date() for d in dates],
            "open_price": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "close_price": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5],
        }
    )


def _signal_row(signal_date, signal_type, actual_close=100.0, predicted=110.0, deviation=-0.1):
    return {
        "signal_date": signal_date,
        "actual_close": actual_close,
        "predicted_trend_price": predicted,
        "deviation_pct": deviation,
        "signal_type": signal_type,
    }


def test_buy_executes_on_next_trading_day_open():
    price_df = _price_df()
    signal_date = price_df["trade_date"].iloc[0]
    signals_df = pd.DataFrame([_signal_row(signal_date, config.SIGNAL_BUY)])

    outcome = execute_signals(signals_df, price_df, StrategyConfig())

    assert len(outcome.trades) == 1
    trade = outcome.trades[0]
    assert trade["execution_date"] == price_df["trade_date"].iloc[1]
    assert trade["execution_open_price"] == price_df["open_price"].iloc[1]
    assert outcome.signal_execution_status[signal_date] == config.EXEC_EXECUTED


def test_buy_units_calculation_and_transaction_cost():
    price_df = _price_df()
    signal_date = price_df["trade_date"].iloc[0]
    signals_df = pd.DataFrame([_signal_row(signal_date, config.SIGNAL_BUY)])
    strategy_config = StrategyConfig(trade_amount_inr=10_000.0, transaction_cost_pct=0.0005, slippage_pct=0.0)

    outcome = execute_signals(signals_df, price_df, strategy_config)
    trade = outcome.trades[0]

    exec_price = price_df["open_price"].iloc[1]
    expected_units = 10_000.0 / exec_price
    assert abs(trade["units_traded"] - expected_units) < 1e-9
    assert abs(trade["transaction_cost"] - 10_000.0 * 0.0005) < 1e-9
    assert trade["cash_flow"] < -10_000.0  # trade amount + transaction cost


def test_sell_cannot_exceed_holdings():
    # Prices drop sharply between the buy execution and the sell execution, so a
    # fixed INR sell request would require more units than were actually bought.
    dates = pd.bdate_range("2020-04-01", periods=10)
    price_df = pd.DataFrame(
        {
            "trade_date": [d.date() for d in dates],
            "open_price": [100, 101, 20, 21, 22, 23, 24, 25, 26, 27],
            "close_price": [100.5, 101.5, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26.5, 27.5],
        }
    )
    d0, d1 = price_df["trade_date"].iloc[0], price_df["trade_date"].iloc[1]
    signals_df = pd.DataFrame(
        [
            _signal_row(d0, config.SIGNAL_BUY),
            _signal_row(d1, config.SIGNAL_SELL, deviation=0.15),
        ]
    )

    strategy_config = StrategyConfig(trade_amount_inr=10_000.0)
    outcome = execute_signals(signals_df, price_df, strategy_config)

    sell_trades = [t for t in outcome.trades if t["signal_type"] == config.SIGNAL_SELL]
    assert len(sell_trades) == 1
    assert sell_trades[0]["portfolio_units_after_trade"] >= 0
    assert sell_trades[0]["portfolio_units_after_trade"] == 0  # sold everything, no negative holdings


def test_sell_with_no_holdings_is_not_required():
    price_df = _price_df()
    signal_date = price_df["trade_date"].iloc[0]
    signals_df = pd.DataFrame([_signal_row(signal_date, config.SIGNAL_SELL, deviation=0.15)])

    outcome = execute_signals(signals_df, price_df, StrategyConfig())

    assert len(outcome.trades) == 0
    assert outcome.signal_execution_status[signal_date] == config.EXEC_NOT_REQUIRED


def test_signal_on_last_day_is_pending():
    price_df = _price_df()
    last_date = price_df["trade_date"].iloc[-1]
    signals_df = pd.DataFrame([_signal_row(last_date, config.SIGNAL_BUY)])

    outcome = execute_signals(signals_df, price_df, StrategyConfig())

    assert len(outcome.trades) == 0
    assert outcome.signal_execution_status[last_date] == config.EXEC_PENDING


def test_hold_signal_produces_no_trade():
    price_df = _price_df()
    signal_date = price_df["trade_date"].iloc[0]
    signals_df = pd.DataFrame([_signal_row(signal_date, config.SIGNAL_HOLD, deviation=0.0)])

    outcome = execute_signals(signals_df, price_df, StrategyConfig())

    assert len(outcome.trades) == 0
    assert outcome.signal_execution_status[signal_date] == config.EXEC_NOT_REQUIRED


def test_cooldown_suppresses_second_trade():
    price_df = _price_df()
    dates = price_df["trade_date"].tolist()
    signals_df = pd.DataFrame(
        [
            _signal_row(dates[0], config.SIGNAL_BUY),
            _signal_row(dates[1], config.SIGNAL_BUY),
        ]
    )
    strategy_config = StrategyConfig(cooldown_days=5)
    outcome = execute_signals(signals_df, price_df, strategy_config)

    assert len(outcome.trades) == 1
    assert outcome.signal_execution_status[dates[1]] == config.EXEC_NOT_REQUIRED


def test_disable_repeated_same_direction_signals():
    price_df = _price_df()
    dates = price_df["trade_date"].tolist()
    signals_df = pd.DataFrame(
        [
            _signal_row(dates[0], config.SIGNAL_BUY),
            _signal_row(dates[2], config.SIGNAL_BUY),
        ]
    )
    strategy_config = StrategyConfig(disable_repeated_same_direction_signals=True)
    outcome = execute_signals(signals_df, price_df, strategy_config)

    assert len(outcome.trades) == 1
    assert outcome.signal_execution_status[dates[2]] == config.EXEC_NOT_REQUIRED


def test_build_daily_portfolio_state_tracks_units_and_value():
    price_df = _price_df()
    d0 = price_df["trade_date"].iloc[0]
    signals_df = pd.DataFrame([_signal_row(d0, config.SIGNAL_BUY)])
    outcome = execute_signals(signals_df, price_df, StrategyConfig())
    trades_df = pd.DataFrame(outcome.trades)
    signals_df["execution_status"] = signals_df["signal_date"].map(outcome.signal_execution_status)

    daily_state = build_daily_portfolio_state(price_df, trades_df, signals_df)

    assert not daily_state.empty
    exec_date = trades_df["execution_date"].iloc[0]
    row_on_exec = daily_state[daily_state["trade_date"] == exec_date].iloc[0]
    assert row_on_exec["total_units_held"] > 0
    assert row_on_exec["portfolio_market_value"] > 0
