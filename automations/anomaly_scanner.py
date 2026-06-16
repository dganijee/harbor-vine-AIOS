"""
Harbor & Vine — Anomaly scanner automation.

Cron-friendly entry point that calls AnomalyEngine.check_all() and prints
a one-line digest. Wires into deploy/setup.sh scheduling.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.anomaly_engine import AnomalyEngine
from engine.data_os import init_db


def run():
    init_db()
    engine = AnomalyEngine()
    result = engine.check_all()
    print(
        f"[anomaly_scanner] {result['total_anomalies']} anomalies: "
        f"showings={len(result['showing_conflicts'])}, "
        f"stalled={len(result['stalled_deals'])}, "
        f"disputes={len(result['commission_disputes'])}"
    )
    return result


if __name__ == "__main__":
    run()
