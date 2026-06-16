"""
Harbor & Vine — Approval monitor automation.

Cron entry point that lists pending approvals + (in production) sends a
digest to the broker-owner via Telegram. Sandbox: just prints to stdout.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.approval_engine import ApprovalEngine
from engine.data_os import init_db


def run():
    init_db()
    engine = ApprovalEngine()
    pending = engine.pending_approvals()
    print(f"[approval_monitor] {len(pending)} pending approval(s)")
    for p in pending[:5]:
        print(f"  - {p['deal_title']} (${p['gross']:,.0f}) — {p['reason']}")
    return pending


if __name__ == "__main__":
    run()
