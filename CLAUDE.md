# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Russian-language async Telegram bot suite ("FindirExpress" / "Findir") that does financial reporting for
Wildberries (WB) marketplace sellers: pulls sales/orders/storage/marketing/acceptance data from WB's seller
APIs, computes P&L, sends weekly/monthly reports, manages subscriptions/invoicing/closing documents through
the Tochka Bank API, and provides admin/support tooling — all over Telegram via `aiogram` 3.x.

There are three separate Telegram bots run from the same process:
- **main bot** (`app/main_bot`) — end users (sellers) register companies, view reports, manage price control,
  subscriptions, referrals.
- **admin bot** (`app/admin`) — internal operations/admin tooling.
- **support bot** (`app/support`) — support ticket handling.

## Running

- Entry point: `python main.py` (starts all three bots' polling loops concurrently via `asyncio.gather`, plus
  the APScheduler instance from `app/scheduler.py`).
- Deployed as a systemd service on Linux (see `findirexpress.service`); on the dev machine (Windows) it's run
  directly from the `.venv`.
- Config/secrets are loaded from `.env` (via `python-dotenv`, copy `.env.example` to `.env` and fill in real
  values) — `TOKEN`, `ADMINBOTTOKEN`, `SUPPORTBOTTOKEN`, `wb_api_token`, `DBURL` (async Postgres URL for
  SQLAlchemy), `yandex_password`, `ADMIN_ID`, optional `PROXY_URL`, plus the Tochka Bank credentials below.
  `config.py` at the repo root only holds non-secret constants (WB API endpoints, Tochka Bank endpoints, file
  paths) and reads all secrets via `os.getenv(...)` — never hardcode a credential back into `config.py`.
