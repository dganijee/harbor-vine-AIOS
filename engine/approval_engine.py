"""
Harbor & Vine — Approval workflow engine.

Pending-approval items are:
- Commission rows in 'disputed' status (need owner sign-off to resolve).
- Commission rows where gross > thresholds.approval_auto_limit (manual
  review threshold from data/thresholds.json).

Returns a list of dicts ready to render in the dashboard / brief.
"""

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.data_os import query

THRESHOLDS_PATH = _ROOT / "data" / "thresholds.json"
DEFAULT_AUTO_LIMIT = 50_000   # $50k gross commission threshold


class ApprovalEngine:
    def __init__(self):
        self.thresholds = self._load_thresholds()
        self.auto_limit = self.thresholds.get(
            "approval_auto_limit", DEFAULT_AUTO_LIMIT,
        )

    @staticmethod
    def _load_thresholds():
        if not THRESHOLDS_PATH.exists():
            return {}
        try:
            with open(THRESHOLDS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def pending_approvals(self):
        """Return commission rows that need owner-level approval."""
        rows = query("""
            SELECT id, external_id, deal_title, agent_name,
                   gross, net, status, period_month
            FROM commissions
            WHERE status = 'disputed' OR gross > ?
            ORDER BY gross DESC
        """, (self.auto_limit,))
        return [
            {
                "id": r["id"],
                "external_id": r["external_id"],
                "deal_title": r["deal_title"],
                "agent_name": r["agent_name"],
                "gross": r["gross"],
                "net": r["net"],
                "status": r["status"],
                "period_month": r["period_month"],
                "reason": (
                    "disputed" if r["status"] == "disputed"
                    else f"gross > ${self.auto_limit:,}"
                ),
            }
            for r in rows
        ]


def is_enabled():
    return True


if __name__ == "__main__":
    e = ApprovalEngine()
    pending = e.pending_approvals()
    print(f"Pending approvals: {len(pending)}")
    for p in pending[:5]:
        print(f"  {p['deal_title']} — ${p['gross']:,.0f} ({p['reason']})")
