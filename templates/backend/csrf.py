"""
Harbor & Vine — CSRF helper (session-anchored double-submit cookie).

How it works
------------
On every authenticated GET, the server sets a `csrf_token` cookie (NOT
httponly so JS can read it) bound to the SESSION via HMAC. On every
POST/PUT/DELETE/PATCH, the `@require_csrf` decorator checks that the
`X-CSRF-Token` request header matches the cookie value AND the HMAC
signature verifies against FLASK_SECRET_KEY AND the embedded session
anchor matches the current authenticated session.

Atlas finding #5 fix
--------------------
Previously the token was just `nonce.hmac(nonce, secret)` — any
validly-signed token worked for any session, so a token from one user's
session would pass for another user's session if attached. The new
format is:

    `<session_anchor>.<nonce>.<hmac(session_anchor + "." + nonce, secret)>`

`session_anchor` is `sha256(aios_token)[:32]` for an authenticated
request, or `unauth-<random>` for the login bootstrap (only valid until
the user actually logs in). On validation we recompute the expected
anchor for the CURRENT session and reject if the submitted token's
anchor doesn't match.

Bootstrap exception: /api/login bypasses CSRF (it's the entry point;
the rate-limiter is the brute-force defense).

The dashboard's existing fetch wrapper is unchanged on disk; the
CSRF JS is INJECTED into the dashboard HTML at /-serve time by the
server (see scripts/server.py serve_dashboard()).
"""

import os
import hmac
import hashlib
import secrets
from functools import wraps

from templates.backend import cookie_secure, cookie_samesite

# Header / cookie names — kept short, no dots/spaces.
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"

# Anchor prefix used when no aios_token cookie exists yet (login bootstrap).
_UNAUTH_PREFIX = "unauth-"


def _secret_key():
    """Return the Flask secret key. Fails closed if absent."""
    s = os.environ.get("FLASK_SECRET_KEY")
    if not s:
        raise RuntimeError(
            "FLASK_SECRET_KEY missing — CSRF helper cannot sign tokens."
        )
    return s.encode("utf-8") if isinstance(s, str) else s


def _session_anchor(aios_token):
    """Derive the session anchor for a given aios_token cookie value.

    sha256 (first 32 hex chars) gives a deterministic, opaque anchor that
    changes the instant the session changes — so an old session's CSRF
    token cannot be reused after re-login.
    """
    if not aios_token:
        return None
    return hashlib.sha256(aios_token.encode("utf-8")).hexdigest()[:32]


def _expected_anchor(request):
    """Anchor expected for the current request's authenticated session."""
    aios_token = request.cookies.get("aios_token")
    if aios_token:
        return _session_anchor(aios_token)
    return None


def generate_csrf_token(session_anchor=None):
    """Generate a fresh CSRF token bound to a session anchor.

    Format: `<anchor>.<nonce>.<sig>`
    Anchor is `_session_anchor(aios_token)` for authenticated sessions or
    `unauth-<random>` for the login bootstrap.
    """
    if not session_anchor:
        session_anchor = _UNAUTH_PREFIX + secrets.token_urlsafe(8)
    nonce = secrets.token_urlsafe(16)
    msg = f"{session_anchor}.{nonce}".encode("utf-8")
    sig = hmac.new(_secret_key(), msg, hashlib.sha256).hexdigest()
    return f"{session_anchor}.{nonce}.{sig}"


def parse_csrf_token(token):
    """Return (session_anchor, nonce, sig) or None on malformed input."""
    if not token or not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def verify_csrf_token(token, expected_anchor=None):
    """Verify a CSRF token. Returns True if BOTH the HMAC signature
    checks out AND the embedded session anchor matches expected_anchor
    (when provided). Unauthenticated anchors (`unauth-*`) are accepted
    only when expected_anchor is None (login bootstrap).
    """
    parsed = parse_csrf_token(token)
    if not parsed:
        return False
    anchor, nonce, sig = parsed
    msg = f"{anchor}.{nonce}".encode("utf-8")
    expected_sig = hmac.new(_secret_key(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
    if expected_anchor is None:
        # No authenticated session — only unauth tokens are acceptable.
        return anchor.startswith(_UNAUTH_PREFIX)
    # Authenticated session — anchor MUST match (no unauth fallback).
    return hmac.compare_digest(anchor, expected_anchor)


def ensure_csrf_cookie(response, request):
    """Set the csrf_token cookie on the response.

    Issued bound to the CURRENT authenticated session's anchor (or an
    unauth anchor if not logged in). If the request already carries a
    cookie that validates against the current anchor, leave it alone.
    """
    expected = _expected_anchor(request)
    existing = request.cookies.get(CSRF_COOKIE)
    if existing and verify_csrf_token(existing, expected_anchor=expected):
        return response
    token = generate_csrf_token(session_anchor=expected)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,  # JS must read this to echo it in the header
        samesite=cookie_samesite(),
        secure=cookie_secure(request),
        max_age=86400,
    )
    return response


def require_csrf(fn):
    """Decorator: enforce session-anchored double-submit CSRF check."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import request, jsonify
        header_token = request.headers.get(CSRF_HEADER, "")
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        # Both must be present + identical.
        if not header_token or not cookie_token:
            return jsonify({"error": "CSRF token missing"}), 403
        if not hmac.compare_digest(header_token, cookie_token):
            return jsonify({"error": "CSRF token mismatch"}), 403
        # Atlas finding #5: anchor MUST match the current session.
        expected = _expected_anchor(request)
        if not verify_csrf_token(header_token, expected_anchor=expected):
            return jsonify({"error": "CSRF token invalid"}), 403
        return fn(*args, **kwargs)
    return wrapper


def csrf_install(app):
    """Wire CSRF into a Flask app: set cookie on every GET response."""
    from flask import request

    @app.after_request
    def _set_csrf_cookie(response):
        # Only set on GET requests with HTML responses (dashboard, login).
        if request.method != "GET":
            return response
        try:
            return ensure_csrf_cookie(response, request)
        except Exception:
            return response
    return app


# JS snippet injected into dashboard HTML at /-serve time so that
# outputs/dashboard.html stays unchanged on disk.
CSRF_INJECT_SCRIPT = """
<script>
/* CSRF (session-anchored double-submit cookie) — injected at /-serve time. */
(function() {
  function getCsrfCookie() {
    var m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  var origFetch = window.fetch;
  window.fetch = function(input, init) {
    init = init || {};
    var method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
    if (['POST','PUT','DELETE','PATCH'].indexOf(method) !== -1) {
      init.headers = init.headers || {};
      if (init.headers instanceof Headers) {
        if (!init.headers.has('X-CSRF-Token')) {
          init.headers.set('X-CSRF-Token', getCsrfCookie());
        }
      } else if (!('X-CSRF-Token' in init.headers)) {
        init.headers['X-CSRF-Token'] = getCsrfCookie();
      }
    }
    return origFetch.call(this, input, init);
  };
})();
</script>
"""


def inject_csrf_into_html(html, csrf_token=None):
    """Inject the CSRF script + meta tag right before </head>.
    csrf_token is informational (server cookie is the gate)."""
    meta = ""
    if csrf_token:
        meta = f'<meta name="csrf-token" content="{csrf_token}">\n'
    inject = meta + CSRF_INJECT_SCRIPT
    if "</head>" in html:
        return html.replace("</head>", inject + "</head>", 1)
    # Fallback: prepend so it still runs before the body's <script> blocks.
    return inject + html
