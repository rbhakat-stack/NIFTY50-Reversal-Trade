"""Backtest Explorer: configure parameters and re-run the strategy."""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import config
from src.config import StrategyConfig
from src.data.data_repository import (
    fetch_price_history,
    insert_daily_state,
    insert_model_run,
    insert_signals,
    insert_trades,
)
from src.models.trend_model import get_model
from src.strategy.backtest_engine import run_backtest
from src.supabase_client import SupabaseConfigError
from src.ui.charts import deviation_chart, drawdown_chart, portfolio_performance_chart, signal_marker_chart, trend_chart
from src.ui.components import download_csv_button, render_backtest_summary_kpis

st.set_page_config(page_title="Backtest Explorer | NIFTY Trend Alpha", layout="wide")
st.title("Backtest Explorer")
st.caption("Configure strategy parameters and reproduce the backtest. Research tool — not financial advice.")

DEFAULTS = StrategyConfig()

with st.sidebar:
    st.header("Backtest Parameters")
    training_start_date = st.date_input("Training start date", value=DEFAULTS.training_start_date)
    initial_training_end_date = st.date_input("Initial training end date", value=DEFAULTS.initial_training_end_date)
    signal_start_date = st.date_input("Backtest (signal) start date", value=DEFAULTS.signal_start_date)
    backtest_end_date = st.date_input("Backtest end date (blank = latest)", value=date.today())

    model_type = st.selectbox(
        "Trend model type",
        [config.MODEL_TYPE_LOG_LINEAR, config.MODEL_TYPE_POLY_LOG, config.MODEL_TYPE_ROLLING_EXP],
        index=0,
    )
    polynomial_degree = st.slider("Polynomial degree (poly model only)", 2, 5, DEFAULTS.polynomial_degree)
    rolling_window_days = st.slider("Rolling window days (rolling model only)", 60, 756, DEFAULTS.rolling_window_days)

    buy_threshold = st.slider("Buy threshold (%)", -30, 0, int(DEFAULTS.buy_threshold * 100)) / 100
    sell_threshold = st.slider("Sell threshold (%)", 0, 30, int(DEFAULTS.sell_threshold * 100)) / 100
    trade_amount_inr = st.number_input("Trade amount (INR)", min_value=1000.0, value=DEFAULTS.trade_amount_inr, step=1000.0)
    transaction_cost_pct = st.number_input(
        "Transaction cost (%)", min_value=0.0, value=DEFAULTS.transaction_cost_pct * 100, step=0.01, format="%.3f"
    ) / 100
    slippage_pct = st.number_input(
        "Slippage (%)", min_value=0.0, value=DEFAULTS.slippage_pct * 100, step=0.01, format="%.3f"
    ) / 100
    risk_free_rate = st.number_input("Risk-free rate (annualized %)", min_value=0.0, value=DEFAULTS.risk_free_rate * 100, step=0.5) / 100
    benchmark_method = st.selectbox(
        "Benchmark method",
        [config.BENCHMARK_MATCHED_CASHFLOW, config.BENCHMARK_LUMP_SUM],
        format_func=lambda v: "Matched Cashflow" if v == config.BENCHMARK_MATCHED_CASHFLOW else "Lump Sum",
    )

    with st.expander("Optional trade controls"):
        cooldown_days = st.number_input("Minimum days between trades (cooldown)", min_value=0, value=0)
        max_capital_deployed_inr = st.number_input("Maximum capital deployment (INR, 0 = no cap)", min_value=0.0, value=0.0, step=10000.0)
        max_units = st.number_input("Maximum units (0 = no cap)", min_value=0.0, value=0.0, step=10.0)
        disable_repeat = st.checkbox("Disable repeated same-direction signals", value=False)

    save_to_supabase = st.checkbox("Save results to Supabase", value=False)

    col1, col2 = st.columns(2)
    run_clicked = col1.button("Run Backtest", type="primary")
    reset_clicked = col2.button("Reset Defaults")

if reset_clicked:
    st.rerun()

