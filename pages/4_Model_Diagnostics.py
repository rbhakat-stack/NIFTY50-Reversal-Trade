"""Model Diagnostics: make the trend model transparent and auditable."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src import config
from src.data.data_repository import fetch_latest_model_run, fetch_price_history, fetch_signals
from src.data.data_validator import validate_ohlc_data
from src.models.trend_model import get_model
from src.supabase_client import SupabaseConfigError
from src.ui.charts import residual_histogram
from src.utils.date_utils import add_trading_day_index
from src.utils.metrics import daily_returns

st.set_page_config(page_title="Model Diagnostics | NIFTY Trend Alpha", layout="wide")
st.title("Model Diagnostics")
st.caption("Full transparency into how the trend line is estimated. Research tool — not financial advice.")

st.info(
    "The trend line estimates the long-term fair-value path of NIFTY 50 based on historical "
    "closing prices. The strategy assumes that large deviations below the trend may represent "
    "accumulation opportunities, while large deviations above the trend may represent "
    "profit-taking opportunities."
)

try:
    price_df = fetch_price_history()
    signals_df = fetch_signals()
    latest_model_run = fetch_latest_model_run()
except SupabaseConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load diagnostics data: {exc}")
    st.stop()

if price_df.empty:
    st.warning("No price data available yet. Load historical data on the Data Management page.")
    st.stop()

st.subheader("Current Model")
model_type = st.selectbox(
    "Model type to inspect",
    [config.MODEL_TYPE_LOG_LINEAR, config.MODEL_TYPE_POLY_LOG, config.MODEL_TYPE_ROLLING_EXP],
    format_func=lambda v: v.replace("_", " ").title(),
)

try:
    model = get_model(model_type)
    fit_result = model.fit(price_df)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

cols = st.columns(4)
cols[0].metric("Training Start", str(fit_result.training_start_date))
cols[1].metric("Training End", str(fit_result.training_end_date))
cols[2].metric("Observations", fit_result.number_of_observations)
cols[3].metric("R-squared", f"{fit_result.r_squared:.4f}")

cols2 = st.columns(4)
cols2[0].metric("Intercept (alpha)", f"{fit_result.intercept:.6f}")
cols2[1].metric("Coefficient (beta)", f"{fit_result.coefficient:.8f}")
cols2[2].metric("Latest Predicted Price", f"₹{fit_result.latest_predicted_price:,.2f}")
cols2[3].metric("Latest Deviation", f"{fit_result.latest_deviation_pct * 100:.2f}%")

if latest_model_run:
    st.caption(f"Latest saved model run: {latest_model_run.get('run_date')} ({latest_model_run.get('model_type')})")

st.divider()
st.subheader("Residuals (log-price actual minus predicted)")
indexed = add_trading_day_index(price_df)
predicted_log = np.log(model.predict_series(indexed))
actual_log = np.log(indexed["close_price"])
residuals = actual_log - predicted_log
st.line_chart(pd.DataFrame({"trade_date": indexed["trade_date"], "residual": residuals}).set_index("trade_date"))

st.subheader("Distribution of Deviation %")
if not signals_df.empty:
    st.plotly_chart(residual_histogram(signals_df["deviation_pct"]), use_container_width=True)

    st.subheader("Historical Threshold Breaches")
    breach_cols = st.columns(3)
    breach_cols[0].metric("BUY signals (≤ -10%)", int((signals_df["signal_type"] == config.SIGNAL_BUY).sum()))
    breach_cols[1].metric("SELL signals (≥ +10%)", int((signals_df["signal_type"] == config.SIGNAL_SELL).sum()))
    breach_cols[2].metric("HOLD signals", int((signals_df["signal_type"] == config.SIGNAL_HOLD).sum()))
else:
    st.info("No signal history yet — run a backtest on the Backtest Explorer page.")

st.divider()
st.subheader("Data Quality")
validation = validate_ohlc_data(price_df.rename(columns={
    "trade_date": "trade_date", "open_price": "open_price", "high_price": "high_price",
    "low_price": "low_price", "close_price": "close_price", "volume": "volume",
}))
if validation.warnings:
    for w in validation.warnings:
        st.warning(w)
else:
    st.success("No data quality issues detected in the stored price history.")

if validation.missing_business_days:
    with st.expander(f"{len(validation.missing_business_days)} missing business day(s)"):
        st.dataframe(pd.DataFrame({"missing_date": validation.missing_business_days}), use_container_width=True)

st.subheader("Outlier Detection (daily return z-score)")
returns = daily_returns(price_df.sort_values("trade_date")["close_price"])
z_scores = (returns - returns.mean()) / returns.std(ddof=0)
outliers = price_df.sort_values("trade_date").assign(daily_return=returns.values, z_score=z_scores.values)
outliers = outliers[outliers["z_score"].abs() >= 4]
if not outliers.empty:
    st.warning(f"{len(outliers)} day(s) with |z-score| >= 4 on daily returns — review for data errors or genuine market shocks.")
    st.dataframe(outliers[["trade_date", "close_price", "daily_return", "z_score"]], use_container_width=True)
else:
    st.success("No extreme daily-return outliers detected (|z-score| < 4).")