- **Tochka Bank integration (invoices/closing documents) is optional and off by default.** It's driven by
  `JWTTOKEN`, `BANK_ACCOUNT_ID`, `BANK_CUSTOMER_CODE`, `COMPANY_INN`, `BANK_CLIENT_ID` in `.env`. If
  `JWTTOKEN` is empty, every function in `app/payments/bank.py` short-circuits via `_bank_integration_disabled()`
  and logs instead of calling the bank API — this is intentional (the project isn't currently monetized), not
  a bug. The related scheduler jobs (`check_invoices_status`, `subscriptions_revenue_recognition`) are
  commented out in `app/scheduler.py` for the same reason; re-enable both the env vars and those jobs together
  if billing comes back.
- Dependencies are pinned in `requirements.txt` (`pip install -r requirements.txt`).
- No test framework is configured and no linter/formatter config is present in the repo.

## Architecture

### Layering convention
Most business logic follows a **thin handler → domain function → DB helper** layering:
- `app/main_bot/handlers.py` (and the other bots' `*_handlers.py`) wire aiogram `Router`s, filter on
  `Command`/`F`/FSM state, and call into domain modules — they hold almost no logic themselves.
- Domain/business logic lives in per-feature packages under `app/` (see below).
- DB access goes through `app/database/requests.py`, `app/database/support_functions.py`,
  `app/database/dates_functions.py`, `app/database/api_functions.py`, and similar `*_functions.py` /
  `requests.py` modules — raw SQLAlchemy models live only in `app/database/models.py`.

### Feature packages under `app/`
- `main_bot/` — main bot: routers, keyboards, FSM `states.py` (aiogram `StatesGroup`), cost-of-sales flow.
- `admin/` — admin bot + admin-only reports/functions (system status, promo checks, restoring goods cost).
- `support/` — support bot + ticket handlers.
- `managers/` — "manager" sub-accounts: sellers can grant scoped access (api/cost/price_control) to other
  Telegram users via invite tokens (`Managers`, `Managers_tokens` models).
- `prices/` — WB price-control feature: reading/uploading price & discount changes to WB, an hourly
  `main_prices_check_function` job.
- `reports/` — weekly/monthly P&L report generation (`weekly_finreport.py`, `monthly_finreport.py`), tax
  report, dashboard/plots (matplotlib), report calc helpers.
- `get_data/` — all WB API pulls: orders, orders by nomenclature, stocks, storage costs, paid acceptance,
  marketing costs/campaign stats, supplies, barcodes, goods cards. Each is the data-fetch half of a
  fetch → validate → persist pipeline driven from `app/app_logic.py`. The sales (realization) report comes
  from WB's finance API (`get_data/wbrequests.py`, `finance-api.wildberries.ru/.../sales-reports/detailed`),
  whose camelCase/string-money rows are translated back to the old v5 snake_case shape that
  `sales_report_compilation.py` expects. A seller's WB API key must include the "Финансы" category, otherwise
  WB returns 403 and the seller gets no reports. WB periodically retires endpoints outright (404 "This method
  is deprecated", as with v1 stocks and v5 sales) — check `finbot_log.log` for those first when reports stop.
- `payments/` & `transactions/` — Tochka Bank integration: creating/checking invoices (`payments/invoices.py`),
  closing documents (`transactions/closing_documents.py`), revenue recognition
  (`transactions/transactions.py`).
- `subscriptions/`, `promocodes/`, `referrals/` — subscription lifecycle (trial/paid, status/date checks),
  promocode validation/usage, referral channel tracking.
- `database/` — SQLAlchemy models (`models.py`, async engine/session factory), request helpers, `classes/`
  (plain data classes like `Sales`, `Stock`, `Goods_cost_template` used to shape API/report data), and
  allocation logic (`check_allocation_functions.py`, `sales_report_compilation.py`) that reconciles
  storage/marketing/acceptance costs against the compiled sales report.
- `data_clerance/` — DB cleanup/deletion utilities.

### Orchestration primitives (`app/`)
- `app_logic.py` — the core scheduled pipeline. `main_regular_reporting_function` (run every few hours by
  the scheduler) fans out over all active sellers, staggering start times, bounded by `semaphore.py`
  (`asyncio.Semaphore(15)`), and using `locks.py`'s `per_seller_lock` decorator to prevent concurrent runs for
  the same seller. Per seller it: checks stocks are fresh → downloads support data (orders, storage, paid
  acceptance, marketing) → downloads the sales/finance report (paginated via `rrdid`, retried up to 15 times)
  → validates barcodes (blocks the seller on mismatch) → allocates marketing/storage/acceptance costs onto
  the compiled sales rows → computes weekly/monthly P&L and sends reports when due. A module-level `Counters`
  object (`counter`) accumulates run stats used for the admin summary message.
- `wrappers.py` — `@with_session` injects a DB session into a function (reusing a passed-in session if the
  signature/args already carry one, else opening a new one via `database/asyncontext.py`'s `db_session()`);
  `@log_and_notify_admin` wraps a function so any exception is logged and DMed to the admin instead of
  crashing the caller. These two decorators are layered on nearly every domain function — read them before
  touching call signatures, since `with_session` inspects the wrapped function's signature to decide where to
  inject `session`.
- `locks.py` — `per_seller_lock(seller_id_param=..., timeout=...)`: keyed `asyncio.Lock` per seller id, with a
  manager lock guarding the lock dict itself; times out and notifies the admin rather than deadlocking.
- `scheduler.py` — all cron-style jobs (APScheduler, `AsyncIOScheduler`) are declared and registered here.
  Many are duplicated across staggered hourly triggers (e.g. `main_prices_check_function_trigger_1..24`)
  because APScheduler's `CronTrigger` is used with fixed hour/minute rather than an interval trigger — when
  adding an hourly job, follow the same one-trigger-per-hour pattern already in the file. Several jobs are
  commented out; check before assuming a pipeline stage is actually wired up.
- `database/apirequests.py` — `ApiClient`, the shared aiohttp wrapper for all outbound WB API calls: retries
  via `tenacity` with custom handling for WB's 429 (rate limit, honors `Retry-After`/`X-Ratelimit-*` headers)
  and 401 (marks the seller's API key unauthorized in the DB via `unauthorised_api_identified`). New WB API
  integrations should go through this client rather than calling `aiohttp`/`requests` directly.
- `logger.py` — `setup_logging()` truncates `finbot_log.log` on every process start and splits output into
  `info.log` (INFO only, daily-rotated, 14-day retention) and `finbot_log.log` (WARNING+, same rotation); no
  console handler is attached, so `print()` output and log output land in different places.
- `dates.py` — the shared vocabulary of "reporting period" boundaries (`start_of_Reporting_Week_func`,
  `end_of_Reporting_Month_func`, `start_for_downloading_data_func`, etc.) used throughout `app_logic.py` and
  `reports/`. Any change to reporting-period semantics belongs here, not re-derived in callers.

### Data flow shape
WB API → `get_data/*` (fetch) → `database/*` (validate + persist, dedup via `UniqueConstraint`s on the
models) → `database/sales_report_compilation.py` + `check_allocation_functions.py` (reconcile costs onto the
sales report) → `reports/*` (compute P&L, render, send via Telegram) → `database/support_functions.py`
(mark report-sent dates so the scheduler doesn't resend).

## Conventions to know
- Log/user-facing strings and comments are in Russian; keep new ones consistent with that unless told
  otherwise.
- Money/report-affecting functions almost always wrap their body in `try/except` and, on failure, both
  `logging.exception(...)` **and** DM the admin via `send_message_to_admin` (`app/admin/admin_message.py`) —
  match this pattern for anything in the reporting/payment pipeline rather than letting exceptions propagate
  silently into the scheduler.
- SQLAlchemy models rely heavily on composite `UniqueConstraint`s as the idempotency mechanism for repeated
  WB API pulls (e.g. `Orders`, `Supplies`, `Storage_costs`, `Marketing_costs_by_SKU`) — when adding a new
  ingested dataset, add a matching unique constraint rather than de-duplicating in Python.
