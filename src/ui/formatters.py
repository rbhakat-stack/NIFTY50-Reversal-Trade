"""Display formatting helpers shared across Streamlit pages."""
from __future__ import annotations

from src import config

SIGNAL_COLORS = {
    config.SIGNAL_BUY: "#16a34a",  # green
    config.SIGNAL_SELL: "#dc2626",  # red
    config.SIGNAL_HOLD: "#6b7280",  # gray
}
PENDING_COLOR = "#d97706"  # amber


def format_inr(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"₹{value:,.2f}"


def format_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def format_units(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.4f}"


def signal_color(signal_type: str, execution_status: str | None = None) -> str:
    if execution_status == config.EXEC_PENDING:
        return PENDING_COLOR
    return SIGNAL_COLORS.get(signal_type, "#6b7280")


def signal_label(signal_type: str, execution_status: str | None = None) -> str:
    if execution_status == config.EXEC_PENDING:
        return f"{signal_type} (Pending)"
    return signal_type
