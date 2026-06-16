# AIOS Operations Template — Reference Bundle (sanitized)

This is the **canonical module/scaffold source** that `scripts/aios_deploy.py` clones
via `AIOS_TEMPLATE_DIR`. It was extracted from a real shipped operations build and
**fully sanitized** — no client name, no employee PII, no `.env`, no credentials, no
databases, no logs. All client-specific values are `PLACEHOLDERS`.

## How to wire it in
1. Unpack to a stable path you control, e.g. `data/fellowship_automation_consulting/reference_bundle/AIOS-Operations-Template`.
2. Repoint `AIOS_TEMPLATE_DIR` in `aios_deploy.py` to that path. (As-shipped it points at a
   Desktop path that no longer exists — repointing here fixes the `FileNotFoundError`.)
3. Run a scaffold: `python scripts/aios_deploy.py "Test Co" --url https://example.com --vertical services --output ./TestCo-AIOS`.

## What's inside (the module pattern you asked about)
- `automations/` — the **modules**. Each is a thin `run()` script (e.g. `sales_anomaly.py`,
  `labor_efficiency.py`, `morning_brief.py`) that calls an engine, formats a report, fires an
  alert, returns a summary dict. This is the unit the scheduler/cron invokes.
- `engine/` — domain logic the modules call (`alert_engine.py` is reusable; `*_engine.py` are
  vertical-specific — the example vertical here is **car-wash operations**, swap per client).
- `tools/connectors/` — connector implementations (Snowflake, NetSuite, QuickBooks, Outlook,
  Teams, Dropbox, dashboard). All read creds from env — none are embedded.
- `outputs/dashboard.html` — the single-page dashboard (Chart.js, CSS-variable branding).
- `scripts/server.py` — Flask app: serves the dashboard + JSON endpoints per module.
- `deploy/` — Caddy (auto-TLS) + systemd + setup.sh hardening recipe.
- `context/`, `soul/`, `memory/`, `data/users.json`, `data/stores.json` — per-client context as
  `PLACEHOLDER` templates. Fill from the 9-field intake.

## Placeholders to fill per build
`Harbor & Vine Realty`, `HarborVine`, `Marisol Trent`, `real-estate`, `Marisol Trent`,
`Devin Okafor`, `Carol Benitez`, `Jess Holloway`, `gmail, google_calendar, google_sheets, qbo`,
`active_listings, pipeline_volume_usd, avg_days_on_market, closings_this_month, commission_earned_mtd, new_leads_this_week, showings_scheduled_7d`, `Transaction docs scattered across email; commission splits tracked by hand and disputed; showings double-booked; lead follow-up falls through; broker-owner has zero day-to-day visibility into pipeline health.`, `https://www.theagencyre.com`, `deals, pipeline, commissions, leads, calendar`.

## Module toggling
`data/thresholds.json` + the dashboard read which modules are active. In the main scaffold the
canonical toggle manifest is `templates/config/modules.json` (boolean per module → dashboard
shows/hides the tab). Copy whole, gate at runtime — no per-module pruning.
