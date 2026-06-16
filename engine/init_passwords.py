"""
Harbor & Vine — First-run password initialization.

Walks data/users.json. For each user missing `password_hash`:
- In production: prompts the operator on stdin (Sentinel rule 41 — no
  default password ships).
- In the SANDBOX: sets a deterministic test password keyed off the role
  (e.g. password_owner). These are documented loudly as TEST credentials,
  not real ones. The operator (and Sentinel) know.

This is idempotent: users that already carry a password_hash are skipped.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from templates.backend.auth import Auth

USERS_PATH = ROOT / "data" / "users.json"

# Deterministic test passwords per role. Sandbox-only — DO NOT use these
# in any environment that touches a real user.
SANDBOX_TEST_PASSWORDS = {
    "owner":      "password_owner",
    "president":  "password_president",
    "accounting": "password_accounting",
    "tc":         "password_tc",
    "agent":      "password_agent",
}


def _read_users():
    if not USERS_PATH.exists():
        return {"users": []}
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_users(doc):
    tmp = USERS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, USERS_PATH)


def run(interactive=False):
    """Initialize password hashes for any user missing one.

    interactive=True   → prompt the operator (production behavior).
    interactive=False  → use SANDBOX_TEST_PASSWORDS keyed by role
                         (sandbox default).
    """
    doc = _read_users()
    auth = Auth()
    set_count = 0
    test_creds = {}

    for u in doc.get("users", []):
        if u.get("password_hash"):
            continue  # already set, skip

        name = u.get("name", "?")
        role = u.get("role", "?")

        if interactive:
            import getpass
            print(f"\nSet password for {name} ({role}):")
            pwd = getpass.getpass("  password: ")
            pwd2 = getpass.getpass("  confirm:  ")
            if pwd != pwd2:
                print(f"  Mismatch — skipping {name}")
                continue
            if not pwd:
                print(f"  Empty — skipping {name}")
                continue
        else:
            pwd = SANDBOX_TEST_PASSWORDS.get(role)
            if not pwd:
                print(f"  No sandbox password for role={role}; skipping {name}")
                continue

        h = auth.hash_password(pwd)
        u["password_hash"] = h["password_hash"]
        u["password_salt"] = h["password_salt"]
        set_count += 1
        test_creds[role] = pwd

    if set_count > 0:
        _write_users(doc)

    return {"set": set_count, "test_credentials": test_creds}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Initialize user passwords")
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt operator for each password (production)",
    )
    args = p.parse_args()
    result = run(interactive=args.interactive)
    print(f"\n[init_passwords] {result['set']} password hash(es) written")
    if result["test_credentials"]:
        print("[init_passwords] TEST credentials (sandbox-only):")
        for role, pwd in result["test_credentials"].items():
            print(f"  {role}: {pwd}")
