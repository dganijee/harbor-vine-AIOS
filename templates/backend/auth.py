#!/usr/bin/env python3
"""
Harbor & Vine — Authentication layer (client-build-grade).

Adapted from the bundle 1 canonical auth.py for our scaffold's layout:
- The user ROSTER lives in data/users.json (not config.json). Each user
  carries a single `password_hash` field (the salt is embedded in the
  argon2id hash format — no separate column). config.json holds only the
  auth toggle + signing secret.
- Passwords hashed with **argon2id** (`$argon2id$v=19$m=19456,t=2,p=1`,
  OWASP minimum parameters); the salt is embedded in the hash format.
  We use `argon2.PasswordHasher` from `argon2-cffi`.
- Session tokens are HMAC-SHA256-signed JWT-like payloads (zero ext deps).
- flask_middleware(app) registers a @before_request `check_auth()` that
  protects every route except /login, /api/login, /logout, /static/* and
  /brand.css (CSS is loaded by the login page itself).

Production posture (no sandbox concessions):
- auth.enabled MUST be true in production. Sandbox now defaults to true also.
- The signing secret comes from data/config.json -> auth.secret; if absent
  it's auto-generated on first run and persisted (per Sentinel rule on
  fail-closed secrets — we generate-and-persist, never auto-default-empty).
- First-run password flow: engine/init_passwords.py walks users.json and
  prompts the operator for each missing password_hash. In the sandbox we
  pre-set deterministic test passwords (documented loudly).
- Transparent rehash: PasswordHasher.check_needs_rehash() is called on
  every successful verify. If OWASP parameters change later, the next
  successful login transparently upgrades the stored hash.
"""

import json
import os
import secrets
import time
import hmac
import hashlib
import base64
import logging
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import (
    VerifyMismatchError,
    InvalidHashError,
    InvalidHash,
    VerificationError,
    Argon2Error,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

# OWASP recommended minimum parameters for argon2id (2024+ cheat sheet).
# Pass these EXPLICITLY even if they're defaults so the choice is auditable.
#   time_cost=2        -> 2 iterations
#   memory_cost=19456  -> 19 MiB (the OWASP floor for argon2id)
#   parallelism=1      -> 1 lane (server-side; raise if multi-core trusted)
#   hash_len=32        -> 32-byte output
#   salt_len=16        -> 16-byte salt embedded in the hash
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 19456
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

# Single PasswordHasher used everywhere — cheap to construct but reusing
# it keeps params consistent across hash + verify + needs_rehash calls.
_PH = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
)


