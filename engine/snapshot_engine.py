"""
Harbor & Vine — Daily snapshot engine.

Builds a KPI dict from the live brokerage tables and persists it to the
daily_snapshots table. Cron-friendly via automations/morning_snapshot.py.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.data_os import query, execute, init_db
from engine.brokerage_engine import BrokerageEngine


class SnapshotEngine:
    def __init__(self):
        self.engine = BrokerageEngine()

    def daily_snapshot(self):
        """Compute today's KPI dict + persist to daily_snapshots table."""
        init_db()
        kpis = self.engine.get_overview_kpis()
        snap = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "active_listings": int(kpis.get("active_listings") or 0),
            "pipeline_volume": float(kpis.get("pipeline_volume") or 0),
            "closings_count": int(kpis.get("closings_this_month") or 0),
            "commission_total": float(kpis.get("commission_mtd") or 0),
            "new_leads": int(kpis.get("new_leads_week") or 0),
            "showings_count": int(kpis.get("showings_next_7d") or 0),
        }
        execute("""
            INSERT INTO daily_snapshots
                (date, active_listings, pipeline_volume, closings_count,
                 commission_total, new_leads, showings_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                active_listings = excluded.active_listings,
                pipeline_volume = excluded.pipeline_volume,
                closings_count = excluded.closings_count,
                commission_total = excluded.commission_total,
                new_leads = excluded.new_leads,
                showings_count = excluded.showings_count
        """, (
            snap["date"], snap["active_listings"], snap["pipeline_volume"],
            snap["closings_count"], snap["commission_total"],
            snap["new_leads"], snap["showings_count"],
        ))
        return snap


def is_enabled():
    return True


if __name__ == "__main__":
    e = SnapshotEngine()
    snap = e.daily_snapshot()
    print(f"[snapshot_engine] daily snapshot persisted for {snap['date']}")
    for k, v in snap.items():
        print(f"  {k}: {v}")
