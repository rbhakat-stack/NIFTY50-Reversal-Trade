"""Alerts & Notifications: configure and trigger strategy alerts."""
from __future__ import annotations

import streamlit as st

from src import config
from src.alerts import alert_service
from src.data.data_repository import fetch_alert_events, fetch_latest_signal
from src.supabase_client import SupabaseConfigError
from src.ui.components import download_csv_button

st.set_page_config(page_title="Alerts | NIFTY Trend Alpha", layout="wide")
st.title("Alerts & Notifications")
st.caption("Configure how you're notified of BUY/SELL signals. Research tool — not financial advice.")

st.subheader("Delivery Channels")
cols = st.columns(3)
use_email = cols[0].checkbox("Email", value=bool(config.EMAIL_SENDER))
use_streamlit_toast = cols[1].checkbox("Browser Notification (Streamlit)", value=True)
use_webhook = cols[2].checkbox("Slack / Webhook", value=bool(config.ALERT_WEBHOOK_URL))

if use_email and not (config.EMAIL_SENDER and config.EMAIL_PASSWORD and config.ALERT_RECIPIENT_EMAIL):
    st.warning("Email channel selected but EMAIL_SENDER / EMAIL_PASSWORD / ALERT_RECIPIENT_EMAIL are not fully configured.")
if use_webhook and not config.ALERT_WEBHOOK_URL:
    st.warning("Webhook channel selected but ALERT_WEBHOOK_URL is not configured.")

st.subheader("Alert Types")
alert_type_cols = st.columns(2)
enable_buy_sell = alert_type_cols[0].checkbox("BUY / SELL signal generated", value=True)
enable_pending = alert_type_cols[0].checkbox("Signal pending execution", value=True)
enable_trade_executed = alert_type_cols[0].checkbox("Trade executed", value=True)
enable_deviation = alert_type_cols[1].checkbox("Deviation crosses configurable threshold", value=False)
deviation_alert_threshold = alert_type_cols[1].slider("Deviation alert threshold (%)", 5, 50, 10) / 100
enable_ingestion_failed = alert_type_cols[1].checkbox("Data ingestion failed", value=True)

channels = []
if use_email:
    channels.append(alert_service.CHANNEL_EMAIL)
if use_streamlit_toast:
    channels.append(alert_service.CHANNEL_STREAMLIT)
if use_webhook:
    channels.append(alert_service.CHANNEL_WEBHOOK)

st.divider()
st.subheader("Check Latest Signal Now")

try:
    latest_signal = fetch_latest_signal()
except SupabaseConfigError as exc:
    st.error(str(exc))
    latest_signal = None
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not fetch latest signal: {exc}")
    latest_signal = None

if latest_signal:
    st.write(
        f"Latest signal: **{latest_signal['signal_type']}** on {latest_signal['signal_date']} "
        f"(deviation {latest_signal['deviation_pct'] * 100:.2f}%, status: {latest_signal.get('execution_status')})"
    )
    if st.button("Send Alert for Latest Signal", type="primary"):
        if not channels:
            st.error("Select at least one delivery channel above.")
        else:
            try:
                if latest_signal.get("execution_status") == config.EXEC_PENDING and enable_pending:
                    outcome = alert_service.send_pending_execution_alert(latest_signal, channels)
                elif latest_signal["signal_type"] in (config.SIGNAL_BUY, config.SIGNAL_SELL) and enable_buy_sell:
                    outcome = alert_service.send_signal_alert(latest_signal, channels)
                else:
                    outcome = None

                if outcome is None:
                    st.info("No alert type is enabled for the current signal state.")
                elif outcome.duplicate:
                    st.warning("An alert for this signal date/type was already sent — duplicate suppressed.")
                elif outcome.sent:
                    st.success("Alert dispatched.")
                    if alert_service.CHANNEL_STREAMLIT in outcome.channel_results:
                        st.toast(outcome.message)
                else:
                    st.error(f"Alert delivery failed: {outcome.channel_results}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Alert delivery failed: {exc}")

    if enable_deviation and abs(latest_signal["deviation_pct"]) >= deviation_alert_threshold:
        if st.button("Send Deviation Threshold Alert"):
            try:
                outcome = alert_service.send_deviation_threshold_alert(
                    latest_signal["signal_date"], latest_signal["deviation_pct"], deviation_alert_threshold, channels
                )
                st.success("Deviation alert dispatched.") if outcome.sent else st.warning("Alert not sent (duplicate or no channels).")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Alert delivery failed: {exc}")
else:
    st.info("No signal history yet. Run a backtest or the daily refresh workflow first.")

st.divider()
st.subheader("Alert History")
try:
    alerts_df = fetch_alert_events()
    if not alerts_df.empty:
        st.dataframe(alerts_df, use_container_width=True)
        download_csv_button(alerts_df, "Download Alert Log CSV", "alert_events.csv")
    else:
        st.info("No alerts have been sent yet.")
except SupabaseConfigError as exc:
    st.error(str(exc))
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load alert history: {exc}")
