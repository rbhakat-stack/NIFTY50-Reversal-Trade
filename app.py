"""
NIFTY Trend Alpha — home page.

Research, backtesting, and alerting tool for a NIFTY 50 medium-term
mean-reversion strategy. This is NOT financial advice.
"""
from __future__ import annotations

import streamlit as st

from src.supabase_client import SupabaseConfigError, is_configured
from src.ui.components import render_signal_badge

st.set_page_config(page_title="NIFTY Trend Alpha", page_icon="📈", layout="wide")

st.sidebar.title("NIFTY Trend Alpha")
st.sidebar.caption("Research • Backtesting • Alerting")
st.sidebar.info(
    "This product is for research and educational purposes only. It does not "
    "provide investment advice, trading advice, or portfolio recommendations. "
    "Users should consult a qualified financial advisor before making "
    "investment decisions."
)

st.title("📈 NIFTY Trend Alpha")
st.caption("A transparent, rules-based mean-reversion research tool for NIFTY 50.")

st.markdown(
    """
This app studies a simple idea: **NIFTY 50's daily close tends to revert toward
its long-run log-price trend line**. When the market trades far below trend,
the strategy research flags a potential accumulation opportunity; far above
trend, a potential profit-taking opportunity. Everything here is a backtest —
past behavior of a rules-based model does not predict future returns.

Use the sidebar to navigate:
- **Dashboard** — current signal, trend chart, portfolio performance
- **Backtest Explorer** — configure and re-run the strategy with custom parameters
- **Alerts** — configure email / webhook notifications
- **Model Diagnostics** — regression details, residuals, data quality
- **Data Management** — refresh data, upload CSV, inspect the raw price history
"""
)

st.divider()

if not is_configured():
    st.error(
        "Supabase connection failed. Please check environment variables "
        "(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) in your .env file or "
        "Streamlit secrets."
    )
else:
    try:
        from src.data.data_repository import fetch_latest_portfolio_state, fetch_latest_signal

        latest_signal = fetch_latest_signal()
        latest_state = fetch_latest_portfolio_state()

        if latest_signal:
            st.subheader("Current Signal Snapshot")
            cols = st.columns([1, 3])
            with cols[0]:
                render_signal_badge(latest_signal["signal_type"], latest_signal.get("execution_status"))
            with cols[1]:
                st.write(
                    f"As of **{latest_signal['signal_date']}**, deviation from trend is "
                    f"**{latest_signal['deviation_pct'] * 100:.2f}%** "
                    f"(actual close {latest_signal['actual_close']:.2f} vs predicted trend "
                    f"{latest_signal['predicted_trend_price']:.2f})."
                )
            if latest_state:
                st.metric("Latest Portfolio Value", f"₹{latest_state['portfolio_market_value']:,.2f}")
        else:
            st.info("No signals generated yet. Visit Data Management to load historical data, then run a backtest.")
    except SupabaseConfigError as exc:
        st.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any backend issue to the user
        st.error(f"Could not load latest strategy status: {exc}")

st.caption(
    "Disclaimer: This product is for research and educational purposes only. "
    "It does not provide investment advice, trading advice, or portfolio "
    "recommendations. Users should consult a qualified financial advisor "
    "before making investment decisions."
)
