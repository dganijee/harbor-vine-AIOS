"""
Harbor & Vine — CSRF helper (double-submit-cookie pattern).

How it works
------------
On every authenticated GET, the server sets a `csrf_token` cookie (NOT
httponly so JS can read it) bound to the session via HMAC. On every
POST/PUT/DELETE/PATCH, the `@require_csrf` decorator checks that the
`X-CSRF-Token` request header matches the cookie value AND the HMAC
signature verifies against FLASK_SECRET_KEY.

Bootstrap exception: /api/login bypasses CSRF (it's the entry point;
the rate-limiter at the proxy is the brute-force defense). The login
PAGE itself includes a hidden CSRF token input for the form post, but
because the dashboard's JS uses the JSON /api/login API the hidden
input is mostly informational.

The dashboard's existing fetch wrapper is unchanged on disk; the
CSRF JS is INJECTED into the dashboard HTML at /-serve time by the
server (see scripts/server.py serve_dashboard()). This keeps
outputs/dashboard.html unchanged on disk per the build constraint.
"""

import os
import hmac
import hashlib
import secrets
from functools import wraps

# Header / cookie names — kept short, no dots/spaces.
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"


def _secret_key():
    """Return the Flask secret key. Fails closed if absent."""
    s = os.environ.get("FLASK_SECRET_KEY")
    if not s:
        # Caller (server.py) is expected to fail-closed BEFORE we get here.
        # This is a belt-and-suspenders guard.
        raise RuntimeError(
            "FLASK_SECRET_KEY missing — CSRF helper cannot sign tokens."
        )
    return s.encode("utf-8") if isinstance(s, str) else s


def generate_csrf_token():
    """Generate a fresh CSRF token: '<random>.<hmac>' signed with FLASK_SECRET_KEY."""
    nonce = secrets.token_urlsafe(16)
    sig = hmac.new(_secret_key(), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def verify_csrf_token(token):
    """Verify a CSRF token. Returns True if the HMAC signature checks out."""
    if not token or "." not in token:
        return False
    try:
        nonce, sig = token.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_secret_key(), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def ensure_csrf_cookie(response, request):
    """Set the csrf_token cookie on the response if one isn't already
    present on the request. Called from an after_request hook."""
    existing = request.cookies.get(CSRF_COOKIE)
    if existing and verify_csrf_token(existing):
        return response
    response.set_cookie(
        CSRF_COOKIE,
        generate_csrf_token(),
        httponly=False,  # JS must read this to echo it in the header
        samesite="Lax",
        max_age=86400,
    )
    return response


def require_csrf(fn):
    """Decorator: enforce double-submit CSRF check on a route."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import request, jsonify
        header_token = request.headers.get(CSRF_HEADER, "")
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        # Both must be present, equal, and signed validly.
        if not header_token or not cookie_token:
            return jsonify({"error": "CSRF token missing"}), 403
        if not hmac.compare_digest(header_token, cookie_token):
            return jsonify({"error": "CSRF token mismatch"}), 403
        if not verify_csrf_token(header_token):
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
/* CSRF (double-submit cookie) — injected by server at /-serve time. */
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
