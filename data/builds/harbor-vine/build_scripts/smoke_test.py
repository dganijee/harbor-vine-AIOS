"""
Felix client-grade promotion smoke test.

Verifies:
- Rule 1: auth gate on protected routes (anonymous GET / -> redirect to /login)
- Rule 3: FLASK_SECRET_KEY fail-closed (server refused to boot without it
  in a separate subprocess test)
- Rule 16: /api/chat max-length (5000 chars -> 400; 5 chars -> 200)
- Rule 56: enc:: count > 0
- Login flow: POST /api/login with test creds -> 200 + cookie
- CSRF: POST /api/role_switch without X-CSRF-Token -> 403; with -> 200
- Authed GET / -> 200
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\dgani\Desktop\harbor-vine-AIOS")
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Ensure FLASK_SECRET_KEY is in env BEFORE importing server
assert os.environ.get("FLASK_SECRET_KEY"), \
    "FLASK_SECRET_KEY missing; run scripts/startup.py first"

from scripts.server import app

results = {}


def _t(name, ok, detail=""):
    results[name] = {"pass": bool(ok), "detail": detail}
    icon = "+" if ok else "X"
    print(f"  [{icon}] {name} — {detail}")


with app.test_client() as c:
    # ── Rule 1: protected route requires auth ─────────────────────
    r = c.get("/", headers={"Accept": "text/html"})
    _t("rule1_get_root_anonymous_redirects",
       r.status_code in (302, 401),
       f"HTTP {r.status_code}, Location={r.headers.get('Location')}")

    r = c.get("/api/overview")
    _t("rule1_api_endpoint_anonymous_blocked",
       r.status_code == 401,
       f"HTTP {r.status_code}")

    def _cookies():
        out = {}
        try:
            for k, v in c._cookies.items():
                # k is (domain, path, name) tuple in newer Flask test client.
                if isinstance(k, tuple) and len(k) == 3:
                    out[k[2]] = v.value
                else:
                    out[k] = v.value
        except AttributeError:
            jar = getattr(c, 'cookie_jar', None) or []
            for cc in jar:
                out[cc.name] = cc.value
        return out

    # ── Login ────────────────────────────────────────────────────
    r = c.post("/api/login",
               json={"username": "Marisol Trent",
                     "password": "password_owner"})
    login_ok = r.status_code == 200 and "aios_token" in _cookies()
    _t("login_with_test_creds_succeeds",
       login_ok,
       f"HTTP {r.status_code}, cookies={list(_cookies().keys())}")

    # Login with bad password
    r2 = c.post("/api/login",
                json={"username": "Marisol Trent",
                      "password": "wrong"})
    _t("login_with_bad_password_fails",
       r2.status_code == 401,
       f"HTTP {r2.status_code}")

    # ── After login, GET / should succeed ────────────────────────
    r = c.get("/", headers={"Accept": "text/html"})
    _t("authed_get_root_returns_200",
       r.status_code == 200,
       f"HTTP {r.status_code}, body len={len(r.data)}")

    # CSRF cookie should be set after a GET
    csrf_value = _cookies().get("csrf_token", "")
    has_csrf = bool(csrf_value)
    _t("csrf_cookie_set_after_get",
       has_csrf,
       f"cookie={'present' if has_csrf else 'missing'}")

    # ── CSRF: POST without token blocked ─────────────────────────
    r = c.post("/api/role_switch", json={"role": "owner"})
    _t("csrf_blocks_post_without_token",
       r.status_code == 403,
       f"HTTP {r.status_code}, body={r.get_json()}")

    # ── CSRF: POST with valid token succeeds ─────────────────────
    r = c.post("/api/role_switch",
               json={"role": "owner"},
               headers={"X-CSRF-Token": csrf_value})
    _t("csrf_allows_post_with_valid_token",
       r.status_code == 200,
       f"HTTP {r.status_code}")

    # ── Rule 16: chat max-length ─────────────────────────────────
    r = c.post("/api/chat",
               json={"message": "hello"},
               headers={"X-CSRF-Token": csrf_value})
    _t("rule16_chat_short_message_ok",
       r.status_code == 200,
       f"HTTP {r.status_code}")

    long_msg = "x" * 5000
    r = c.post("/api/chat",
               json={"message": long_msg},
               headers={"X-CSRF-Token": csrf_value})
    _t("rule16_chat_long_message_rejected",
       r.status_code == 400,
       f"HTTP {r.status_code}, body={r.get_json()}")

    # ── RBAC: switch to accounting, hit /api/leads -> 403 ────────
    r = c.post("/api/role_switch",
               json={"role": "accounting"},
               headers={"X-CSRF-Token": csrf_value})
    assert r.status_code == 200, f"role_switch failed: {r.get_json()}"
    r = c.get("/api/leads")
    _t("rbac_accounting_blocked_from_leads",
       r.status_code == 403,
       f"HTTP {r.status_code}")

# ── Rule 56: enc:: count > 0 ──────────────────────────────────────
with open(ROOT / "data" / "connectors.json", "r", encoding="utf-8") as f:
    text = f.read()
enc_count = text.count("enc::")
_t("rule56_enc_count_gt_0",
   enc_count > 0,
   f"enc:: occurrences = {enc_count}")

# Print summary
passed = sum(1 for v in results.values() if v["pass"])
total = len(results)
print(f"\n{passed}/{total} smoke checks passed")
sys.exit(0 if passed == total else 1)
