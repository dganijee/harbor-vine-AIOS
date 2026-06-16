"""
Harbor & Vine — Secrets at rest (Fernet, build-local key).

Per the playbook (Atlas's B2 derivation): each build derives its connector
key from a master key + a per-build salt via PBKDF2-HMAC-SHA256(100_000),
then wraps as a urlsafe-b64 Fernet key.

Sandbox specifics:
- AIOS_MASTER_KEY is generated once and persisted to .env (gitignored).
- Per-build derived key salt is `b"aios-build-harbor-vine"`.
- All credential-shaped fields in data/connectors.json are encrypted with
  the `enc::v1:<token>` tag prefix so the migration is verifiable via
  `grep enc::` (Sentinel rule 56).

NOT for production SaaS use: a real SaaS deploy would derive per-USER keys
from the platform's KMS-resident master, not a build-local key file. This
file is the sandbox / single-tenant build pattern.
"""

import base64
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
BUILD_SLUG = "harbor-vine"
DERIVATION_SALT = f"aios-build-{BUILD_SLUG}".encode("utf-8")
PBKDF2_ITERATIONS = 100_000

ENCRYPTED_TAG = "enc::v1:"


# ─── .env helpers ────────────────────────────────────────────────────


def _read_env_file():
    """Parse the .env file into a dict. Returns {} if absent."""
    if not ENV_PATH.exists():
        return {}
    data = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _write_env_key(key, value):
    """Append or update a key=value pair in .env (creates the file)."""
    existing = _read_env_file()
    existing[key] = value
    lines = []
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if stripped.startswith("#") or "=" not in stripped:
                lines.append(raw)
                continue
            k = stripped.split("=", 1)[0].strip()
            if k == key:
                continue   # we'll re-emit it below
            lines.append(raw)
    lines.append(f'{key}={value}')
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── Master key + derived Fernet ────────────────────────────────────


def _ensure_master_key():
    """Return the master key (bytes). Generate + persist to .env if absent."""
    env = _read_env_file()
    master = env.get("AIOS_MASTER_KEY") or os.environ.get("AIOS_MASTER_KEY")
    if not master:
        master = Fernet.generate_key().decode("ascii")
        _write_env_key("AIOS_MASTER_KEY", master)
        # Make it available to the current process too.
        os.environ["AIOS_MASTER_KEY"] = master
    return master.encode("ascii") if isinstance(master, str) else master


def _derive_fernet_key(master_bytes):
    """PBKDF2-HMAC-SHA256(master, salt=aios-build-<slug>) -> Fernet key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=DERIVATION_SALT,
        iterations=PBKDF2_ITERATIONS,
    )
    raw = kdf.derive(master_bytes)
    return base64.urlsafe_b64encode(raw)


_fernet_singleton = None


def _get_fernet():
    global _fernet_singleton
    if _fernet_singleton is None:
        master = _ensure_master_key()
        # AIOS_MASTER_KEY is itself a Fernet key (urlsafe-b64) — but per the
        # playbook we still pass it through PBKDF2 with the build-slug salt
        # so two builds with the same master derive DIFFERENT keys.
        derived = _derive_fernet_key(master)
        _fernet_singleton = Fernet(derived)
    return _fernet_singleton


def reset_for_tests():
    """Discard the cached singleton (used by unit tests that override env)."""
    global _fernet_singleton
    _fernet_singleton = None


# ─── Public API ──────────────────────────────────────────────────────


def encrypt(plaintext):
    """Encrypt a string; return 'enc::v1:<token>'. None/empty pass-through."""
    if plaintext is None or plaintext == "":
        return plaintext
    if isinstance(plaintext, str) and plaintext.startswith(ENCRYPTED_TAG):
        return plaintext   # already encrypted, idempotent
    f = _get_fernet()
    token = f.encrypt(str(plaintext).encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_TAG}{token}"


def decrypt(value):
    """Decrypt a tagged string; pass-through unchanged for plain values."""
    if not isinstance(value, str) or not value.startswith(ENCRYPTED_TAG):
        return value
    f = _get_fernet()
    token = value[len(ENCRYPTED_TAG):]
    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Bad ciphertext — surface as a clear error rather than silent fail.
        raise RuntimeError("Failed to decrypt secret — key mismatch or tampering")


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(ENCRYPTED_TAG)


# Field-name heuristic for the migration: anything matching these patterns
# is treated as a credential and encrypted.
CREDENTIAL_FIELD_PATTERNS = (
    "password", "secret", "token", "api_key", "apikey",
    "client_secret", "client_id", "refresh_token", "access_token",
    "private_key", "service_account",
)


def looks_like_credential(field_name):
    """Return True if the field name looks credential-shaped."""
    n = (field_name or "").lower()
    return any(p in n for p in CREDENTIAL_FIELD_PATTERNS)


if __name__ == "__main__":
    # Smoke test: generate + roundtrip.
    print(f"Master key path: {ENV_PATH}")
    sample = "sandbox-test-secret-value"
    enc = encrypt(sample)
    print(f"Encrypted: {enc[:60]}...")
    dec = decrypt(enc)
    print(f"Decrypted: {dec}")
    assert dec == sample, "Roundtrip failed!"
    print("OK")
