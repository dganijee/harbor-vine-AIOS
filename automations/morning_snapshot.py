"""
Harbor & Vine — Morning snapshot automation.

Cron entry point (07:00 daily). Generates the morning brief for the
owner role, persists today's KPI snapshot, and (in production) sends
the brief via Telegram. Sandbox keeps the Telegram send as a no-op when
TELEGRAM_BOT_TOKEN isn't set.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.brief_engine import BriefEngine
from engine.snapshot_engine import SnapshotEngine
from engine.alert_engine import AlertEngine
from engine.data_os import init_db


def run():
    init_db()

    # 1. Persist today's KPI snapshot.
    snap = SnapshotEngine().daily_snapshot()

    # 2. Generate the owner brief.
    brief = BriefEngine().generate_morning_brief("owner")

    # 3. Send via Telegram (no-op in sandbox if token missing).
    alerts = AlertEngine()
    result = alerts.send_telegram(brief, "owner")

    delivery = "sent" if result.get("ok") else result.get("error", "skipped (no telegram cfg)")
    print(f"[morning_snapshot] snapshot persisted for {snap['date']}; delivery: {delivery}")
    return {"snapshot": snap, "delivery": delivery}


if __name__ == "__main__":
    run()