if run_clicked:
    try:
        price_df = fetch_price_history()
    except SupabaseConfigError as exc:
        st.error(str(exc))
        st.stop()

    if price_df.empty:
        st.error("No price data available. Load historical data on the Data Management page first.")
        st.stop()

    strategy_config = StrategyConfig(
        training_start_date=training_start_date,
        initial_training_end_date=initial_training_end_date,
        signal_start_date=signal_start_date,
        backtest_end_date=backtest_end_date,
        model_type=model_type,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        trade_amount_inr=trade_amount_inr,
        transaction_cost_pct=transaction_cost_pct,
        slippage_pct=slippage_pct,
        risk_free_rate=risk_free_rate,
        benchmark_method=benchmark_method,
        cooldown_days=int(cooldown_days),
        max_capital_deployed_inr=max_capital_deployed_inr or None,
        max_units=max_units or None,
        disable_repeated_same_direction_signals=disable_repeat,
        polynomial_degree=int(polynomial_degree),
        rolling_window_days=int(rolling_window_days),
    )

    with st.spinner("Running walk-forward backtest (refitting the model daily, no look-ahead)..."):
        try:
            result = run_backtest(price_df, strategy_config)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Backtest failed: {exc}")
            st.stop()

    st.session_state["backtest_result"] = result
    st.session_state["backtest_config"] = strategy_config

    if save_to_supabase:
        try:
            insert_signals(result.signals_df)
            insert_trades(result.trades_df)
            insert_daily_state(result.daily_state_df)
            model = get_model(model_type, degree=polynomial_degree, window_days=rolling_window_days)
            fit_result = model.fit(price_df[price_df["trade_date"] <= strategy_config.backtest_end_date])
            insert_model_run(
                {
                    "run_date": date.today(),
                    "model_type": fit_result.model_type,
                    "training_start_date": fit_result.training_start_date,
                    "training_end_date": fit_result.training_end_date,
                    "number_of_observations": fit_result.number_of_observations,
                    "intercept": fit_result.intercept,
                    "coefficient": fit_result.coefficient,
                    "r_squared": fit_result.r_squared,
                    "latest_predicted_price": fit_result.latest_predicted_price,
                    "latest_actual_close": fit_result.latest_actual_close,
                    "latest_deviation_pct": fit_result.latest_deviation_pct,
                }
            )
            st.success("Backtest results saved to Supabase.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to save results to Supabase: {exc}")

result = st.session_state.get("backtest_result")

if result is None:
    st.info("Configure parameters in the sidebar and click **Run Backtest** to get started.")
    st.stop()

if result.signals_df.empty:
    st.warning("Backtest produced no signals — check your date range and training window.")
    st.stop()

st.subheader("Summary")
render_backtest_summary_kpis(result.metrics)

st.divider()
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Actual vs Trend", "Deviation", "Buy/Sell Signals", "Strategy vs Benchmark", "Drawdown"]
)
with tab1:
    st.plotly_chart(trend_chart(result.daily_state_df, result.trades_df), use_container_width=True)
with tab2:
    st.plotly_chart(deviation_chart(result.daily_state_df), use_container_width=True)
with tab3:
    st.plotly_chart(signal_marker_chart(result.signals_df), use_container_width=True)
with tab4:
    st.plotly_chart(portfolio_performance_chart(result.daily_state_df), use_container_width=True)
with tab5:
    st.plotly_chart(drawdown_chart(result.daily_state_df), use_container_width=True)

st.divider()
st.subheader("Trade Log")
st.dataframe(result.trades_df, use_container_width=True)
download_csv_button(result.trades_df, "Export Trade Log CSV", "trade_log.csv")

st.subheader("Daily Signal Log")
st.dataframe(result.signals_df, use_container_width=True)

st.subheader("Performance Metrics (Daily State)")
st.dataframe(result.daily_state_df, use_container_width=True)
download_csv_button(result.daily_state_df, "Export Results CSV", "backtest_daily_state.csv")
