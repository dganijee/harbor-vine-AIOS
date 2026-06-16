"""
Alert Engine — Brokerage threshold monitors + notifications for Harbor & Vine

Runs monitors against the SQLite cache (populated by the connectors),
creates alert rows, and (in production) sends a Telegram digest to the
broker-owner and managing broker.

Sandbox: no real Telegram calls. send_telegram() returns an error dict
when the bot token isn't set, which is the offline default.
"""

import os
import sys
import json
from datetime import datetime

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from engine.data_os import query, create_alert, get_active_alerts

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

THRESHOLDS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'thresholds.json')


class AlertEngine:
    def __init__(self):
        with open(THRESHOLDS_PATH) as f:
            self.thresholds = json.load(f)
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_recipients = {
            'owner': os.getenv('TELEGRAM_CHAT_ID_OWNER'),
            'president': os.getenv('TELEGRAM_CHAT_ID_PRESIDENT'),
        }

    def run_all_monitors(self):
        """Execute every brokerage monitor and return the union of new alerts."""
        results = []
        results.extend(self.check_stalled_deals())
        results.extend(self.check_showing_conflicts())
        results.extend(self.check_commission_disputes())
        results.extend(self.check_lead_followup())
        results.extend(self.check_listing_dom())
        return results

    # -- Monitors --------------------------------------------------------

    def check_stalled_deals(self):
        """Deals in escrow/pending/closing past the configured day thresholds."""
        cfg = self.thresholds.get('stalled_deals', {})
        med_days = int(cfg.get('med_days', 7))
        high_days = int(cfg.get('high_days', 14))

        rows = query("""
            SELECT id, external_id, title, status, value, agent, updated_at,
                   CAST((julianday('now') - julianday(updated_at)) AS INTEGER) as days_stalled
            FROM pipeline
            WHERE status IN ('Closing', 'Pending', 'Offer')
              AND (julianday('now') - julianday(updated_at)) >= ?
        """, (med_days,))

        alerts = []
        for r in rows:
            stalled = r['days_stalled'] or 0
            severity = 'high' if stalled >= high_days else 'medium'
            alert_id = create_alert(
                severity=severity,
                alert_type='stalled_deal',
                title=f"{r['title']} — {r['status'].lower()} stalled {stalled} days",
                body=f"Deal value ${r['value']:,.0f}; assigned to {r['agent']}.",
                entity_id=r['external_id'],
            )
            alerts.append({
                'id': alert_id, 'type': 'stalled_deal',
                'title': r['title'], 'days_stalled': stalled, 'severity': severity,
            })
        return alerts

    def check_showing_conflicts(self):
        """Same agent or overlapping showings flag a conflict."""
        cfg = self.thresholds.get('showing_conflict', {})
        severity = cfg.get('severity', 'high')

        # Same-time conflicts: two showings at the exact same datetime that
        # share an agent OR share an address.
        rows = query("""
            SELECT s1.external_id as a_id, s2.external_id as b_id,
                   s1.listing_address as address,
                   s1.agent_name as agent_a, s2.agent_name as agent_b,
                   s1.showing_datetime as ts
            FROM showings s1
            JOIN showings s2
              ON s1.showing_datetime = s2.showing_datetime
             AND s1.id < s2.id
             AND (s1.agent_name = s2.agent_name OR s1.listing_address = s2.listing_address)
            WHERE s1.showing_datetime >= date('now')
        """)
        alerts = []
        for r in rows:
            title = f"Showing conflict at {r['address']}"
            body = (
                f"{r['ts']}: {r['agent_a']} and {r['agent_b']} double-booked. "
                f"Events {r['a_id']} / {r['b_id']}."
            )
            alert_id = create_alert(
                severity=severity, alert_type='showing_conflict',
                title=title, body=body, entity_id=r['a_id'],
            )
            alerts.append({'id': alert_id, 'type': 'showing_conflict',
                           'title': title, 'severity': severity})
        return alerts

    def check_commission_disputes(self):
        """Any commission row flagged 'disputed' → high severity alert."""
        cfg = self.thresholds.get('commission_dispute', {})
        severity = cfg.get('severity', 'high')

        rows = query("""
            SELECT id, external_id, deal_title, agent_name, gross, period_month
            FROM commissions
            WHERE status = 'disputed'
        """)
        alerts = []
        for r in rows:
            title = f"Commission dispute — {r['deal_title']}"
            body = (
                f"Gross ${r['gross']:,.0f} unallocated for {r['agent_name']} "
                f"(period {r['period_month']})."
            )
            alert_id = create_alert(
                severity=severity, alert_type='commission_dispute',
                title=title, body=body, entity_id=r['external_id'],
            )
            alerts.append({'id': alert_id, 'type': 'commission_dispute',
                           'title': title, 'severity': severity})
        return alerts

    def check_lead_followup(self):
        """Leads with no contact in N+ days → medium severity."""
        cfg = self.thresholds.get('lead_followup', {})
        max_days = int(cfg.get('max_days_since_contact', 5))
        severity = cfg.get('severity', 'medium')

        rows = query("""
            SELECT id, external_id, name, source, status, last_contacted_at, agent_assigned
            FROM leads
            WHERE status IN ('new', 'warm', 'hot')
              AND (
                last_contacted_at IS NULL
                OR (julianday('now') - julianday(last_contacted_at)) >= ?
              )
        """, (max_days,))

        alerts = []
        for r in rows:
            title = f"Lead follow-up overdue — {r['name']}"
            body = (
                f"Status {r['status']}, source {r['source'] or 'unknown'}, "
                f"assigned {r['agent_assigned'] or 'unassigned'}."
            )
            alert_id = create_alert(
                severity=severity, alert_type='lead_followup',
                title=title, body=body, entity_id=r['external_id'],
            )
            alerts.append({'id': alert_id, 'type': 'lead_followup',
                           'title': title, 'severity': severity})
        return alerts

    def check_listing_dom(self):
        """Listings sitting past the DOM threshold → medium severity."""
        cfg = self.thresholds.get('listing_dom', {})
        max_days = int(cfg.get('max_days', 90))
        severity = cfg.get('severity', 'medium')

        rows = query("""
            SELECT id, external_id, address, list_price, days_on_market, agent_name
            FROM listings
            WHERE status IN ('Active', 'Listed', 'New')
              AND days_on_market > ?
        """, (max_days,))

        alerts = []
        for r in rows:
            title = f"{r['address']} — {r['days_on_market']} days on market"
            body = f"Listed at ${r['list_price']:,.0f} by {r['agent_name']}. Consider price review."
            alert_id = create_alert(
                severity=severity, alert_type='listing_stale',
                title=title, body=body, entity_id=r['external_id'],
            )
            alerts.append({'id': alert_id, 'type': 'listing_stale',
                           'title': title, 'severity': severity})
        return alerts

    # -- Notifications ---------------------------------------------------

    def send_telegram(self, message, recipient='owner'):
        """Send an alert digest. Sandbox-safe: returns an error dict when
        TELEGRAM_BOT_TOKEN is unset, which is the default in this build."""
        if not self.telegram_token:
            return {'error': 'Telegram not configured', 'ok': False}

        chat_id = self.telegram_recipients.get(recipient)
        if not chat_id:
            return {'error': f'No chat ID for {recipient}', 'ok': False}

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'},
                timeout=10,
            )
            return resp.json()
        except Exception as e:
            return {'error': str(e), 'ok': False}

    def notify_alerts(self, alerts):
        """Compose a digest and send to owner + president."""
        if not alerts:
            return {'sent': False, 'reason': 'no alerts'}

        lines = [f"<b>Harbor &amp; Vine Alerts — {datetime.now().strftime('%b %d %H:%M')}</b>\n"]
        for a in alerts:
            sev = a.get('severity', 'medium')
            icon = {'high': '⚠️', 'medium': 'ℹ️', 'low': '•'}.get(sev, '•')
            lines.append(f"{icon} {a.get('title', a.get('type', 'alert'))}")

        msg = '\n'.join(lines)
        owner_resp = self.send_telegram(msg, 'owner')
        pres_resp = self.send_telegram(msg, 'president')
        return {'sent': True, 'owner': owner_resp, 'president': pres_resp}

    def get_alert_summary(self):
        """Group active alerts by severity."""
        active = get_active_alerts()
        summary = {'high': [], 'medium': [], 'low': []}
        for a in active:
            sev = a.get('severity', 'medium')
            if sev in summary:
                summary[sev].append(a)
        return summary


if __name__ == '__main__':
    engine = AlertEngine()
    print("Alert Engine initialized")
    print(f"  Telegram: {'configured' if engine.telegram_token else 'not configured'}")
    print(f"  Thresholds loaded: {list(engine.thresholds.keys())}")
