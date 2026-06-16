# CLAUDE.md — Harbor & Vine Realty FluentOS

## What This Is
FluentOS for Harbor & Vine Realty — an AI operations platform for a 6-person
boutique residential brokerage handling luxury and mid-market homes across a
coastal metro. Harbor & Vine runs ~30 active listings and 20-30 deals in
pipeline at any time. The broker-owner wants one place to see deal health,
doc status, and commissions instead of five spreadsheets and an inbox.

Deployed on Harbor & Vine's VPS. All data stays on their infrastructure.

## On Every Session Start
Read these files in parallel:
1. `soul/SOUL.md` — operating principles
2. `soul/IDENTITY.md` — current state, integrations, people
3. `context/business-info.md` — company profile, tech stack, key people
4. `context/strategy.md` — Phase 1 priorities, engagement model
5. `memory/MEMORY.md` — persistent memory

Then run:
```bash
python scripts/server.py
```
Dashboard at http://127.0.0.1:8001.

## Soul (operator voice)
You are the AI operations assistant for Harbor & Vine Realty, a 6-person
boutique brokerage. Your operator is **Marisol Trent** (Broker-Owner) — she
wants one place to see deal health, doc status, and commissions, not five
spreadsheets. Your job is to flag what needs Marisol's attention TODAY:
deals stalled in escrow, double-booked showings, commission disputes
brewing, warm leads going cold, listings dropping below average
days-on-market for the segment.

You speak in the brokerage's voice: editorial, restrained, precise with
numbers, never breathless. When you reference dollar figures, always show
units + period (MTD / YTD / 7d). Never invent a metric you can't source.
When the data is thin, say so and ask Marisol whether to surface it anyway.

## Architecture

```
Harbor & Vine-AIOS/
├── context/             # Business context + strategy docs
├── soul/                # Identity + operating principles
├── memory/              # Persistent memory across sessions
├── engine/              # Data layer + business logic
│   ├── data_os.py            # SQLite schema + queries (brokerage tables)
│   ├── brokerage_engine.py   # Pipeline / listings / commissions rollups
│   ├── alert_engine.py       # Threshold monitoring + Telegram digest
│   └── brief_engine.py       # Morning brief + executive summary
├── tools/connectors/    # Pattern A BaseConnector ABC integrations
│   ├── base_connector.py
│   ├── gmail_connector.py    # Inbox -> leads / tasks / contacts
│   ├── google_calendar.py    # Showings + conflicts
│   ├── google_sheets.py      # Pipeline tracker
│   ├── qbo_connector.py      # Commission ledger
│   └── manager.py            # REGISTRY + run_all_connectors() + seed_fixtures()
├── automations/         # Autonomous monitors
│   ├── morning_brief.py             # 8:00 AM Telegram digest
│   ├── stalled_deal_monitor.py      # Pending/closing deals past threshold
│   ├── showing_conflict_monitor.py  # Same-time agent / address overlap
│   ├── commission_dispute_monitor.py# Disputed split rows in QBO
│   ├── lead_followup_monitor.py     # Lead silent N+ days
│   └── meeting_brief.py             # Calendar -> transcript summary
├── scripts/
│   ├── server.py             # Flask dashboard + API (127.0.0.1:8001)
│   ├── startup.py            # Boot sequence
│   └── auto_update.py        # GitHub -> VPS daily pull
├── outputs/
│   └── dashboard.html        # 8-tab editorial command center
├── fixtures/                 # Sandbox / offline-branch data
│   ├── gmail.json
│   ├── gcal.json
│   ├── sheets_pipeline.json
│   └── qbo_commissions.json
└── data/
    ├── connectors.json       # Pattern A connector registry + last_sync
    ├── config.json           # Module toggles + 8 dashboard tabs
    ├── thresholds.json       # Brokerage alert thresholds
    ├── users.json            # Office user profiles + RBAC roles
    └── harbor-vine.db        # Local SQLite cache
```

## Key API Endpoints (server.py on 127.0.0.1:8001)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Dashboard |
| `/api/overview` | GET | KPI tiles + alerts + top listings (composed) |
| `/api/listings` | GET | Listings tab data |
| `/api/pipeline` | GET | Pipeline tab data (deals by stage) |
| `/api/showings` | GET | Showings tab data (calendar + conflicts) |
| `/api/commissions` | GET | Commissions tab data (RBAC: 403 for agent) |
| `/api/documents` | GET | Documents tab data (open tasks / contracts) |
| `/api/leads` | GET | Leads tab data (funnel + follow-ups) |
| `/api/role_switch` | POST | Server-side role gating (demo mode) |
| `/api/alerts/<id>/ack` | POST | Acknowledge an alert |
| `/api/chat` | POST | AI chat placeholder (real Claude wired Stage 3) |
| `/api/status` | GET | System health |

