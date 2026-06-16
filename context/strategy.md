# Harbor & Vine Realty — Strategy
**Last updated:** 2026-06-16

---

## Current Priorities
1. **Pipeline visibility for the broker-owner** — Marisol's primary ask. The Overview tab + morning Telegram brief is the daily handle.
2. **Commission clarity** — eliminate the spreadsheet disputes (pain point #2). QBO sync + Commissions tab + commission_dispute_monitor surface every disputed row as a task.
3. **Showings calendar without conflicts** — anomaly_detection on overlapping showings (pain point #3) flagged in the Alerts panel + a dedicated automation.
4. **Lead recovery** — lead_followup_monitor flags any lead untouched for 5+ days (pain point #4).
5. **Doc consolidation per deal** — Documents tab + document_classification cuts the email-archeology problem (pain point #1).

---

## KPIs We Optimize Against
- `active_listings` — wire to fixture, target visibility for Marisol + Devin
- `pipeline_volume_usd` — total $ across all open deals
- `avg_days_on_market` — listings discipline; >90d triggers a MED alert
- `closings_this_month` — month-to-date count
- `commission_earned_mtd` — month-to-date dollars
- `new_leads_this_week` — top-of-funnel pacing
- `showings_scheduled_7d` — next-7-day showings volume

---

## Alert Thresholds (from `data/thresholds.json`)
- Stalled deals: MED at 7 days in escrow/pending, HIGH at 14 days
- Showing conflict: any 30-minute window overlap → HIGH
- Commission dispute: any row `status='disputed'` → HIGH
- Lead follow-up: 5+ days since last contact → MED
- Listing DOM: > 90 days → MED

---

## Active Modules (sandbox build, 14 active)
| Module | State |
|---|---|
| pipeline | ACTIVE |
| alerts | ACTIVE |
| chat_widget | ACTIVE |
| exec_report | ACTIVE |
| payment_history | ACTIVE (commissions) |
| notifications | ACTIVE |
| anomaly_detection | ACTIVE (showing conflicts) |
| approval_workflow | ACTIVE (commissions) |
| document_classification | ACTIVE |
| daily_snapshot | ACTIVE |
| admin_panel | ACTIVE |
| data_export | ACTIVE |
| role_based_access | ACTIVE |
| exception_audit | ACTIVE |
| bounce_report | inactive |
| employee_onboarding | inactive |
| invoice_intake | inactive |
| labor_revenue | inactive |
| event_pnl | inactive |
| multi_location | inactive |

---

## Automation Schedule
- **Morning brief:** 7:30 AM Telegram digest to owner + president (`automations/morning_brief.py`)
- **Stalled deal monitor:** every 1 hour (`automations/stalled_deal_monitor.py`)
- **Showing conflict monitor:** every 15 min (`automations/showing_conflict_monitor.py`)
- **Commission dispute monitor:** every 1 hour (`automations/commission_dispute_monitor.py`)
- **Lead follow-up monitor:** every 4 hours (`automations/lead_followup_monitor.py`)
- **Meeting brief:** triggered (`automations/meeting_brief.py`)

---

## Sandbox Constraints
- All connectors `active: false`. Offline branch via `fixtures/`.
- Server binds 127.0.0.1:8001 only. No public port.
- Telegram sends stubbed to log line. No real outbound.
- No real PII anywhere. `theagencyre.com` is brand-extraction target only, not a represented client.
- Phase F (deploy) gated; no `deploy_aios.sh` execution.

## Security Posture (client-build-grade, 2026-06-16)
- **Authentication enabled.** `templates/backend/auth.flask_middleware()` gates every route except `/login`, `/api/login`, `/logout`, `/brand.css`, `/static/*`. Passwords are sha256(salt + password) — see `data/users.json`. Session tokens are HMAC-SHA256-signed JWT-like payloads.
- **CSRF enforced** on every state-changing endpoint via double-submit cookie pattern (X-CSRF-Token header echoes `csrf_token` cookie; both signed with `FLASK_SECRET_KEY`).
- **`FLASK_SECRET_KEY` fails closed.** Server refuses to boot if the env var is missing; `scripts/startup.py` bootstraps `.env` on first run.
- **Connector credentials encrypted at rest** via Fernet with the `enc::v1:` tag prefix. Master key in `AIOS_MASTER_KEY` (Fernet-generated, `.env`-persisted, gitignored); per-build derived key uses PBKDF2-HMAC-SHA256(100,000 iters) salted with `aios-build-harbor-vine`. Encryption migration `engine/encrypt_config.py` has RUN against `data/connectors.json` — `grep "enc::"` returns > 0.
