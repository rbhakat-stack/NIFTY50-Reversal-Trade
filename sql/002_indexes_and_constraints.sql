-- Additional indexes to support common query patterns in the app.

create index if not exists idx_nifty_daily_prices_trade_date
    on public.nifty_daily_prices (trade_date desc);

create index if not exists idx_strategy_signals_signal_date
    on public.strategy_signals (signal_date desc);

create index if not exists idx_strategy_signals_type
    on public.strategy_signals (signal_type);

create index if not exists idx_strategy_trades_execution_date
    on public.strategy_trades (execution_date desc);

create index if not exists idx_strategy_trades_signal_date
    on public.strategy_trades (signal_date desc);

create index if not exists idx_daily_strategy_state_trade_date
    on public.daily_strategy_state (trade_date desc);

create index if not exists idx_model_runs_run_date
    on public.model_runs (run_date desc);

create index if not exists idx_alert_events_alert_date
    on public.alert_events (alert_date desc);

create index if not exists idx_alert_events_dedupe
    on public.alert_events (alert_date, signal_type);

-- updated_at auto-touch triggers
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_nifty_daily_prices_updated_at on public.nifty_daily_prices;
create trigger trg_nifty_daily_prices_updated_at
    before update on public.nifty_daily_prices
    for each row execute function public.set_updated_at();

drop trigger if exists trg_strategy_signals_updated_at on public.strategy_signals;
create trigger trg_strategy_signals_updated_at
    before update on public.strategy_signals
    for each row execute function public.set_updated_at();

drop trigger if exists trg_daily_strategy_state_updated_at on public.daily_strategy_state;
create trigger trg_daily_strategy_state_updated_at
    before update on public.daily_strategy_state
    for each row execute function public.set_updated_at();
