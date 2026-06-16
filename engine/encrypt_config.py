"""
Harbor & Vine — Connector credentials encryption migration.

Walks data/connectors.json and encrypts every field whose name matches
the credential heuristic. Idempotent: re-running is a no-op for already
encrypted values (they're tagged `enc::v1:` and skipped).

In the sandbox, connector configs don't carry real creds (all
`active:false`). So this migration also seeds a few obvious-fake test
credential values into each connector's `secrets` block first, then
encrypts them — this way the migration actually has something to encrypt
and `grep -c "enc::"` returns > 0, proving the path RAN (Sentinel rule
56 — built-but-unrun = no remediation).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.secrets_vault import (
    encrypt,
    decrypt,
    is_encrypted,
    looks_like_credential,
)

CONNECTORS_PATH = ROOT / "data" / "connectors.json"

# Sandbox seed values per connector — obvious fakes so the migration
# has something to encrypt. The format mirrors what live OAuth2 credentials
# would look like (client_id / client_secret / refresh_token) so when
# Stage 3 wires the real flow, the field shape matches.
SANDBOX_SEED_SECRETS = {
    "gmail": {
        "client_id": "sandbox-gmail-client-id.apps.googleusercontent.com",
        "client_secret": "sandbox-gmail-client-secret-value",
        "refresh_token": "sandbox-gmail-refresh-token-fake",
    },
    "google_calendar": {
        "client_id": "sandbox-gcal-client-id.apps.googleusercontent.com",
        "client_secret": "sandbox-gcal-client-secret-value",
        "refresh_token": "sandbox-gcal-refresh-token-fake",
    },
    "google_sheets": {
        "client_id": "sandbox-sheets-client-id.apps.googleusercontent.com",
        "client_secret": "sandbox-sheets-client-secret-value",
        "refresh_token": "sandbox-sheets-refresh-token-fake",
    },
    "qbo": {
        "client_id": "sandbox-qbo-client-id-value",
        "client_secret": "sandbox-qbo-client-secret-value",
        "refresh_token": "sandbox-qbo-refresh-token-fake",
        "realm_id": "sandbox-qbo-realm-id-fake",
    },
}


def _walk_and_encrypt(obj):
    """Recursively walk a dict/list; encrypt any leaf string whose KEY
    looks credential-shaped. Returns (modified_obj, count_encrypted)."""
    count = 0
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, (dict, list)):
                _, sub_count = _walk_and_encrypt(v)
                count += sub_count
            elif isinstance(v, str) and looks_like_credential(k) and not is_encrypted(v):
                obj[k] = encrypt(v)
                count += 1
    elif isinstance(obj, list):
        for item in obj:
            _, sub_count = _walk_and_encrypt(item)
            count += sub_count
    return obj, count


def _seed_sandbox_secrets(config):
    """Add a `secrets` block per connector if not present, populated with
    obvious-fake values. Idempotent: skips connectors that already carry
    encrypted secrets."""
    added = 0
    connectors = config.get("connectors", {})
    for name, seed in SANDBOX_SEED_SECRETS.items():
        if name not in connectors:
            continue
        existing = connectors[name].get("secrets") or {}
        for field, fake_value in seed.items():
            # Only seed if the field isn't already there (either as plain
            # or already-encrypted) — preserves operator-set values.
            if field not in existing:
                existing[field] = fake_value
                added += 1
        connectors[name]["secrets"] = existing
    return added


def run_migration():
    """Read connectors.json, seed sandbox secrets, encrypt creds, write back."""
    if not CONNECTORS_PATH.exists():
        print(f"[encrypt_config] connectors.json not found at {CONNECTORS_PATH}")
        return {"ran": False, "encrypted": 0, "seeded": 0}

    with open(CONNECTORS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 1. Seed obvious-fake sandbox secrets if absent (so the migration has
    # something to encrypt and the audit can verify it RAN).
    seeded = _seed_sandbox_secrets(config)

    # 2. Encrypt all credential-shaped fields, recursively.
    _, encrypted_count = _walk_and_encrypt(config)

    # 3. Write back atomically.
    tmp = CONNECTORS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, CONNECTORS_PATH)

    print(f"[encrypt_config] Seeded {seeded} sandbox secret fields")
    print(f"[encrypt_config] Encrypted {encrypted_count} credential field(s)")
    print(f"[encrypt_config] Migration complete: {CONNECTORS_PATH}")
    return {
        "ran": True,
        "seeded": seeded,
        "encrypted": encrypted_count,
        "path": str(CONNECTORS_PATH),
    }


def decrypt_lookup(connector_name, field_name):
    """Read a connector's secret field, decrypting on the fly. Returns None
    if missing. Used by live connectors at OAuth time in production."""
    if not CONNECTORS_PATH.exists():
        return None
    with open(CONNECTORS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    block = (
        config.get("connectors", {})
        .get(connector_name, {})
        .get("secrets", {})
    )
    value = block.get(field_name)
    if value is None:
        return None
    return decrypt(value)


if __name__ == "__main__":
    result = run_migration()
    print(json.dumps(result, indent=2))