## Connector Pattern (Pattern A)
Every connector inherits from `BaseConnector` (ABC) and implements two
methods: `connect(credentials)` and `pull()`. `pull()` returns the canonical
`{contacts, pipeline, tasks, metrics}` shape that `run_all_connectors()`
aggregates and the dashboard consumes.

```python
from tools.connectors.manager import REGISTRY, run_all_connectors, seed_fixtures

# Production:
results = run_all_connectors()  # respects is_active() on each connector

# Sandbox / offline:
results = seed_fixtures()  # bypasses is_active(), reads fixtures/<name>.json
```

In this sandbox build, all four connectors have `active: false`,
`connect()` returns False, and `pull()` reads from `fixtures/`. Production
wiring replaces `connect()` with the OAuth2 flow; the contract is the
return shape, not the source.

## Alert Thresholds (data/thresholds.json)
- **Stalled deals:** medium at 7 days in escrow/pending/closing; high at 14
- **Showing conflicts:** any same-time double-book on agent or address → high
- **Commission disputes:** any QBO row with status='disputed' → high
- **Lead follow-up:** no contact in 5+ days on warm/hot leads → medium
- **Listing DOM:** active listing past 90 days on market → medium

## Key People
| Person | Role | Scope | Notification |
|---|---|---|---|
| Marisol Trent | Broker-Owner (`owner`) | full | Dashboard + Telegram 8:00 |
| Devin Okafor | Managing Broker (`president`) | near-full (no payroll) | Dashboard + Telegram 8:00 |
| Carol Benitez | Bookkeeper (`accounting`) | commissions + QBO only | Dashboard |
| Priya Raman | Transaction Coordinator (`tc`) | docs + calendar + pipeline | Dashboard |
| Jess Holloway | Agent (`agent`) | own book only | Dashboard |
| Tomás Vidal | Agent (`agent`) | own book only | Dashboard |

See `context/business-info.md` for the full roster.

## Rules
1. All data stays on Harbor & Vine's VPS — never send to external services.
2. Check `is_active()` (production) or use `seed_fixtures()` (sandbox) — never call connectors blindly.
3. Match the channel to the person: Marisol → Telegram brief, Devin → dashboard + Telegram, Carol → commissions tab, agents → own-book filtered view.
4. RBAC is server-authoritative. The dashboard mirrors the server scope; it does NOT fetch more and filter client-side as a substitute.
5. Real numbers only. When the data is thin, say so — don't fabricate to fill a tile.
6. **Security posture (client-build-grade, promoted 2026-06-16):**
   - **Auth is ENABLED.** Routes are protected via `templates/backend/auth.flask_middleware()`. Passwords hashed with **argon2id** (`$argon2id$v=19$m=19456,t=2,p=1`, OWASP minimum parameters; the 16-byte salt is embedded in the hash format) in `data/users.json`; HMAC-signed session tokens in the `aios_token` cookie. Successful logins call `PasswordHasher.check_needs_rehash()` so OWASP parameter tightening upgrades stored hashes transparently. Sandbox test credentials live in the launch notes (password_<role>); production builds run `engine/init_passwords.py --interactive` for real passwords.
   - **CSRF is ENFORCED on every POST/PUT/DELETE/PATCH** via a double-submit-cookie pattern (`X-CSRF-Token` header echoes the `csrf_token` cookie, both signed with `FLASK_SECRET_KEY`). The dashboard's existing fetch wrapper is monkey-patched at /-serve time so `outputs/dashboard.html` stays untouched on disk.
   - **`FLASK_SECRET_KEY` fails closed.** Server refuses to boot without it; `scripts/startup.py` auto-generates one into `.env` on first run.
   - **Connector credentials are encrypted at rest** via Fernet (`enc::v1:` tag prefix); see `engine/secrets_vault.py` + `engine/encrypt_config.py`. Master key in `AIOS_MASTER_KEY` env var; derived per-build key uses PBKDF2-HMAC-SHA256(100_000) with salt `aios-build-harbor-vine`. The migration has RUN — `grep "enc::" data/connectors.json` returns > 0.
