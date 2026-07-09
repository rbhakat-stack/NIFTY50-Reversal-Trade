from src import config
from src.config import StrategyConfig
from src.strategy.backtest_engine import run_backtest


def test_run_backtest_end_to_end_produces_expected_structure(synthetic_price_history):
    strategy_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[400],
    )

    result = run_backtest(synthetic_price_history, strategy_config)

    assert not result.signals_df.empty
    assert set(["signal_date", "actual_close", "predicted_trend_price", "deviation_pct", "signal_type"]).issubset(
        result.signals_df.columns
    )
    assert "final_portfolio_value" in result.metrics
    assert "strategy_cagr" in result.metrics
    assert "max_drawdown_pct" in result.metrics
    assert result.metrics["max_drawdown_pct"] <= 0


def test_run_backtest_reproducible(synthetic_price_history):
    strategy_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[400],
    )

    result_a = run_backtest(synthetic_price_history, strategy_config)
    result_b = run_backtest(synthetic_price_history, strategy_config)

    pd_assert = __import__("pandas").testing.assert_frame_equal
    pd_assert(result_a.signals_df.reset_index(drop=True), result_b.signals_df.reset_index(drop=True))
    assert result_a.metrics == result_b.metrics


def test_run_backtest_no_signals_before_signal_start_date(synthetic_price_history):
    signal_start = synthetic_price_history["trade_date"].iloc[400]
    strategy_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=signal_start,
    )
    result = run_backtest(synthetic_price_history, strategy_config)
    assert result.signals_df["signal_date"].min() == signal_start


def test_run_backtest_transaction_cost_reduces_trade_cash_flow(synthetic_price_history):
    base_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[400],
        transaction_cost_pct=0.0,
    )
    costly_config = StrategyConfig(
        training_start_date=synthetic_price_history["trade_date"].min(),
        signal_start_date=synthetic_price_history["trade_date"].iloc[400],
        transaction_cost_pct=0.01,
    )

    result_free = run_backtest(synthetic_price_history, base_config)
    result_costly = run_backtest(synthetic_price_history, costly_config)

    buys_free = result_free.trades_df[result_free.trades_df["signal_type"] == config.SIGNAL_BUY]
    buys_costly = result_costly.trades_df[result_costly.trades_df["signal_type"] == config.SIGNAL_BUY]

    if not buys_free.empty and not buys_costly.empty:
        assert buys_costly["transaction_cost"].sum() > buys_free["transaction_cost"].sum()
