"""
Harbor & Vine — Anomaly detection engine.

Cross-cuts the existing AlertEngine monitors: anything that looks like
an outlier (same-day showing conflicts, deals stalled past the high
threshold, commission disputes) is a brokerage anomaly worth flagging.

Thin shim today; the contract is `check_all()` returns a dict with
categorized findings. The dashboard's anomaly_detection module reads
this so the Overview "needs your attention" panel can surface it.
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.alert_engine import AlertEngine


class AnomalyEngine:
    def __init__(self):
        self.alerts = AlertEngine()

    def check_all(self):
        """Run every anomaly monitor; return categorized results."""
        showings = self.alerts.check_showing_conflicts()
        stalled = self.alerts.check_stalled_deals()
        disputes = self.alerts.check_commission_disputes()
        return {
            "showing_conflicts": showings,
            "stalled_deals": stalled,
            "commission_disputes": disputes,
            "total_anomalies": len(showings) + len(stalled) + len(disputes),
        }


def is_enabled():
    return True


if __name__ == "__main__":
    e = AnomalyEngine()
    result = e.check_all()
    print(f"Anomalies detected: {result['total_anomalies']}")
    print(f"  showing_conflicts: {len(result['showing_conflicts'])}")
    print(f"  stalled_deals: {len(result['stalled_deals'])}")
    print(f"  commission_disputes: {len(result['commission_disputes'])}")
