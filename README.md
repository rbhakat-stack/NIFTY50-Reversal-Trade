# NIFTY Trend Alpha

A research, backtesting, and alerting tool for a NIFTY 50 medium-term mean-reversion
strategy. It fits a long-term trend model to the NIFTY 50 index, flags days where the
index deviates significantly from that trend, and backtests a simple BUY/SELL/HOLD
rule with realistic execution timing, transaction costs, and benchmark comparisons.

> **Disclaimer:** This product is for research and educational purposes only. It does
> not provide investment advice, trading advice, or portfolio recommendations. Users
> should consult a qualified financial advisor before making investment decisions.

## How the strategy works

1. **Trend model.** A long-term trend is fit to `log(close_price)` over time using one
   of three configurable models (log-linear regression, polynomial log regression, or a
   rolling exponentially-weighted regression). The default model is trained from
   1 Apr 2000 through 31 Mar 2020.
2. **Signal generation.** From 1 Apr 2020 onward, the model is **refit each day using
   only data up to and including that day** (no look-ahead bias). The deviation of the
   actual close from the model's predicted trend price is computed:
   `deviation_pct = (actual_close - predicted_trend_price) / predicted_trend_price`.
   A deviation below the buy threshold (default -10%) emits a BUY signal, above the
   sell threshold (default +10%) emits a SELL signal, otherwise HOLD.
3. **Execution.** A signal generated on the close of day `t` is executed at the open of
   day `t+1` — never the same day. Sell size is capped at current holdings (no
   short-selling, no negative units). Transaction costs (default 0.05%) and optional
   slippage are applied to every trade.
4. **Benchmarking.** Strategy performance is compared against a buy-and-hold benchmark
   using either a matched-cashflow method (invests the same amounts on the same dates
   as the strategy) or a lump-sum method (invests all strategy capital up front).

See [src/config.py](src/config.py) for all configurable defaults and
[src/strategy/](src/strategy) for the signal, portfolio, benchmark, and backtest
engines.

## Project structure

```
app.py                     Streamlit entry point / home page
pages/                     5 Streamlit pages (Dashboard, Backtest Explorer,
                            Alerts, Model Diagnostics, Data Management)
src/config.py               Central configuration and StrategyConfig
src/supabase_client.py      Supabase client factory
src/data/                   Data ingestion, validation, CSV fallback
src/models/                 Trend models (log-linear, polynomial log, rolling exp)
src/strategy/                Signal, portfolio, benchmark, and backtest engines
src/alerts/                  Email/webhook alert dispatch with dedup
src/ui/                      Formatters, Plotly charts, reusable components
src/utils/                   Logging, trading-day calendar, financial metrics
sql/                         Supabase schema (tables, indexes, RLS policies)
tests/                       pytest unit and integration tests
```

## Setup

### 1. Supabase project

1. Create a project at [supabase.com](https://supabase.com).
2. In the SQL editor, run [sql/001_create_tables.sql](sql/001_create_tables.sql)
   followed by [sql/002_indexes_and_constraints.sql](sql/002_indexes_and_constraints.sql).
   This creates the six tables (`nifty_daily_prices`, `strategy_signals`,
   `strategy_trades`, `daily_strategy_state`, `model_runs`, `alert_events`) with their
   constraints, indexes, and row-level security policies.
3. Copy the project URL, `anon` key, and `service_role` key from Project Settings > API.

### 2. Environment variables

Copy `.env.example` to `.env` and fill in your values:

```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
EMAIL_SENDER=
EMAIL_PASSWORD=
ALERT_RECIPIENT_EMAIL=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
ALERT_WEBHOOK_URL=
```

The `service_role` key is used server-side for all writes; the `anon` key is used for
public reads. Never expose the `service_role` key in client-facing code.

### 3. Local install and run

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate.bat on cmd
pip install -r requirements.txt
streamlit run app.py
```

### 4. Load historical data

Open the **Data Management** page in the app and either:
- Click "Refresh from Yahoo Finance" to pull NIFTY 50 (`^NSEI`) history via `yfinance`,
  with NSE as a secondary source, or
- Upload a CSV with `trade_date, open_price, high_price, low_price, close_price, volume`
  columns as a manual fallback.

Data is validated (positive prices, OHLC consistency, deduplication by date, missing
business day detection) before being upserted into `nifty_daily_prices`.

### 5. Run a backtest

Open the **Backtest Explorer** page, choose a model type, thresholds, trade size,
transaction cost/slippage, optional trade controls (cooldown, max capital, max units,
disable-repeat-direction), and benchmark method, then run the backtest. Results
(equity curve, trade log, signals, and summary metrics — CAGR, Sharpe, Sortino, max
drawdown, win/loss ratio, alpha vs. benchmark) are shown in the UI and can be persisted
to Supabase for later reference from the **Dashboard** and **Model Diagnostics** pages.

### 6. Configure alerts

Set `EMAIL_SENDER` / `EMAIL_PASSWORD` / `ALERT_RECIPIENT_EMAIL` (and/or
`ALERT_WEBHOOK_URL`) in `.env`, then use the **Alerts & Notifications** page to review
and dispatch the day's signal. Alerts are deduplicated by `(alert_date, signal_type)`
so the same signal is never sent twice.

## Deployment

The app is a standard multi-page Streamlit app and can be deployed to Streamlit
Community Cloud or any host that runs `streamlit run app.py`. Set the same environment
variables listed above as secrets in your deployment environment (for Streamlit
Community Cloud, use `.streamlit/secrets.toml` or the app's Secrets settings — these
are read automatically by `src/config.py`'s `_get_secret` fallback).

## Testing

```bash
python -m pytest tests/ -q
```

The suite covers OHLC data validation, trend model correctness (recovering known
coefficients from synthetic data), no-look-ahead behavior at both the model-fit and
signal-generation levels, portfolio execution rules (next-day-open timing, no
short-selling, cooldown, repeat-direction suppression), benchmark computations, and
end-to-end backtest reproducibility.

## Key assumptions and limitations

- Signals are generated from **daily close prices only**; intraday price action is not
  modeled.
- Execution is assumed to always fill at the next trading day's open price, with no
  partial fills or liquidity constraints.
- The trend models assume the long-term log-price trend is a reasonable fair-value
  anchor; this assumption can break down during structural regime changes.
- No leverage, no short-selling, and no derivatives are modeled.
- This is a **research and educational tool** — it does not place real trades and does
  not constitute investment advice.
