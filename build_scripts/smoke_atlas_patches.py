"""
Live HTTP smoke test for the 5 Atlas finding patches.

Hits the Flask server running on 127.0.0.1:8001 and verifies each fix.

Prints PASS/FAIL per check and a final summary JSON (used by the dispatch
return shape). Exit code 0 if every check passes, 1 otherwise.
"""

import json
import sys
import time
import urllib.request
import urllib.error
import http.cookiejar

BASE = "http://127.0.0.1:8001"


def make_opener():
    """Fresh cookie jar opener — one per simulated browser session."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "smoke/1.0")]
    return opener, jar


def call(opener, method, path, body=None, extra_headers=None):
    """Perform an HTTP call; return (status, response_body_text, headers_dict)."""
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")
        return e.code, body_txt, dict(e.headers or {})


def get_cookie(jar, name):
    for c in jar:
        if c.name == name:
            return c.value
    return None


def login(username, password):
    """Run the full login bootstrap for a username. Returns (opener, jar, login_status, csrf_token)."""
    opener, jar = make_opener()
    # 1. GET /login so the csrf_token cookie gets set with an unauth anchor.
    call(opener, "GET", "/login")
    # 2. POST /api/login (CSRF bypassed on this endpoint).
    status, _, _ = call(opener, "POST", "/api/login",
                        body={"username": username, "password": password})
    if status != 200:
        return opener, jar, status, None
    # 3. Hit a GET endpoint to force the server to issue a NEW csrf_token
    #    bound to the post-login session anchor. The dashboard / would do
    #    this naturally; we hit /api/me which is cheap.
    call(opener, "GET", "/api/me")
    csrf = get_cookie(jar, "csrf_token")
    return opener, jar, 200, csrf


def main():
    results = {}

    # ───────────────────────────────────────────────────────────────────
    # Finding #1: privilege escalation via /api/role_switch
    # ───────────────────────────────────────────────────────────────────
    print("\n── Finding #1: Jess (agent) tries to elevate to owner via role_switch ──")
    jess_opener, jess_jar, jess_status, jess_csrf = login("Jess Holloway", "password_agent")
    assert jess_status == 200, f"Jess login should succeed, got {jess_status}"
    assert jess_csrf, "Jess should have csrf cookie after GET"

    # Attempt elevation
    status, body, _ = call(
        jess_opener, "POST", "/api/role_switch",
        body={"role": "owner"},
        extra_headers={"X-CSRF-Token": jess_csrf},
    )
    print(f"  POST /api/role_switch {{role:'owner'}} as Jess -> {status} {body[:120]}")
    results["jess_role_switch_to_owner_returns_403"] = (status == 403)

    # Same Jess session asks for commissions (agent doesn't have commissions in scope)
    status_c, body_c, _ = call(jess_opener, "GET", "/api/commissions")
    print(f"  GET /api/commissions as Jess -> {status_c} {body_c[:100]}")
    results["jess_get_commissions_returns_403"] = (status_c == 403)

    # ───────────────────────────────────────────────────────────────────
    # Finding #2: president no longer has commissions
    # ───────────────────────────────────────────────────────────────────
    print("\n── Finding #2: Devin (president) tries commissions + leads ──")
    devin_opener, devin_jar, devin_status, devin_csrf = login("Devin Okafor", "password_president")
    assert devin_status == 200, f"Devin login should succeed, got {devin_status}"

    status, body, _ = call(devin_opener, "GET", "/api/commissions")
    print(f"  GET /api/commissions as Devin -> {status} {body[:100]}")
    results["devin_get_commissions_returns_403"] = (status == 403)

    status_l, body_l, _ = call(devin_opener, "GET", "/api/leads")
    print(f"  GET /api/leads as Devin -> {status_l} {body_l[:80]}")
    results["devin_get_leads_returns_200"] = (status_l == 200)

    # ───────────────────────────────────────────────────────────────────
    # Finding #3: Set-Cookie attributes
    # ───────────────────────────────────────────────────────────────────
    print("\n── Finding #3: cookie attributes (samesite/secure) ──")
    opener3, jar3 = make_opener()
    # We need to capture the raw Set-Cookie header on /api/login response.
    # Use a one-off URL open + look at response headers.
    req = urllib.request.Request(
        BASE + "/api/login",
        data=json.dumps({"username": "Marisol Trent", "password": "password_owner"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = opener3.open(req, timeout=10)
        set_cookie_headers = resp.headers.get_all("Set-Cookie") or []
        resp.read()
    except urllib.error.HTTPError as e:
        set_cookie_headers = e.headers.get_all("Set-Cookie") or []
        e.read()

    print("  Set-Cookie headers seen:")
    for h in set_cookie_headers:
        print(f"    {h}")

    aios_cookie_line = next((h for h in set_cookie_headers if h.startswith("aios_token=")), "")
    samesite_seen = "samesite=lax" in aios_cookie_line.lower()
    secure_seen = "secure" in aios_cookie_line.lower()
    httponly_seen = "httponly" in aios_cookie_line.lower()
    print(f"  aios_token cookie: samesite=Lax? {samesite_seen}, secure? {secure_seen}, httponly? {httponly_seen}")
    results["samesite_lax_set"] = samesite_seen
    results["sandbox_secure_flag_off"] = not secure_seen
    results["httponly_set"] = httponly_seen

    # ───────────────────────────────────────────────────────────────────
    # Finding #4: login rate limit
    # ───────────────────────────────────────────────────────────────────
    print("\n── Finding #4: 6 failed logins from one IP within seconds ──")
    statuses = []
    for i in range(6):
        opener_x, _ = make_opener()
        s, b, h = call(opener_x, "POST", "/api/login",
                       body={"username": "Marisol Trent", "password": "WRONG"})
        statuses.append(s)
        print(f"  attempt {i + 1}: status={s}")
    sixth_429 = (statuses[5] == 429)
    results["sixth_failed_login_returns_429"] = sixth_429

    # Clear the rate limiter so subsequent runs / live login still work.
    import sqlite3
    conn = sqlite3.connect(r"C:\Users\dgani\Desktop\harbor-vine-AIOS\data\ops.db")
    conn.execute("DELETE FROM login_attempts")
    conn.commit()
    conn.close()

    # ───────────────────────────────────────────────────────────────────
    # Finding #5: CSRF token bound to session
    # ───────────────────────────────────────────────────────────────────
    print("\n── Finding #5: CSRF token from another session is rejected ──")
    # Log in as Marisol, capture her csrf token.
    mar_opener, mar_jar, mar_status, mar_csrf = login("Marisol Trent", "password_owner")
    assert mar_status == 200, f"Marisol login should succeed, got {mar_status}"
    print(f"  Marisol's csrf_token (anchor prefix): {(mar_csrf or '')[:20]}")
    # Log out so the cookie is gone.
    call(mar_opener, "POST", "/logout")

    # Now log in as Jess in a separate session.
    jess2_opener, jess2_jar, jess2_status, jess2_csrf = login("Jess Holloway", "password_agent")
    assert jess2_status == 200, f"Jess re-login should succeed, got {jess2_status}"
    print(f"  Jess's   csrf_token (anchor prefix): {(jess2_csrf or '')[:20]}")
    print(f"  Are the anchors different?           {(mar_csrf or '')[:20] != (jess2_csrf or '')[:20]}")

    # Attempt /api/role_switch from Jess's session BUT with Marisol's OLD csrf token
    # both as the header AND as the cookie (so the double-submit equality check passes
    # and only the session-anchor check catches it).
    # Strip the csrf_token cookie Jess has and inject Marisol's old one.
    jess2_jar.clear(domain="127.0.0.1", path="/", name="csrf_token")
    # Inject Marisol's old csrf cookie into Jess's jar by hand:
    import http.cookiejar as cj
    fake = cj.Cookie(
        version=0, name="csrf_token", value=mar_csrf or "",
        port=None, port_specified=False,
        domain="127.0.0.1", domain_specified=True, domain_initial_dot=False,
        path="/", path_specified=True,
        secure=False, expires=None, discard=False,
        comment=None, comment_url=None, rest={},
    )
    jess2_jar.set_cookie(fake)

    status, body, _ = call(
        jess2_opener, "POST", "/api/role_switch",
        body={"role": "agent"},
        extra_headers={"X-CSRF-Token": mar_csrf or ""},
    )
    print(f"  POST /api/role_switch with Marisol's old csrf in Jess's session -> {status} {body[:120]}")
    results["csrf_token_from_other_session_returns_403"] = (status == 403)

    # ───────────────────────────────────────────────────────────────────
    # Regression sweep
    # ───────────────────────────────────────────────────────────────────
    print("\n── Regression sweep ──")
    # Owner previewing agent should still work + narrow.
    opener_o, jar_o, status_o, csrf_o = login("Marisol Trent", "password_owner")
    assert status_o == 200
    status, body, _ = call(opener_o, "POST", "/api/role_switch",
                           body={"role": "agent", "user_name": "Jess Holloway"},
                           extra_headers={"X-CSRF-Token": csrf_o})
    print(f"  owner preview as agent -> {status} {body[:120]}")
    owner_preview_ok = (status == 200)
    # In preview, owner should hit 403 on commissions (agent set has no commissions)
    status_c, _, _ = call(opener_o, "GET", "/api/commissions")
    print(f"  owner-preview-as-agent GET /api/commissions -> {status_c}")
    owner_preview_narrowed = (status_c == 403)
    results["owner_can_preview_other_roles_narrow_only"] = owner_preview_ok and owner_preview_narrowed

    print("\n=" * 1)
    print("SUMMARY")
    print(json.dumps(results, indent=2))
    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"\nFAILED: {failed}")
        sys.exit(1)
    print("\nALL CHECKS PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
