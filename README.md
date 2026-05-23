# stock_news_watch

`stock_news_watch` is a standalone, reusable Codex demo that watches live market news for `MSFT`, `AAPL`, and `GOOGL`, classifies only high-severity negative events, and exposes a live-refresh dashboard with a heartbeat and event log.

## What it does

- Runs as a self-contained Python project with its own virtual environment.
- Checks live sources on an hourly cadence during market hours and a bit before open.
- Can also run in `always_on` mode for 24/7 monitoring.
- Uses `codex exec` with `gpt-5.4-mini` when available, with web search and network access enabled.
- Falls back to a deterministic heuristic review if Codex is unavailable, so the demo still runs.
- Runs one startup cycle before serving the dashboard so the page always opens with fresh content.
- Uses a clean white, icon-based homepage with a readable six-class briefing scale.
- Stores runtime state in `.runtime/` and serves it through a small dashboard.
- Stays alert-only: no brokerage integration, no auto-sell, no trade execution.

## Project layout

- `stock_news_watch/` application code
- `config/stock_news_watch.json` default settings
- `.runtime/` generated heartbeat, event, and state files
- `tests/` unit and integration smoke tests

## Setup

```powershell
cd C:\Users\Max\code\work\stock_news_watch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

This project uses only the Python standard library, so there are no third-party packages to install.

## Run

Start the dashboard and loop together:

```powershell
python -m stock_news_watch demo
```

Run just the dashboard:

```powershell
python -m stock_news_watch serve
```

Run just one cycle:

```powershell
python -m stock_news_watch run-once
```

Check status:

```powershell
python -m stock_news_watch status
```

## Codex setup

To use the Codex-powered review path, install and authenticate the Codex CLI, then make sure `codex` is on your `PATH`.

Quick check:

```powershell
Get-Command codex
codex --help
```

If those commands fail, install the Codex CLI first and reopen the terminal.

If you want the login to stay isolated to this repo, point `CODEX_HOME` at a repo-local folder before logging in, the same way the other workspace projects do:

```powershell
$env:CODEX_HOME = "C:\Users\Max\code\work\stock_news_watch\.runtime\codex_home"
codex login --device-auth
codex login status
```

That keeps the Codex session and cached auth data scoped to this project instead of your whole user profile.

If you prefer a one-liner helper, use [`scripts/login_codex.ps1`](scripts/login_codex.ps1):

```powershell
cd C:\Users\Max\code\work\stock_news_watch
.\scripts\login_codex.ps1
```

After login, verify the session from the same terminal or a new terminal:

```powershell
$env:CODEX_HOME = "C:\Users\Max\code\work\stock_news_watch\.runtime\codex_home"
codex login status
```

For debugging, run a single visible cycle first:

```powershell
python -m stock_news_watch run-once
```

That is the best way to confirm the dashboard, heartbeat, and Codex buckets are updating before you leave the loop running.

The default runtime settings use:

- model: `gpt-5.4-mini`
- web search: `auto`
- network access: enabled

Live sources include:

- Yahoo Finance RSS
- Google News RSS queries that pull Reuters/AP and official company pages
- SEC filings
- Company newsroom pages

## Heartbeat

The dashboard and runtime store update a structured heartbeat with fields such as:

- `updated_utc`
- `last_check_utc`
- `last_alert_utc`
- `last_summary`
- `cycle_count`
- `source_count`
- `model`
- `status`
- `revision`
- `overall_score`
- `overall_label`

## Operating modes

- `market_hours`: runs hourly during the configured pre-open and market session window.
- `always_on`: 24/7 mode that keeps checking on the same hourly cadence.

## Briefing scale

The dashboard uses a six-class horizon scale that focuses on whether the story could matter over the next week or month:

- `1` = Strong positive
- `2` = Okay
- `3` = Beware / short-term hype
- `4` = Mixed / watch
- `5` = Concerning over weeks
- `6` = Likely bad within weeks

The page shows one tab per symbol with the strongest headlines, a short human-readable summary, and a plain-English note about whether the item looks routine, hype-driven, or genuinely concerning.

## Safety

- Alerts only.
- No auto-sell logic.
- No brokerage integration.
- Safe internal state writes are auto-approved by the loop policy.
- Out-of-scope or destructive actions are blocked.
