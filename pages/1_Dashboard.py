"""Dashboard: executive summary of current strategy status."""
from __future__ import annotations

import streamlit as st

from src import config
from src.data.data_repository import (
    fetch_backtest_results,
    fetch_latest_portfolio_state,
    fetch_latest_signal,
    fetch_price_history,
    fetch_signals,
    fetch_trades,
)
from src.supabase_client import SupabaseConfigError
from src.ui.charts import portfolio_performance_chart, trend_chart
from src.ui.components import download_csv_button, render_dashboard_kpis, render_signal_badge
from src.utils.date_utils import get_next_trading_day

st.set_page_config(page_title="Dashboard | NIFTY Trend Alpha", layout="wide")
st.title("Dashboard")
st.caption("Executive summary of current strategy status. Research tool — not financial advice.")

try:
    latest_signal = fetch_latest_signal()
    latest_state = fetch_latest_portfolio_state()
    price_df = fetch_price_history()
except SupabaseConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load dashboard data: {exc}")
    st.stop()

if not latest_signal:
    st.info("No signals available yet. Go to Data Management to load data, then Backtest Explorer to run the strategy.")
    st.stop()

next_action_date = None
if price_df is not None and not price_df.empty:
    next_action_date = get_next_trading_day(latest_signal["signal_date"], price_df["trade_date"])

render_dashboard_kpis(
    latest_close=latest_signal["actual_close"],
    predicted_trend_price=latest_signal["predicted_trend_price"],
    deviation_pct=latest_signal["deviation_pct"],
    signal_type=latest_signal["signal_type"],
    next_action_date=next_action_date,
    portfolio_value=latest_state["portfolio_market_value"] if latest_state else None,
    alpha_pct=latest_state.get("alpha_pct") if latest_state else None,
)

st.divider()
st.subheader("Signal Status")
render_signal_badge(latest_signal["signal_type"], latest_signal.get("execution_status"))
if latest_signal.get("execution_status") == config.EXEC_PENDING:
    st.warning("Signal generated but execution is pending because next trading day open is unavailable.")

st.divider()
st.subheader("Trend Chart")
daily_state_df = fetch_backtest_results()
trades_df = fetch_trades()
st.plotly_chart(trend_chart(daily_state_df, trades_df), use_container_width=True)

st.subheader("Portfolio Performance")
st.plotly_chart(portfolio_performance_chart(daily_state_df), use_container_width=True)

st.divider()
st.subheader("Recent Signals")
signals_df = fetch_signals()
if not signals_df.empty:
    recent = signals_df.sort_values("signal_date", ascending=False).head(20)
    trades_indexed = trades_df.set_index("signal_date") if not trades_df.empty else trades_df
    display_cols = ["signal_date", "signal_type", "actual_close", "predicted_trend_price", "deviation_pct", "execution_status"]
    st.dataframe(recent[[c for c in display_cols if c in recent.columns]], use_container_width=True)
    download_csv_button(recent, "Download Recent Signals CSV", "recent_signals.csv")
else:
    st.info("No signal history available yet.")
