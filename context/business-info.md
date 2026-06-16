# Harbor & Vine Realty — Business Context
**Last updated:** 2026-06-16

---

## Company
- **Name:** Harbor & Vine Realty (HarborVine)
- **Industry:** Residential real estate brokerage (luxury + mid-market)
- **Primary Contact:** Marisol Trent, Broker-Owner
- **Website:** https://www.theagencyre.com

---

## What You Do
Harbor & Vine is a 6-person boutique residential brokerage handling luxury and mid-market homes across a coastal metro. The firm runs about 30 active listings and 20-30 deals in pipeline at any time. **We are a brokerage, not a property manager** — our work is transactions (listings, showings, deals, closings, commissions), not tenant management or building maintenance.

The broker-owner wants one place to see deal health, doc status, and commissions instead of five spreadsheets and an inbox.

---

## Key Personnel

| Name | Role | RBAC scope | Comms |
|------|------|------------|-------|
| Marisol Trent   | Broker-Owner          | full                                                | Dashboard + Telegram brief 8:00 AM |
| Devin Okafor    | Managing Broker       | near-full, NO payroll / commission internals        | Dashboard + Telegram brief        |
| Carol Benitez   | Bookkeeper / Accounting | Commissions + QBO only, NO leads / docs           | Dashboard only                    |
| Priya Raman     | Transaction Coordinator | Documents + Calendar + Pipeline, NO commissions   | Dashboard only                    |
| Jess Holloway   | Agent                 | Own deals + own clients + own showings              | Dashboard + Telegram              |
| Tomás Vidal     | Agent                 | Own deals + own clients + own showings              | Dashboard + Telegram              |

---

## Tech Stack
- AI Operating System (AIOS) — deployed 2026-06-16
- Dashboard: `http://127.0.0.1:8001` (sandbox)
- Data sync: hourly via `engine/sync_engine.py`; brokerage automations cron every 15 min for notifications + 7:30 AM for the morning brief

---

## Active Integrations (sandbox)
All four are wired but **inactive** for the sandbox build. Offline branch reads from `fixtures/` so the dashboard is non-blank.

| Connector       | Status   | Backs                            |
|-----------------|----------|----------------------------------|
| gmail           | inactive | leads + doc requests + escrow comms |
| google_calendar | inactive | showings + closings + listing appts |
| google_sheets   | inactive | pipeline (deals + status)        |
| qbo             | inactive | commission splits + reconciliation |

---

## Key Metrics (broker-owner cares about these)
- `active_listings` — count of listings currently on market
- `pipeline_volume_usd` — total $ in flight across all open deals
- `avg_days_on_market` — average DOM across active listings
- `closings_this_month` — number of deals that closed this month
- `commission_earned_mtd` — month-to-date commissions
- `new_leads_this_week` — leads added in trailing 7 days
- `showings_scheduled_7d` — showings booked in next 7 days

---

## Pain Points → Module Wiring

| Pain | Module / surface |
|---|---|
| Transaction docs scattered across email; no single source of truth per deal | `document_classification`, Documents tab |
| Commission splits tracked by hand; agents dispute the math | `approval_workflow`, `payment_history`, Commissions tab, commission_dispute_monitor automation |
| Showings double-booked; calendar is chaos | `anomaly_detection`, Showings tab, showing_conflict_monitor automation |
| Lead follow-up falls through; warm leads go cold | `daily_snapshot`, `notifications`, Leads tab, lead_followup_monitor automation |
| Broker-owner has zero day-to-day visibility into pipeline health | `exec_report`, Overview tab, morning Telegram brief, stalled_deal_monitor automation |
