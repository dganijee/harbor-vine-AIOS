"""
Commission Dispute Monitor — surfaces any commission rows in the QBO
ledger that are flagged 'disputed' so Carol + Marisol can resolve the
split before the period closes.
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
    alerts = engine.check_commission_disputes()
    delivery = engine.notify_alerts(alerts)
    return {
        'timestamp': datetime.now().isoformat(),
        'alerts': alerts,
        'delivery': delivery,
    }


if __name__ == '__main__':
    result = run()
    print(f"Commission dispute monitor — {result['timestamp']}")
    print(f"  Alerts created: {len(result['alerts'])}")
    print(f"  Delivery: {result['delivery']}")
