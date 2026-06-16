"""
Harbor & Vine — Exception audit engine.

Scans the brokerage tables for exceptions (stalled deals, commission
disputes, lead-followup overdue), writes findings into an audit_log
table, and returns a categorized summary.

The audit_log table is created on demand (idempotent CREATE IF NOT
EXISTS) so this engine can be wired without a separate migration.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.data_os import query, execute
from engine.alert_engine import AlertEngine


def _ensure_audit_log_table():
    execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_at TEXT DEFAULT CURRENT_TIMESTAMP,
            category TEXT NOT NULL,
            entity_id TEXT,
            severity TEXT,
            title TEXT,
            body TEXT
        )
    """)


class AuditEngine:
    def __init__(self):
        self.alerts = AlertEngine()

    def scan_exceptions(self):
        """Run every exception monitor, write findings to audit_log,
        return a categorized summary dict."""
        _ensure_audit_log_table()
        stalled = self.alerts.check_stalled_deals()
        disputes = self.alerts.check_commission_disputes()
        followup = self.alerts.check_lead_followup()

        findings = []
        findings.extend(("stalled_deal", x) for x in stalled)
        findings.extend(("commission_dispute", x) for x in disputes)
        findings.extend(("lead_followup", x) for x in followup)

        for category, item in findings:
            execute("""
                INSERT INTO audit_log (category, entity_id, severity, title, body)
                VALUES (?, ?, ?, ?, ?)
            """, (
                category,
                str(item.get("id") or ""),
                item.get("severity", "medium"),
                item.get("title", ""),
                json.dumps({
                    k: v for k, v in item.items()
                    if k not in ("title", "severity", "id")
                }, default=str),
            ))

        return {
            "stalled_deals": len(stalled),
            "commission_disputes": len(disputes),
            "lead_followup": len(followup),
            "total": len(findings),
            "scanned_at": datetime.now().isoformat(),
        }


def is_enabled():
    return True


if __name__ == "__main__":
    e = AuditEngine()
    summary = e.scan_exceptions()
    print(f"[audit_engine] scanned at {summary['scanned_at']}")
    print(f"  stalled deals: {summary['stalled_deals']}")
    print(f"  commission disputes: {summary['commission_disputes']}")
    print(f"  lead followup overdue: {summary['lead_followup']}")
    print(f"  total exceptions: {summary['total']}")
