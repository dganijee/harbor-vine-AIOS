"""
Brief Engine — Brokerage briefs for Harbor & Vine Realty

Generates morning briefs (Telegram-friendly HTML) and a weekly executive
summary. Numbers come from the brokerage engine + the daily_snapshots table.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from engine.data_os import query, execute, get_active_alerts
from engine.brokerage_engine import BrokerageEngine


class BriefEngine:
    def __init__(self):
        self.engine = BrokerageEngine()
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    def generate_morning_brief(self, recipient='owner'):
        """Produce the morning brief HTML (Telegram-friendly tags)."""
        sections = []

        # -- Pipeline Snapshot ------------------------------------------
        pipeline = self.engine.get_pipeline_summary()
        commission = self.engine.get_commission_mtd()
        active_listings = self.engine.get_active_listings_count()
        sections.append(
            f"<b>Pipeline Snapshot</b>\n"
            f"  Active listings: {active_listings}\n"
            f"  Open volume: ${pipeline['open_volume']:,.0f}\n"
            f"  Active deals: {pipeline['active_count']}\n"
            f"  Commission MTD (net): ${commission['net_total']:,.0f}"
        )

        # -- Active Alerts ----------------------------------------------
        alerts = get_active_alerts()
        if alerts:
            high = [a for a in alerts if a['severity'] == 'high']
            med = [a for a in alerts if a['severity'] == 'medium']
            lines = [f"<b>Active Alerts</b> ({len(alerts)} total)"]
            for a in high[:5]:
                lines.append(f"  ⚠️ {a['title']}")
            for a in med[:3]:
                lines.append(f"  ℹ️ {a['title']}")
            if len(alerts) > 8:
                lines.append(f"  ... and {len(alerts) - 8} more")
            sections.append('\n'.join(lines))

        # -- Top Listings by DOM ----------------------------------------
        top = self.engine.get_top_listings_by_dom(5)
        if top:
            lines = ["<b>Top Listings by DOM</b>"]
            for i, l in enumerate(top, 1):
                lines.append(f"  {i}. {l['address']} — DOM {l['days_on_market']}")
            sections.append('\n'.join(lines))

        # -- Closings This Week -----------------------------------------
        closings = query("""
            SELECT title, value, agent, contact_name
            FROM pipeline
            WHERE status = 'Closing'
              AND updated_at >= date('now', '-7 days')
            ORDER BY value DESC
            LIMIT 5
        """)
        if closings:
            lines = ["<b>Closings This Week</b>"]
            for c in closings:
                lines.append(f"  • {c['title']} — ${c['value']:,.0f} ({c['agent']})")
            sections.append('\n'.join(lines))

        # -- Lead Funnel -------------------------------------------------
        funnel = self.engine.get_lead_funnel()
        if funnel:
            lines = ["<b>Lead Funnel</b>"]
            for f in funnel:
                lines.append(f"  {f['status'].title()}: {f['cnt']}")
            sections.append('\n'.join(lines))

        # -- Compose -----------------------------------------------------
        header = f"<b>Good Morning — {datetime.now().strftime('%A, %b %d')}</b>"
        body = '\n\n'.join(sections) if sections else 'No data available yet. Activate the connectors to populate the brief.'
        brief = f"{header}\n\n{body}"

        execute("""
            INSERT INTO briefs (brief_type, recipient, content)
            VALUES (?, ?, ?)
        """, ('morning', recipient, brief))

        return brief

    def generate_executive_summary(self):
        """7-day brokerage trend summary."""
        sections = []

        # 7-day snapshot trend
        week = query("""
            SELECT date, active_listings, pipeline_volume, closings_count,
                   commission_total, new_leads, showings_count
            FROM daily_snapshots
            WHERE date >= date('now', '-7 days')
            ORDER BY date DESC
        """)
        if week:
            total_closings = sum((r['closings_count'] or 0) for r in week)
            total_commission = sum((r['commission_total'] or 0) for r in week)
            total_leads = sum((r['new_leads'] or 0) for r in week)
            avg_pipeline = sum((r['pipeline_volume'] or 0) for r in week) / len(week)
            avg_showings = sum((r['showings_count'] or 0) for r in week) / len(week)
            sections.append(
                f"<b>7-Day Brokerage Trend</b>\n"
                f"  Avg pipeline volume: ${avg_pipeline:,.0f}\n"
                f"  Closings: {total_closings}\n"
                f"  Commission earned (run-rate): ${total_commission:,.0f}\n"
                f"  New leads: {total_leads}\n"
                f"  Avg showings/day: {avg_showings:.1f}"
            )

        # Commissions by agent (this month)
        by_agent = self.engine.get_commissions_by_agent()
        if by_agent:
            lines = ["<b>Commissions by Agent (MTD)</b>"]
            for a in by_agent:
                lines.append(f"  {a['agent_name']}: ${a['net_total']:,.0f} ({a['cnt']} deals)")
            sections.append('\n'.join(lines))

        # Alert activity
        alert_act = query("""
            SELECT severity, COUNT(*) as cnt
            FROM alerts
            WHERE created_at >= date('now', '-7 days')
            GROUP BY severity
        """)
        if alert_act:
            lines = ["<b>Alert Activity (7d)</b>"]
            for a in alert_act:
                lines.append(f"  {a['severity'].upper()}: {a['cnt']}")
            sections.append('\n'.join(lines))

        header = f"<b>Weekly Executive Summary — {datetime.now().strftime('%b %d, %Y')}</b>"
        body = '\n\n'.join(sections) if sections else 'No snapshot data yet.'
        return f"{header}\n\n{body}"


if __name__ == '__main__':
    engine = BriefEngine()
    print(engine.generate_morning_brief())
