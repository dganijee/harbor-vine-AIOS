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
- **Hard rules:** Sees no commission data at all per intake's "no payroll/financials" framing. Commissions tab hidden via visible_tabs; `/api/commissions` returns 403. (Atlas finding #2, 2026-06-16.)

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

## Auth posture (this build — client-build-grade, post-Atlas patches)

- **Auth enabled.** `config.json → auth.enabled = true`. `templates/backend/auth.flask_middleware(app)` is mounted at server boot and gates every route except `/login`, `/api/login`, `/logout`, `/brand.css`, `/static/*`, `/manifest.json`, `/icon-*.png`.
- **Password hashing:** argon2id with OWASP minimum params (`$argon2id$v=19$m=19456,t=2,p=1`). Salt embedded in the hash format; transparent rehash via `PasswordHasher.check_needs_rehash()` on every successful login.
- **Authority gate (Atlas finding #1 fix, 2026-06-16):** the effective role at every request is derived server-side from `session['authenticated_username']` → `data/users.json` lookup. `/api/role_switch` is owner-only and may only *narrow* the effective role (preview). Non-owner authenticated callers get 403 from `/api/role_switch`. **No client-settable session field controls authority.**
- **CSRF (Atlas finding #5 fix, 2026-06-16):** session-anchored double-submit cookie. Token format `<sha256(aios_token)[:32]>.<nonce>.<hmac>`. A CSRF token from one session cannot be reused after re-login.
- **Login rate limit (Atlas finding #4 fix, 2026-06-16):** in-process per-IP, max 5 failures / 15 min → 429 + `Retry-After`. Backed by SQLite `login_attempts` table.
- **Cookie hardening (Atlas finding #3 fix, 2026-06-16):** `aios_token` is `httponly=True` always; `csrf_token` is `httponly=False` (JS must read it). Both default `samesite=Lax`. `Secure` flag env-gated via `AIOS_SECURE_COOKIES`, `request.is_secure` (TLS), or `data/config.json → cookies.secure`. Sandbox loopback default is `secure=false` so HTTP works.

### Sandbox test credentials (DOCUMENTED, not secret)

Keyed by role: `password_owner`, `password_president`, `password_accounting`, `password_tc`, `password_agent`. Seeded by `engine/init_passwords.py` on first run. Production builds run `engine/init_passwords.py --interactive` to set real passwords per user.
