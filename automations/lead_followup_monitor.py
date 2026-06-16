"""
Lead Follow-up Monitor — flags warm/hot leads with no contact in
N+ days (per data/thresholds.json) so the assigned agent re-engages
before the lead goes cold.
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
    alerts = engine.check_lead_followup()
    delivery = engine.notify_alerts(alerts)
    return {
        'timestamp': datetime.now().isoformat(),
        'alerts': alerts,
        'delivery': delivery,
    }


if __name__ == '__main__':
    result = run()
    print(f"Lead follow-up monitor — {result['timestamp']}")
    print(f"  Alerts created: {len(result['alerts'])}")
    print(f"  Delivery: {result['delivery']}")
