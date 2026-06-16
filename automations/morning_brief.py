"""
Morning Brief — 7:30 AM daily Telegram digest for Marisol Trent and Devin Okafor
Orchestrates all data sources into a single morning brief.
Scheduled via system scheduler.
"""

import os
import sys
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.brief_engine import BriefEngine
from engine.alert_engine import AlertEngine
from engine.data_os import init_db


def run():
    init_db()
    brief = BriefEngine()
    alerts = AlertEngine()

    # Generate briefs for each recipient
    owner_brief = brief.generate_morning_brief('owner')
    president_brief = brief.generate_morning_brief('president')

    # Send via Telegram
    results = {}

    owner_result = alerts.send_telegram(owner_brief, 'owner')
    results['owner'] = 'sent' if owner_result.get('ok') else owner_result.get('error', 'failed')

    president_result = alerts.send_telegram(president_brief, 'president')
    results['president'] = 'sent' if president_result.get('ok') else president_result.get('error', 'failed')

    return {
        'timestamp': datetime.now().isoformat(),
        'delivery': results
    }


if __name__ == '__main__':
    result = run()
    print(f"Morning brief generated at {result['timestamp']}")
    for recipient, status in result['delivery'].items():
        print(f"  {recipient}: {status}")
