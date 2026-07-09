"""Reusable Streamlit UI components shared across pages."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config
from src.ui.formatters import format_inr, format_pct, format_units, signal_color, signal_label


def render_signal_badge(signal_type: str, execution_status: str | None = None) -> None:
    color = signal_color(signal_type, execution_status)
    label = signal_label(signal_type, execution_status)
    st.markdown(
        f"""
        <div style="display:inline-block;padding:8px 20px;border-radius:20px;
                     background-color:{color};color:white;font-weight:600;font-size:1.1rem;">
            {label}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_kpis(
    latest_close: float | None,
    predicted_trend_price: float | None,
    deviation_pct: float | None,
    signal_type: str | None,
    next_action_date,
    portfolio_value: float | None,
    alpha_pct: float | None,
) -> None:
    cols = st.columns(4)
    cols[0].metric("Latest NIFTY Close", format_inr(latest_close))
    cols[1].metric("Predicted Trend Price", format_inr(predicted_trend_price))
    cols[2].metric("Current Deviation", format_pct(deviation_pct))
    with cols[3]:
        st.markdown("**Current Signal**")
        if signal_type:
            render_signal_badge(signal_type)
        else:
            st.write("N/A")

    cols2 = st.columns(3)
    cols2[0].metric("Next Action Date", str(next_action_date) if next_action_date else "N/A")
    cols2[1].metric("Portfolio Value", format_inr(portfolio_value))
    cols2[2].metric("Alpha vs Benchmark", format_pct(alpha_pct))


def render_backtest_summary_kpis(metrics: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Final Portfolio Value", format_inr(metrics.get("final_portfolio_value")))
    cols[1].metric("Total Capital Deployed", format_inr(metrics.get("total_capital_deployed")))
    cols[2].metric("Total Return", format_pct(metrics.get("total_return_pct")))
    cols[3].metric("Strategy CAGR", format_pct(metrics.get("strategy_cagr")))

    cols2 = st.columns(4)
    cols2[0].metric("Alpha vs NIFTY (CAGR)", format_pct(metrics.get("alpha_vs_benchmark_cagr")))
    cols2[1].metric("Max Drawdown", format_pct(metrics.get("max_drawdown_pct")))
    cols2[2].metric("Number of Trades", str(metrics.get("number_of_trades", 0)))
    cols2[3].metric("Units Held", format_units(metrics.get("current_units_held")))

    cols3 = st.columns(4)
    cols3[0].metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
    cols3[1].metric("Sortino Ratio", f"{metrics.get('sortino_ratio', 0):.2f}")
    cols3[2].metric("Total P&L", format_inr(metrics.get("total_pnl")))
    cols3[3].metric("Net Capital Deployed", format_inr(metrics.get("net_capital_deployed")))


def render_data_warnings(warnings: list[str]) -> None:
    for w in warnings:
        st.warning(w)


def render_missing_days_table(missing_days: list) -> None:
    if not missing_days:
        st.success("No missing business days detected in the current range.")
        return
    st.warning(f"{len(missing_days)} business day(s) with no trading data (review for holidays vs. real gaps).")
    st.dataframe(pd.DataFrame({"missing_date": missing_days}), use_container_width=True)


def download_csv_button(df: pd.DataFrame, label: str, file_name: str) -> None:
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
    )
