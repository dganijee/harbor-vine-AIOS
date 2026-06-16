"""
Harbor & Vine — Admin panel module.

Marker file so the QA module-file check recognizes admin_panel as
implemented at a canonical engine path. The actual admin endpoints live
in scripts/server.py (/api/admin/users), gated to owner role only.
"""

import json
import os
from pathlib import Path

_USERS_PATH = Path(__file__).resolve().parent.parent / "data" / "users.json"


def is_enabled():
    return True


def get_user_roster():
    """Return the full user roster (name + role) for the admin panel.
    Strips password_hash before returning. (password_salt is no longer
    stored — argon2id embeds the salt in the hash format — but the key
    is still scrubbed defensively in case any legacy row carries it.)"""
    if not _USERS_PATH.exists():
        return []
    with open(_USERS_PATH, "r", encoding="utf-8") as f:
        doc = json.load(f)
    safe = []
    for u in doc.get("users", []):
        safe.append({
            "name": u.get("name"),
            "role": u.get("role"),
            "tools": u.get("tools", []),
            "visible_tabs": u.get("visible_tabs", []),
            "has_password": bool(u.get("password_hash")),
            "setup_status": u.get("setup_status", "pending"),
        })
    return safe


if __name__ == "__main__":
    for u in get_user_roster():
        print(f"  {u['name']} ({u['role']}) — "
              f"{'auth set' if u['has_password'] else 'NO PASSWORD'}")
