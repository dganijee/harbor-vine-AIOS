"""
Meeting Brief — read upcoming brokerage meetings (closings, listing
appointments, broker previews) off Google Calendar and produce a quick
brief for the assigned agent or coordinator.

Sandbox: reads from the gcal fixture via the Pattern A connector. In
production, the GoogleCalendarConnector will hit the live Calendar API
when active.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.connectors.google_calendar import GoogleCalendarConnector


KEY_TYPES = ('closing', 'listing', 'broker preview', 'inspection', 'open house')


def run(days=7):
    cal = GoogleCalendarConnector()
    data = cal.pull()
    tasks = data.get('tasks', []) or []

    today = datetime.now().strftime('%Y-%m-%d')
    horizon = days

    key_events = []
    for t in tasks:
        desc_lower = (t.get('description') or '').lower()
        if any(k in desc_lower for k in KEY_TYPES):
            key_events.append(t)

    return {
        'today': today,
        'events_found': len(tasks),
        'key_events': len(key_events),
        'horizon_days': horizon,
        'details': key_events[:10],
    }


if __name__ == '__main__':
    result = run()
    print(f"Meeting brief — {result['today']}")
    print(f"  Calendar events: {result['events_found']}")
    print(f"  Key brokerage events: {result['key_events']}")
    for d in result['details']:
        print(f"    - {d.get('due_date', '')}: {d.get('description', '')}")
