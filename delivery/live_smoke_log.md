# Live HTTP smoke — post-Atlas patch round (commit 57b4f14)

All 8 checks PASS. Verified by Felix during the patch round; reproducible by cloning the repo and running `python scripts/startup.py`.

| # | Check | Verifies | Result |
|---|---|---|---|
| 1 | Jess (agent) POST `/api/role_switch` with `{"role":"owner"}` + valid CSRF | Atlas Finding #1 — privilege escalation | **403** (was 200) |
| 2 | Jess GET `/api/commissions` | Atlas Finding #1 — RBAC narrowing | **403** |
| 3 | Devin (president) GET `/api/commissions` | Atlas Finding #2 — president RBAC drift | **403** |
| 4 | Devin GET `/api/leads` | Atlas Finding #2 — regression check (president still has leads) | **200** |
| 5 | `Set-Cookie` headers contain `SameSite=Lax`; `Secure` present when `AIOS_SECURE_COOKIES=1` is set | Atlas Finding #3 — cookie hardening | **PASS** |
| 6 | 6th failed login from same IP within 15s | Atlas Finding #4 — login rate limit | **429 + Retry-After** |
| 7 | Marisol's `csrf_token` cookie used in Jess's authed session | Atlas Finding #5 — CSRF session binding | **403** (session mismatch) |
| 8 | Owner-preview of agent role narrows scope correctly (owner-preview hits `/api/commissions` -> 403 because preview's `_role_can` is subset of agent's, and agent has no commissions) | Atlas Finding #1 corollary — preview must strictly narrow | **403** |

`aios_qa.py`: **43/47** pass. The 4 residual failures are bundle-harness defects (the canonical `aios_qa.py:424-441` module_file_map has no entries for `admin_panel`/`data_export`/`role_based_access`, and its `Passwords hashed` check hardcodes a `sha256:` prefix that argon2 hashes correctly do not have). Implementations exist; harness map is incomplete. Per Sentinel rule 16, the bundle is immutable from our side.

## Code paths to verify against
- `scripts/server.py` — `_current_role()` derives from `session['authenticated_username']`; `/api/role_switch` owner-only + strict-narrowing.
- `templates/backend/auth.py` — argon2id `PasswordHasher` with explicit OWASP params; `_cookie_secure()` helper; samesite=Lax + httponly on `aios_token`.
- `templates/backend/csrf.py` — token format `<sha256(aios_token)[:32]>.<nonce>.<hmac>`; bound to session anchor.
- `templates/backend/rate_limit.py` — `LoginRateLimiter` over SQLite `login_attempts` table.
- `data/users.json` — Devin Okafor `visible_tabs` no longer includes "Commissions"; `_security_note` updated to client-build-grade.

## Standing rules added during the patch round
**Felix** (`agents/felix/IDENTITY.md`): rules 35-39 — never use client-settable session field as authority gate; cross-reference peer rules; cookie defaults; rate-limit-from-day-1; CSRF binds to session.

**Sentinel** (`agents/sentinel/IDENTITY.md`): rules 57-59 — attack the authority path during RBAC audits; cross-reference peer agents' standing rules; structured elevation-test result required in audit return.
