"""One-shot rehash of users.json to argon2id (OWASP minimum params).

Maps each user by role to their documented sandbox test password and
re-derives the password_hash. Removes the now-defunct password_salt field.
Run once after the auth.py argon2id swap.
"""
import sys, os, json
ROOT = r"C:\Users\dgani\Desktop\harbor-vine-AIOS"
sys.path.insert(0, ROOT)
from templates.backend.auth import _PH

USERS = os.path.join(ROOT, "data", "users.json")

# Per-user explicit map (handles the two-agent case which both share password_agent).
NAME_TO_PWD = {
    "Marisol Trent":  "password_owner",
    "Devin Okafor":   "password_president",
    "Carol Benitez":  "password_accounting",
    "Priya Raman":    "password_tc",
    "Jess Holloway":  "password_agent",
    "Tomás Vidal":    "password_agent",
}

with open(USERS, "r", encoding="utf-8") as f:
    doc = json.load(f)

for u in doc.get("users", []):
    name = u.get("name")
    pwd = NAME_TO_PWD.get(name)
    if not pwd:
        print(f"  no pwd map for {name}; skipping")
        continue
    new_hash = _PH.hash(pwd)
    u["password_hash"] = new_hash
    if "password_salt" in u:
        del u["password_salt"]
    print(f"  {name}: {new_hash[:55]}...")

tmp = USERS + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
os.replace(tmp, USERS)
print("DONE")

# Verify
with open(USERS, "r", encoding="utf-8") as f:
    doc2 = json.load(f)
print("\nVerification:")
for u in doc2["users"]:
    h = u.get("password_hash", "")
    ok = h.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    has_salt = "password_salt" in u
    print(f"  {u['name']}: prefix_ok={ok}, salt_present={has_salt}")
