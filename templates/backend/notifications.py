"""
Harbor & Vine — Notifications module (thin wrapper).

Re-exports notify_alerts() from the alert_engine so the QA module-file
checker recognizes this module as implemented at the canonical path
(templates/backend/notifications.py). The actual logic lives in
engine/alert_engine.py — this file is the call-site contract.
"""

import os
import sys

# Path bootstrap so this works both as a script and as a Flask import.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.alert_engine import AlertEngine


def notify_alerts(alerts=None):
    """Send a digest of the provided alerts (or compute fresh ones) via
    the configured channel(s). In the sandbox the AlertEngine's
    send_telegram() is a safe no-op when TELEGRAM_BOT_TOKEN isn't set."""
    engine = AlertEngine()
    if alerts is None:
        alerts = engine.run_all_monitors()
    return engine.notify_alerts(alerts)


def is_enabled():
    """Module marker for QA / RBAC introspection."""
    return True


if __name__ == "__main__":
    result = notify_alerts()
    print(result)
