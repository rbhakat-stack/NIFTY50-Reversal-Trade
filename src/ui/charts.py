"""Plotly chart builders used across the Dashboard, Backtest Explorer, and
Model Diagnostics pages."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import config
from src.ui.formatters import SIGNAL_COLORS

PRIMARY_COLOR = "#2563eb"  # actual NIFTY
TREND_COLOR = "#7c3aed"  # dashed trend
BAND_COLOR = "rgba(124, 58, 237, 0.15)"
BENCHMARK_COLOR = "#9ca3af"  # muted secondary


def trend_chart(daily_state_df: pd.DataFrame, trades_df: pd.DataFrame | None = None) -> go.Figure:
    """
    Actual close vs predicted trend, +/- threshold bands, and buy/sell
    markers (using execution price where a trade occurred, else the
    signal's actual_close as a fallback marker position).
    """
    fig = go.Figure()
    df = daily_state_df.dropna(subset=["predicted_trend_price"]).copy() if not daily_state_df.empty else daily_state_df

    if df.empty:
        fig.update_layout(title="No data available for the selected range.")
        return fig

    upper_band = df["predicted_trend_price"] * (1 + config.DEFAULT_SELL_THRESHOLD)
    lower_band = df["predicted_trend_price"] * (1 + config.DEFAULT_BUY_THRESHOLD)

    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=upper_band, mode="lines",
            line=dict(width=0.5, color=TREND_COLOR), name="Upper Threshold (+10%)", showlegend=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=lower_band, mode="lines",
            line=dict(width=0.5, color=TREND_COLOR), name="Lower Threshold (-10%)",
            fill="tonexty", fillcolor=BAND_COLOR, showlegend=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=df["predicted_trend_price"], mode="lines",
            line=dict(dash="dash", color=TREND_COLOR, width=2), name="Predicted Trend",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=df["actual_close"], mode="lines",
            line=dict(color=PRIMARY_COLOR, width=2), name="Actual NIFTY Close",
            customdata=np.stack([df["deviation_pct"] * 100, df["signal_type"].fillna("")], axis=-1),
            hovertemplate=(
                "Date: %{x}<br>Close: %{y:.2f}<br>Deviation: %{customdata[0]:.2f}%<br>"
                "Signal: %{customdata[1]}<extra></extra>"
            ),
        )
    )

    if trades_df is not None and not trades_df.empty:
        for signal_type, color in SIGNAL_COLORS.items():
            if signal_type == config.SIGNAL_HOLD:
                continue
            subset = trades_df[trades_df["signal_type"] == signal_type]
            if subset.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=subset["execution_date"], y=subset["execution_open_price"], mode="markers",
                    marker=dict(color=color, size=10, symbol="triangle-up" if signal_type == config.SIGNAL_BUY else "triangle-down"),
                    name=f"{signal_type} Executed",
                    customdata=np.stack([subset["signal_date"], subset["trade_amount_inr"], subset["units_traded"]], axis=-1),
                    hovertemplate=(
                        "Execution Date: %{x}<br>Open: %{y:.2f}<br>Signal Date: %{customdata[0]}<br>"
                        "Trade Amount: ₹%{customdata[1]:.2f}<br>Units: %{customdata[2]:.4f}<extra></extra>"
                    ),
                )
            )

    fig.update_layout(
        title="NIFTY 50: Actual vs Predicted Trend",
        xaxis_title="Date",
        yaxis_title="Price",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def portfolio_performance_chart(daily_state_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if daily_state_df.empty:
        fig.update_layout(title="No backtest results available.")
        return fig

    fig.add_trace(
        go.Scatter(
            x=daily_state_df["trade_date"], y=daily_state_df["portfolio_market_value"],
            mode="lines", line=dict(color=PRIMARY_COLOR, width=2), name="Strategy Portfolio Value",
        )
    )
    if "benchmark_market_value" in daily_state_df.columns:
        fig.add_trace(
            go.Scatter(
                x=daily_state_df["trade_date"], y=daily_state_df["benchmark_market_value"],
                mode="lines", line=dict(color=BENCHMARK_COLOR, width=2, dash="dot"), name="Benchmark Value",
            )
        )
    if "alpha_pct" in daily_state_df.columns:
        fig.add_trace(
            go.Scatter(
                x=daily_state_df["trade_date"], y=daily_state_df["alpha_pct"] * 100,
                mode="lines", line=dict(color="#059669", width=1.5), name="Cumulative Alpha (%)", yaxis="y2",
            )
        )
        fig.update_layout(yaxis2=dict(title="Alpha (%)", overlaying="y", side="right"))

    fig.update_layout(
        title="Strategy vs Benchmark Performance",
        xaxis_title="Date",
        yaxis_title="Portfolio Value (INR)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def deviation_chart(daily_state_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if daily_state_df.empty:
        fig.update_layout(title="No data available.")
        return fig
    fig.add_trace(
        go.Scatter(
            x=daily_state_df["trade_date"], y=daily_state_df["deviation_pct"] * 100,
            mode="lines", line=dict(color=TREND_COLOR, width=1.5), name="Deviation %",
        )
    )
    fig.add_hline(y=config.DEFAULT_SELL_THRESHOLD * 100, line_dash="dot", line_color=SIGNAL_COLORS[config.SIGNAL_SELL])
    fig.add_hline(y=config.DEFAULT_BUY_THRESHOLD * 100, line_dash="dot", line_color=SIGNAL_COLORS[config.SIGNAL_BUY])
    fig.add_hline(y=0, line_dash="dash", line_color="#9ca3af")
    fig.update_layout(title="Deviation from Trend", xaxis_title="Date", yaxis_title="Deviation (%)")
    return fig


def signal_marker_chart(signals_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if signals_df.empty:
        fig.update_layout(title="No signals available.")
        return fig
    for signal_type, color in SIGNAL_COLORS.items():
        subset = signals_df[signals_df["signal_type"] == signal_type]
        fig.add_trace(
            go.Scatter(
                x=subset["signal_date"], y=subset["deviation_pct"] * 100, mode="markers",
                marker=dict(color=color, size=7), name=signal_type,
            )
        )
    fig.update_layout(title="Buy/Sell/Hold Signals Over Time", xaxis_title="Date", yaxis_title="Deviation (%)")
    return fig


def drawdown_chart(daily_state_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if daily_state_df.empty or "drawdown_pct" not in daily_state_df.columns:
        fig.update_layout(title="No data available.")
        return fig
    fig.add_trace(
        go.Scatter(
            x=daily_state_df["trade_date"], y=daily_state_df["drawdown_pct"] * 100,
            mode="lines", line=dict(color="#dc2626", width=1.5), fill="tozeroy", name="Drawdown %",
        )
    )
    fig.update_layout(title="Portfolio Drawdown", xaxis_title="Date", yaxis_title="Drawdown (%)")
    return fig


def residual_histogram(deviation_series: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=deviation_series * 100, marker_color=PRIMARY_COLOR, nbinsx=50))
    fig.update_layout(title="Distribution of Deviation %", xaxis_title="Deviation (%)", yaxis_title="Count")
    return fig
