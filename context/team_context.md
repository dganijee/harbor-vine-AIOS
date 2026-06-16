# Team Context (per-role briefing)

> Server-authoritative RBAC scope is in `data/users.json`. This file is the **prose context** the chat agent loads to behave correctly when each role is the active user. Read-only by the chat endpoint; never edit at runtime.

---

## Marisol Trent — Broker-Owner (`owner`)
- **Daily view:** Overview tab. Wants Pipeline Volume, Closings This Month, Commission MTD, and any alerts above the noise floor.
- **Tone preference:** restrained, executive. Lead with the number that matters most, then the why.
- **Notifications:** dashboard (always) + Telegram digest at 8:00 (`TELEGRAM_CHAT_ID_OWNER` in `.env`).
- **Hard rules:** never expose Carol's accounting internals. Show commission totals, not paycheck mechanics.

## Devin Okafor — Managing Broker (`president`)
- **Daily view:** Overview + Pipeline + Showings. Cares about agent performance + deal velocity + showings throughput.
- **Tone preference:** collaborative-peer to Marisol; more operational than executive.
- **Notifications:** dashboard + Telegram brief.
- **Hard rules:** can see commission TOTALS per agent, NOT split breakdowns or accounting entries. The server strips `split_pct` from `/api/commissions` for this role.

## Carol Benitez — Bookkeeper / Accounting (`accounting`)
- **Daily view:** Commissions tab. Surface: pending splits, QBO sync status, monthly reconciliation gaps.
- **Tone preference:** precise, accountant-cadence. No fluff.
- **Notifications:** dashboard only.
- **Hard rules:** sees commission internals; does NOT see lead lists, deal documents, or showings. `/api/leads` returns 403. `/api/documents` returns 403.

## Priya Raman — Transaction Coordinator (`tc`)
- **Daily view:** Documents tab. Surface: deals with missing docs, contract deadlines this week, showing conflicts to resolve.
- **Tone preference:** action-oriented; treats every doc gap as a punch-list item.
- **Notifications:** dashboard only (chat for ad-hoc).
- **Hard rules:** can edit doc statuses; cannot edit commissions; cannot view Carol's accounting tab. `/api/commissions` returns 403.

## Jess Holloway — Agent (`agent`)
- **Daily view:** Overview filtered to her book. Pipeline + Showings + Documents + Leads, all scoped to her name.
- **Tone preference:** peer-to-peer; help her win her next deal.
- **Notifications:** dashboard + Telegram (her own alerts only).
- **Hard rules:** cannot see Tomás's deals, cannot see Marisol's accounting tab, cannot see firm-wide pipeline volume. RBAC scoping enforced server-side via `agent_filter='Jess Holloway'` on every list endpoint; dashboard mirrors with client-side filtering.

## Tomás Vidal — Agent (`agent`)
- Same scope as Jess, with `agent_filter='Tomás Vidal'`.

---

## Cross-role rules
- **Demo role switcher:** Marisol (owner) can preview other roles. When switched, KPIs narrow to that role's allowed set by mirroring the server's scope map client-side (Iris standing rule #9 — never fetch more, always filter down). Real lower-role sessions stay server-authoritative; the demo preview never sees data the real role couldn't.
- **Server-side scope (RBAC):** every list/tab endpoint resolves the active role, looks the role up in `_role_can(role, resource)` and short-circuits 403 if the role is not allowed; for agent roles it additionally narrows results via `agent_filter` against the agent's name. The dashboard's `visible_tabs` is a UX hint, not the gate.

---

## Sandbox auth posture (this build)

This scaffold runs **with auth disabled** (`config.json` → `auth.enabled = false`) so the offline dashboard can be opened locally without a login screen. That means:

- **No `check_auth()` decorator is wired on any route in this sandbox.** Role is read from the Flask session and only drives RBAC *scoping* — not identity verification. Anyone with a session can call `/api/role_switch` and assume any role. This is intentional for the sandbox demo.
- **No `templates/backend/auth.py` ships in this sandbox.** That file is the production-only auth layer (sha256 password hash lookup against `data/users.json` + HMAC-signed session tokens, mounted via `flask_middleware(app)` at startup) referenced in the playbook's canonical scaffold. It will be added in a later wiring pass, not in this build.
- **`data/users.json` is the user roster** (name, role, visible_tabs). It is NOT a credential store in the sandbox — no password fields, no first-run setup flow. Production builds add a `password_hash` column populated on the user's first login.
- **First-run "set your own password" flow (Sentinel rule 41)** is a production-build requirement, not a sandbox one. It lives alongside `templates/backend/auth.py`.

When promoting this build to a real client environment:
1. Drop in `templates/backend/auth.py` from the playbook canonical scaffold.
2. Mount it at server startup: `from templates.backend.auth import flask_middleware; flask_middleware(app)`.
3. Flip `config.json → auth.enabled = true`.
4. Run the password-set flow for every user in `data/users.json`.
5. Verify that every protected endpoint short-circuits with a 401 when called without a token, and a 403 when called with a token whose role is not in `_role_can(role, resource)`.
