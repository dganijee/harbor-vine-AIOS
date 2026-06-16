"""
Stalled Deal Monitor — alerts when a deal sits in pending/closing/offer
past the configured thresholds (data/thresholds.json).
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.alert_engine import AlertEngine
from engine.data_os import init_db


def run():
    init_db()
    engine = AlertEngine()
    alerts = engine.check_stalled_deals()
    delivery = engine.notify_alerts(alerts)
    return {
        'timestamp': datetime.now().isoformat(),
        'alerts': alerts,
        'delivery': delivery,
    }


if __name__ == '__main__':
    result = run()
    print(f"Stalled deal monitor — {result['timestamp']}")
    print(f"  Alerts created: {len(result['alerts'])}")
    print(f"  Delivery: {result['delivery']}")