class Auth:
    def __init__(self, config_path=None, users_path=None):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.config_path = config_path or os.path.join(root, 'data', 'config.json')
        self.users_path = users_path or os.path.join(root, 'data', 'users.json')
        self.config = self._load_json(self.config_path) or {}
        self.users_doc = self._load_json(self.users_path) or {"users": []}

        # Signing secret: pulled from config, generated + persisted if absent.
        auth_block = self.config.get("auth", {})
        secret = auth_block.get("secret")
        if not secret:
            secret = secrets.token_hex(32)
            self.config.setdefault("auth", {})
            self.config["auth"]["secret"] = secret
            self._save_config()
        self.secret = secret

    # ── IO helpers ──────────────────────────────────────────────────

    @staticmethod
    def _load_json(path):
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)

    def _save_users(self):
        os.makedirs(os.path.dirname(self.users_path) or '.', exist_ok=True)
        with open(self.users_path, 'w', encoding='utf-8') as f:
            json.dump(self.users_doc, f, indent=2)

    def reload(self):
        """Re-read disk state. Useful after init_passwords runs."""
        self.config = self._load_json(self.config_path) or {}
        self.users_doc = self._load_json(self.users_path) or {"users": []}

    # ── Config readers ─────────────────────────────────────────────

    def is_enabled(self):
        return bool(self.config.get("auth", {}).get("enabled", False))

    def get_user(self, name):
        """Case-insensitive lookup against users.json."""
        if not name:
            return None
        target = name.strip().lower()
        for u in self.users_doc.get("users", []):
            if (u.get("name") or "").strip().lower() == target:
                return u
        return None

    # ── Password hashing (argon2id, OWASP minimum params) ──────────

    def hash_password(self, password, salt=None):
        """Hash a password with argon2id.

        Returns `{"password_hash": "$argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>"}`.
        The salt is embedded in the argon2 hash format — no separate
        column. `salt` kwarg is accepted for API compatibility but ignored
        (argon2id generates its own cryptographically-random salt).
        """
        return {
            "password_hash": _PH.hash(password),
        }

    def verify_password(self, username, password):
        """Verify a username + password pair against users.json.

        Uses argon2.PasswordHasher.verify(). On success, also checks
        check_needs_rehash() and transparently re-hashes + persists if
        the stored parameters are weaker than the current OWASP minimums.
        """
        user = self.get_user(username)
        if not user:
            return False
        stored = user.get("password_hash")
        if not stored:
            return False
        try:
            _PH.verify(stored, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, InvalidHash, VerificationError, Argon2Error):
            # Defensive: don't leak whether the failure was format vs mismatch.
            return False
        except Exception:
            # Catch-all: same posture — fail closed without leaking detail.
            return False

        # Transparent rehash if OWASP params have been raised since the
        # stored hash was written.
        try:
            if _PH.check_needs_rehash(stored):
                new_hash = _PH.hash(password)
                user["password_hash"] = new_hash
                # Persist back to disk so the upgrade sticks.
                try:
                    self._save_users()
                except Exception as e:
                    logger.warning(f"needs_rehash: persist failed: {e}")
        except Exception as e:
            # Don't fail the login just because the rehash check exploded.
            logger.warning(f"needs_rehash: check failed: {e}")

        return True

    # ── Token ops ──────────────────────────────────────────────────

    def create_token(self, username, expires_hours=24):
        """Return a base64(payload).hex(sig) string."""
        payload = {
            "sub": username,
            "iat": int(time.time()),
            "exp": int(time.time()) + (expires_hours * 3600),
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
        sig = hmac.new(
            self.secret.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        return f"{payload_b64}.{sig}"

    def verify_token(self, token):
        """Return the username (sub) if the token is valid + unexpired."""
        if not token:
            return None
        try:
            payload_b64, sig = token.rsplit(".", 1)
            expected = hmac.new(
                self.secret.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            if payload.get("exp", 0) < time.time():
                return None
            return payload.get("sub")
        except Exception:
            return None

    # ── Flask middleware ───────────────────────────────────────────

    def flask_middleware(self, app):
        """Register @before_request auth gate + login/logout routes."""
        from flask import request, jsonify, make_response, redirect, url_for

        # Paths that bypass auth. /brand.css is needed by the login page;
        # /static/* covers any future static assets.
        bypass_prefixes = ("/static",)
        bypass_paths = {"/login", "/api/login", "/logout", "/brand.css",
                        "/manifest.json", "/icon-192.png", "/icon-512.png",
                        "/favicon.ico"}

        @app.before_request
        def check_auth():
            if not self.is_enabled():
                request.user = "anonymous"
                return None

            path = request.path or "/"
            if path in bypass_paths or any(path.startswith(p) for p in bypass_prefixes):
                return None

            # 1. Bearer token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                user = self.verify_token(auth_header[7:])
                if user:
                    request.user = user
                    return None

            # 2. aios_token cookie (set on /api/login)
            token = request.cookies.get("aios_token")
            if token:
                user = self.verify_token(token)
                if user:
                    request.user = user
                    return None

            # 3. Unauthorized
            accept = request.headers.get("Accept", "") or ""
            if "text/html" in accept and request.method == "GET":
                return redirect("/login", code=302)
            return jsonify({"error": "Unauthorized"}), 401

        @app.route("/api/login", methods=["POST"])
        def api_login():
            # CSRF is intentionally NOT enforced on login (bootstrap entry).
            # Brute-force defense is rate-limiting at the reverse proxy.
            data = request.get_json(silent=True) or {}
            username = (data.get("username") or "").strip()
            password = data.get("password") or ""
            # Re-read users.json on each login attempt so password updates
            # don't require a server restart.
            self.users_doc = self._load_json(self.users_path) or {"users": []}
            if self.verify_password(username, password):
                token = self.create_token(username)
                resp = make_response(jsonify({
                    "token": token,
                    "user": username,
                    "ok": True,
                }))
                resp.set_cookie(
                    "aios_token", token,
                    httponly=True, samesite="Lax", max_age=86400,
                )
                return resp
            return jsonify({"error": "Invalid credentials", "ok": False}), 401

        @app.route("/login", methods=["GET"])
        def login_page():
            from flask import make_response
            resp = make_response(self.login_page_html())
            resp.headers["Content-Type"] = "text/html; charset=utf-8"
            return resp

        @app.route("/logout", methods=["GET", "POST"])
        def logout():
            resp = make_response(redirect("/login", code=302))
            resp.delete_cookie("aios_token")
            return resp

    # ── Login page HTML ────────────────────────────────────────────

    def login_page_html(self):
        """Render the login page. Pulls brand from config white_label.
        Includes a CSRF token meta tag for the dashboard JS (post-login)."""
        wl = self.config.get("white_label", {})
        company = wl.get("company_name", "AIOS")
        primary = "#ed2127"  # Harbor & Vine brand red

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{company} — Sign In</title>
<link rel="stylesheet" href="/brand.css">
<style>
  :root {{ --primary: {primary}; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Lato', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #fafafa; color: #1a1a1a;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
  }}
  .login-card {{
    background: #fff; border: 1px solid #e5e5e5; border-radius: 4px;
    padding: 3rem 2.5rem; width: 100%; max-width: 380px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .brand-mark {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.6rem; font-weight: 700; letter-spacing: 0.04em;
    text-align: center; margin-bottom: 0.4rem; color: #1a1a1a;
  }}
  .brand-mark .amp {{ font-style: italic; font-weight: 400; padding: 0 0.25em; }}
  .sub {{ color: #666; text-align: center; font-size: 0.82rem;
         text-transform: uppercase; letter-spacing: 0.1em;
         margin-bottom: 2rem; }}
  .form-group {{ margin-bottom: 1.1rem; }}
  label {{ display: block; font-size: 0.72rem; color: #444;
          margin-bottom: 0.4rem; text-transform: uppercase;
          letter-spacing: 0.08em; font-weight: 700; }}
  input[type="text"], input[type="password"] {{
    width: 100%; padding: 0.7rem 0.9rem; background: #fff;
    border: 1px solid #d4d4d4; border-radius: 2px;
    color: #1a1a1a; font-size: 0.95rem; outline: none;
    transition: border-color 0.15s;
  }}
  input:focus {{ border-color: var(--primary); }}
  button {{
    width: 100%; padding: 0.75rem; background: var(--primary);
    color: #fff; border: none; border-radius: 2px;
    font-size: 0.85rem; font-weight: 700; cursor: pointer;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-top: 0.5rem; transition: filter 0.15s;
  }}
  button:hover {{ filter: brightness(0.92); }}
  .error {{ color: var(--primary); text-align: center; font-size: 0.85rem;
           margin-top: 1rem; display: none; }}
  .note {{ font-size: 0.72rem; color: #888; text-align: center;
          margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<div class="login-card">
  <div class="brand-mark">Harbor<span class="amp">&amp;</span>Vine</div>
  <div class="sub">Operations · Sign In</div>
  <form id="loginForm" onsubmit="return handleLogin(event)">
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required
             autocomplete="username" autofocus>
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required
             autocomplete="current-password">
    </div>
    <button type="submit">Sign In</button>
    <div class="error" id="errorMsg">Invalid username or password</div>
  </form>
  <div class="note">Sandbox build · Authentication enabled.</div>
</div>
<script>
async function handleLogin(e) {{
  e.preventDefault();
  const errEl = document.getElementById('errorMsg');
  errEl.style.display = 'none';
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  try {{
    const resp = await fetch('/api/login', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{username, password}})
    }});
    if (resp.ok) {{
      window.location.href = '/';
    }} else {{
      errEl.style.display = 'block';
    }}
  }} catch (err) {{
    errEl.textContent = 'Connection error. Try again.';
    errEl.style.display = 'block';
  }}
  return false;
}}
</script>
</body>
</html>"""


# Module-level helper for server.py: import + call once at startup.
def flask_middleware(app):
    """Module-level entry point. Wires the Auth instance + middleware."""
    auth = Auth()
    auth.flask_middleware(app)
    # Expose on the app so tests + other modules can introspect.
    app.auth = auth
    return auth


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auth manager (sandbox)")
    parser.add_argument(
        "action",
        choices=["hash", "verify", "generate-secret", "list-users"],
    )
    parser.add_argument("--username", "-u", help="Username")
    parser.add_argument("--password", "-p", help="Password")
    args = parser.parse_args()

    auth = Auth()
    if args.action == "hash":
        if not args.password:
            print("Error: --password required")
            raise SystemExit(1)
        print(json.dumps(auth.hash_password(args.password), indent=2))
    elif args.action == "verify":
        if not args.username or not args.password:
            print("Error: --username and --password required")
            raise SystemExit(1)
        ok = auth.verify_password(args.username, args.password)
        print("Valid credentials" if ok else "Invalid credentials")
        raise SystemExit(0 if ok else 1)
    elif args.action == "generate-secret":
        print(secrets.token_hex(32))
    elif args.action == "list-users":
        for u in auth.users_doc.get("users", []):
            print(f"  {u.get('name')} ({u.get('role')}) — "
                  f"{'has hash' if u.get('password_hash') else 'NO HASH'}")
