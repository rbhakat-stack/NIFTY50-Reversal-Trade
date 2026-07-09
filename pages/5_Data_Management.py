"""Data Management: data transparency and operational control."""
from __future__ import annotations

from datetime import date

import streamlit as st

from src import config
from src.data.csv_loader import load_nifty_from_csv
from src.data.data_fetcher import (
    diagnose_data_source_environment,
    fetch_nifty_from_nse,
    fetch_nifty_from_yfinance,
    refresh_latest_nifty_data,
)
from src.data.data_repository import fetch_price_history, upsert_daily_prices
from src.data.data_validator import validate_ohlc_data
from src.supabase_client import SupabaseConfigError
from src.ui.components import download_csv_button, render_missing_days_table
from src.utils.date_utils import find_missing_business_days

st.set_page_config(page_title="Data Management | NIFTY Trend Alpha", layout="wide")
st.title("Data Management")
st.caption("Data transparency and operational control. Research tool — not financial advice.")

try:
    price_df = fetch_price_history()
except SupabaseConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load price history: {exc}")
    st.stop()

env_info = diagnose_data_source_environment()
if env_info["likely_wrong_interpreter"] or not env_info["yfinance_version_ok"] or not env_info["nsepython_installed"]:
    with st.expander("⚠️ Data source environment check — click to view", expanded=True):
        st.warning(
            "This Python process may not be running from the project's `.venv`. "
            "NSE and Yahoo Finance fetch failures often look like outages but are "
            "actually caused by running the app with the wrong interpreter (missing "
            "or outdated packages)."
        )
        st.code(
            f"Python executable: {env_info['python_executable']}\n"
            f"yfinance version:  {env_info['yfinance_version'] or 'not installed'} "
            f"({'OK' if env_info['yfinance_version_ok'] else 'outdated / needs >= 1.5.1'})\n"
            f"nsepython installed: {env_info['nsepython_installed']}",
            language="text",
        )
        st.caption(
            "Fix: stop the app, activate the project virtual environment, then restart it, e.g. "
            "(from the project root) `.venv\\Scripts\\activate` then `streamlit run app.py` on "
            "Windows, or `source .venv/Scripts/activate && streamlit run app.py` in Git Bash."
        )
else:
    st.caption(f"Environment OK — running from `{env_info['python_executable']}`.")

st.subheader("Current Data Status")
cols = st.columns(4)
cols[0].metric("Row Count", len(price_df))
cols[1].metric("Earliest Date", str(price_df["trade_date"].min()) if not price_df.empty else "N/A")
cols[2].metric("Latest Date", str(price_df["trade_date"].max()) if not price_df.empty else "N/A")
if not price_df.empty and "data_source" in price_df.columns:
    cols[3].metric("Data Sources", ", ".join(sorted(price_df["data_source"].dropna().unique())))
else:
    cols[3].metric("Data Sources", "N/A")

st.divider()
st.subheader("Refresh Data")
refresh_cols = st.columns(2)
with refresh_cols[0]:
    if st.button("Refresh Latest Data", type="primary"):
        with st.spinner("Fetching latest NIFTY 50 data (NSE primary, Yahoo Finance fallback)..."):
            try:
                result = refresh_latest_nifty_data()
            except SupabaseConfigError as exc:
                st.error(str(exc))
                result = None
        if result:
            for w in result.warnings:
                st.warning(w)
            if result.success:
                st.success(f"Refreshed {result.rows_upserted} row(s) from {result.source_used or 'no new data needed'}.")
            else:
                st.error(result.error or "Latest NIFTY data is not available yet.")

with refresh_cols[1]:
    if st.button("Load Full History (from 1 Apr 2000)"):
        with st.spinner("Loading full historical data — this may take a minute..."):
            errors = []
            loaded = False
            for source_name, fetch_fn in (
                (config.DATA_SOURCE_NSE, fetch_nifty_from_nse),
                (config.DATA_SOURCE_YFINANCE, fetch_nifty_from_yfinance),
            ):
                try:
                    raw_df = fetch_fn(config.HISTORICAL_START_DATE, date.today())
                    validation = validate_ohlc_data(raw_df, data_source=source_name)
                    for w in validation.warnings:
                        st.warning(w)
                    if validation.is_valid:
                        rows = upsert_daily_prices(validation.clean_df)
                        st.success(f"Loaded {rows} rows from {source_name}.")
                        loaded = True
                        break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{source_name}: {exc}")
            if not loaded:
                st.error("Data refresh failed from primary source; fallback also failed. " + "; ".join(errors))

st.divider()
st.subheader("Missing Trading Days")
if not price_df.empty:
    missing_days = find_missing_business_days(price_df["trade_date"], price_df["trade_date"].min(), price_df["trade_date"].max())
    render_missing_days_table(missing_days)
else:
    st.info("No data loaded yet.")

st.subheader("Duplicate Records Check")
if not price_df.empty:
    dup_count = int(price_df["trade_date"].duplicated().sum())
    if dup_count:
        st.error(f"{dup_count} duplicate trade_date row(s) found — this should not happen given the unique constraint; investigate the source data.")
    else:
        st.success("No duplicate trade dates found.")

st.divider()
st.subheader("Export Raw Data")
if not price_df.empty:
    st.dataframe(price_df.sort_values("trade_date", ascending=False), use_container_width=True)
    download_csv_button(price_df, "Export Raw Data CSV", "nifty_daily_prices.csv")
else:
    st.info("No data to export yet.")

st.divider()
st.subheader("Manual CSV Upload (fallback)")
st.caption("Expected schema: date, open, high, low, close, volume")
uploaded_file = st.file_uploader("Upload NIFTY 50 OHLC CSV", type=["csv"])
if uploaded_file is not None:
    try:
        validation = load_nifty_from_csv(uploaded_file)
    except ValueError as exc:
        st.error(f"CSV upload validation failed: {exc}")
        validation = None

    if validation is not None:
        for w in validation.warnings:
            st.warning(w)
        if not validation.dropped_rows.empty:
            with st.expander(f"{len(validation.dropped_rows)} row(s) dropped during validation"):
                st.dataframe(validation.dropped_rows, use_container_width=True)

        if validation.is_valid:
            st.write(f"{len(validation.clean_df)} valid row(s) ready to merge.")
            st.dataframe(validation.clean_df.head(20), use_container_width=True)
            if st.button("Merge Uploaded Data into Supabase", type="primary"):
                try:
                    rows = upsert_daily_prices(validation.clean_df)
                    st.success(f"Merged {rows} row(s) into Supabase.")
                except SupabaseConfigError as exc:
                    st.error(str(exc))
        else:
            st.error("No valid rows remained after validation; nothing was merged.")
