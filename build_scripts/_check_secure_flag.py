"""Check that AIOS_SECURE_COOKIES=1 flips the Secure attribute on aios_token."""
import json
import urllib.request
import urllib.error

req = urllib.request.Request(
    "http://127.0.0.1:8001/api/login",
    data=json.dumps({"username": "Marisol Trent", "password": "password_owner"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    set_cookies = resp.headers.get_all("Set-Cookie") or []
    resp.read()
except urllib.error.HTTPError as e:
    set_cookies = e.headers.get_all("Set-Cookie") or []
    e.read()

print("Set-Cookie headers:")
for h in set_cookies:
    print(" ", h)

aios = next((h for h in set_cookies if h.startswith("aios_token=")), "")
secure = "secure" in aios.lower()
samesite = "samesite=lax" in aios.lower()
httponly = "httponly" in aios.lower()
print(f"\naios_token: secure={secure}, samesite=Lax={samesite}, httponly={httponly}")
print(f"\nRESULT secure_flag_when_env_set: {secure}")
