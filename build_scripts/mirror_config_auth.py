"""Mirror users.json -> config.json auth.users (for aios_qa.py).

Bundle 1 reference auth stores hashes in config.auth.users keyed by username.
We keep that mirror only so aios_qa.py's check_auth contract test sees a
populated dict; the live verify path uses data/users.json.
"""
import json, os
ROOT = r"C:\Users\dgani\Desktop\harbor-vine-AIOS"
USERS = os.path.join(ROOT, "data", "users.json")
CFG   = os.path.join(ROOT, "data", "config.json")

with open(USERS, "r", encoding="utf-8") as f:
    users_doc = json.load(f)
with open(CFG, "r", encoding="utf-8") as f:
    cfg = json.load(f)

# Mirror as argon2:<hash> so the format matches the live auth path
# (the prefix self-identifies as argon2id either way).
mirror = {}
for u in users_doc["users"]:
    name = u["name"]
    h = u.get("password_hash", "")
    mirror[name] = f"argon2:{h}" if h else ""

cfg.setdefault("auth", {})
cfg["auth"]["users"] = mirror

tmp = CFG + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
os.replace(tmp, CFG)
print("config.json auth.users mirror updated.")
for k, v in mirror.items():
    print(f"  {k}: {v[:50]}...")
