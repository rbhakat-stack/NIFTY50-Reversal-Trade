-- NIFTY Trend Alpha: core schema
-- Run this in the Supabase SQL editor (or via `supabase db push`).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- nifty_daily_prices: validated daily OHLC data
-- ---------------------------------------------------------------------------
create table if not exists public.nifty_daily_prices (
    id uuid primary key default gen_random_uuid(),
    trade_date date unique not null,
    open_price numeric not null,
    high_price numeric,
    low_price numeric,
    close_price numeric not null,
    volume numeric,
    data_source text,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now(),
    constraint chk_open_positive check (open_price > 0),
    constraint chk_close_positive check (close_price > 0)
);

comment on table public.nifty_daily_prices is 'Validated NIFTY 50 daily OHLC data.';

-- ---------------------------------------------------------------------------
-- strategy_signals: daily strategy signals (generated on close of day t)
-- ---------------------------------------------------------------------------
create table if not exists public.strategy_signals (
    id uuid primary key default gen_random_uuid(),
    signal_date date unique not null,
    actual_close numeric not null,
    predicted_trend_price numeric not null,
    deviation_pct numeric not null,
    signal_type text not null,
    model_type text not null,
    buy_threshold numeric not null,
    sell_threshold numeric not null,
    execution_status text,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now(),
    constraint chk_signal_type check (signal_type in ('BUY', 'SELL', 'HOLD')),
    constraint chk_execution_status check (
        execution_status is null or execution_status in ('PENDING', 'EXECUTED', 'NOT_REQUIRED', 'FAILED')
    )
);

comment on table public.strategy_signals is 'Daily strategy signals computed from trend deviation.';

-- ---------------------------------------------------------------------------
-- strategy_trades: executed trades (next trading day open)
-- ---------------------------------------------------------------------------
create table if not exists public.strategy_trades (
    id uuid primary key default gen_random_uuid(),
    signal_date date not null,
    execution_date date not null,
    signal_type text not null,
    signal_close_price numeric not null,
    predicted_trend_price numeric not null,
    deviation_pct numeric not null,
    execution_open_price numeric not null,
    trade_amount_inr numeric not null,
    units_traded numeric not null,
    transaction_cost numeric,
    slippage_cost numeric,
    net_units_change numeric not null,
    portfolio_units_after_trade numeric not null,
    cash_flow numeric not null,
    created_at timestamp with time zone default now(),
    constraint chk_trade_signal_type check (signal_type in ('BUY', 'SELL'))
);

comment on table public.strategy_trades is 'Executed trades resulting from BUY/SELL signals.';

-- ---------------------------------------------------------------------------
-- daily_strategy_state: daily backtest / portfolio state
-- ---------------------------------------------------------------------------
create table if not exists public.daily_strategy_state (
    id uuid primary key default gen_random_uuid(),
    trade_date date unique not null,
    actual_close numeric not null,
    predicted_trend_price numeric,
    deviation_pct numeric,
    signal_type text,
    total_units_held numeric,
    portfolio_market_value numeric,
    cumulative_buy_amount numeric,
    cumulative_sell_amount numeric,
    net_capital_deployed numeric,
    realized_pnl numeric,
    unrealized_pnl numeric,
    total_pnl numeric,
    strategy_return_pct numeric,
    benchmark_return_pct numeric,
    alpha_pct numeric,
    drawdown_pct numeric,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

comment on table public.daily_strategy_state is 'Daily portfolio and performance state for the backtest.';

-- ---------------------------------------------------------------------------
-- model_runs: model metadata / diagnostics
-- ---------------------------------------------------------------------------
create table if not exists public.model_runs (
    id uuid primary key default gen_random_uuid(),
    run_date date not null,
    model_type text not null,
    training_start_date date not null,
    training_end_date date not null,
    number_of_observations integer,
    intercept numeric,
    coefficient numeric,
    r_squared numeric,
    latest_predicted_price numeric,
    latest_actual_close numeric,
    latest_deviation_pct numeric,
    created_at timestamp with time zone default now()
);

comment on table public.model_runs is 'Metadata and diagnostics for each trend model fit.';

-- ---------------------------------------------------------------------------
-- alert_events: generated alerts
-- ---------------------------------------------------------------------------
create table if not exists public.alert_events (
    id uuid primary key default gen_random_uuid(),
    alert_date date not null,
    signal_type text not null,
    message text,
    delivery_channel text,
    delivery_status text,
    created_at timestamp with time zone default now()
);

comment on table public.alert_events is 'Log of alerts generated and their delivery status.';

-- ---------------------------------------------------------------------------
-- Row Level Security (single-user v1: enabled, permissive; tighten for multi-user)
-- ---------------------------------------------------------------------------
alter table public.nifty_daily_prices enable row level security;
alter table public.strategy_signals enable row level security;
alter table public.strategy_trades enable row level security;
alter table public.daily_strategy_state enable row level security;
alter table public.model_runs enable row level security;
alter table public.alert_events enable row level security;

-- Service role bypasses RLS automatically. These policies allow the anon/
-- authenticated key read-only access for the Streamlit client if it is ever
-- used directly; all writes should go through the service role key on the
-- server side only.
create policy if not exists "public read nifty_daily_prices"
    on public.nifty_daily_prices for select using (true);
create policy if not exists "public read strategy_signals"
    on public.strategy_signals for select using (true);
create policy if not exists "public read strategy_trades"
    on public.strategy_trades for select using (true);
create policy if not exists "public read daily_strategy_state"
    on public.daily_strategy_state for select using (true);
create policy if not exists "public read model_runs"
    on public.model_runs for select using (true);
create policy if not exists "public read alert_events"
    on public.alert_events for select using (true);
