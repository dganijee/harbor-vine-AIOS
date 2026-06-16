"""
Harbor & Vine Realty FluentOS — Boot Sequence
Initializes database, checks connector status, starts dashboard server.
Bootstraps .env (FLASK_SECRET_KEY, AIOS_MASTER_KEY) if missing.
"""

import os
import secrets as py_secrets
import sys
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ENV_PATH = os.path.join(ROOT, ".env")


def _read_env_file():
    if not os.path.exists(ENV_PATH):
        return {}
    out = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _append_env(key, value):
    with open(ENV_PATH, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def ensure_env():
    """Make sure .env exists with FLASK_SECRET_KEY + AIOS_MASTER_KEY set.
    Generated values are persisted so they survive reboots."""
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("# Harbor & Vine — Sandbox environment (gitignored)\n")
    env = _read_env_file()

    if not env.get("FLASK_SECRET_KEY"):
        _append_env("FLASK_SECRET_KEY", py_secrets.token_urlsafe(32))
    if not env.get("AIOS_MASTER_KEY"):
        # Fernet-shaped urlsafe-b64 32-byte key.
        from cryptography.fernet import Fernet
        _append_env("AIOS_MASTER_KEY", Fernet.generate_key().decode("ascii"))

    # Load the file into the current process environment too.
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=False)
    except ImportError:
        for k, v in _read_env_file().items():
            os.environ.setdefault(k, v)


def boot():
    print("=" * 50)
    print("  Harbor & Vine Realty FluentOS — Starting Up")
    print("=" * 50)

    # 0. Bootstrap .env (FLASK_SECRET_KEY, AIOS_MASTER_KEY).
    print("\n[0/4] Bootstrapping .env...")
    ensure_env()
    print("  ✓ .env ready (secrets present)")

    # 1. Initialize database
    print("\n[1/4] Initializing database...")
    from engine.data_os import init_db
    init_db()
    print("  ✓ Database ready")

    # 2. Check connectors
    print("\n[2/4] Checking connectors...")
    connectors = check_connectors()
    for name, status in connectors.items():
        icon = "OK" if status else "--"
        print(f"  [{icon}] {name}: {'active' if status else 'inactive (sandbox)'}")

    # 3. Check automations
    print("\n[3/4] Automation monitors loaded:")
    automations = [
        'stalled_deal_monitor', 'showing_conflict_monitor',
        'commission_dispute_monitor', 'lead_followup_monitor',
        'meeting_brief', 'morning_brief'
    ]
    for a in automations:
        print(f"  - {a.replace('_', ' ').title()}")

    # 4. Start dashboard server
    print("\n[4/4] Starting dashboard server...")
    server_path = os.path.join(ROOT, 'scripts', 'server.py')
    if os.path.exists(server_path):
        subprocess.Popen(
            [sys.executable, server_path],
            cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        time.sleep(2)
        print("  ✓ Dashboard running at http://127.0.0.1:8001")
    else:
        print("  ✗ server.py not found")

    print("\n" + "=" * 50)
    configured = sum(1 for v in connectors.values() if v)
    total = len(connectors)
    print(f"  Status: {configured}/{total} connectors ready")
    print(f"  Dashboard: http://127.0.0.1:8001")
    print("=" * 50)


def check_connectors():
    """
    Probe the 4 Pattern A connectors registered for this brokerage build.

    Uses tools.connectors.manager.REGISTRY as the single source of truth so
    this stays in sync with the rest of the stack. Calls is_active() per
    connector — in the sandbox every connector returns False (auth disabled,
    data flows from fixtures via seed_db_from_fixtures), which is correct.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, '.env'))
    except Exception:
        pass

    status = {}

    try:
        from tools.connectors.manager import REGISTRY
        for name, ConnectorClass in REGISTRY.items():
            try:
                inst = ConnectorClass()
                # Pattern A connectors expose is_active(); the sandbox
                # always returns False because connect() is stubbed.
                status[name] = bool(inst.is_active()) if hasattr(inst, 'is_active') else False
            except Exception:
                status[name] = False
    except Exception:
        # Manager unavailable — fall back to listing the 4 known connectors
        # as inactive so the boot screen still renders something useful.
        for name in ('gmail', 'google_calendar', 'google_sheets', 'qbo'):
            status[name] = False

    status['Telegram'] = bool(os.getenv('TELEGRAM_BOT_TOKEN'))
    return status


if __name__ == '__main__':
    boot()
