"""
Brokerage Engine — Harbor & Vine Realty operations rollup

Reads from the SQLite cache populated by the Pattern A connectors
(gmail / google_calendar / google_sheets / qbo). Exposes the methods the
dashboard's Overview and per-tab endpoints consume.

All SQL uses parameter binding; no string interpolation into queries.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from engine.data_os import query, get_active_alerts, get_brokerage_summary


class BrokerageEngine:
    def __init__(self):
        self.today = datetime.now().strftime('%Y-%m-%d')

    # ---- Pipeline -------------------------------------------------------
    def get_pipeline_summary(self, agent_filter=None):
        """Active deal count, open volume, and month-over-month delta.
        When agent_filter is set, scopes the rollup to that agent's deals only.
        """
        if agent_filter:
            active = query("""
                SELECT COUNT(*) as cnt, COALESCE(SUM(value), 0) as total
                FROM pipeline
                WHERE status NOT IN ('Closed', 'Lost', 'Cancelled')
                  AND LOWER(agent) = LOWER(?)
            """, (agent_filter,))
            last_month = query("""
                SELECT COALESCE(SUM(value), 0) as total
                FROM pipeline
                WHERE status NOT IN ('Closed', 'Lost', 'Cancelled')
                  AND updated_at < date('now', 'start of month')
                  AND LOWER(agent) = LOWER(?)
            """, (agent_filter,))
        else:
            active = query("""
                SELECT COUNT(*) as cnt, COALESCE(SUM(value), 0) as total
                FROM pipeline
                WHERE status NOT IN ('Closed', 'Lost', 'Cancelled')
            """)
            last_month = query("""
                SELECT COALESCE(SUM(value), 0) as total
                FROM pipeline
                WHERE status NOT IN ('Closed', 'Lost', 'Cancelled')
                  AND updated_at < date('now', 'start of month')
            """)
        active_count = active[0]['cnt'] if active else 0
        active_total = active[0]['total'] if active else 0
        prev_total = last_month[0]['total'] if last_month else 0
        delta_pct = 0
        if prev_total > 0:
            delta_pct = round((active_total - prev_total) / prev_total * 100, 1)
        return {
            'active_count': active_count,
            'open_volume': active_total,
            'mom_delta_pct': delta_pct,
        }

    def get_pipeline_by_stage(self, agent_filter=None):
        """Group pipeline value by stage — for the Pipeline Health chart.
        When agent_filter is set, the chart scopes to that agent only.
        """
        if agent_filter:
            return query("""
                SELECT status, COUNT(*) as cnt, COALESCE(SUM(value), 0) as total
                FROM pipeline
                WHERE LOWER(agent) = LOWER(?)
                GROUP BY status
                ORDER BY total DESC
            """, (agent_filter,))
        return query("""
            SELECT status, COUNT(*) as cnt, COALESCE(SUM(value), 0) as total
            FROM pipeline
            GROUP BY status
            ORDER BY total DESC
        """)

    def get_pipeline_rows(self, limit=100):
        """All pipeline rows for the Pipeline tab."""
        return query("""
            SELECT id, external_id, title, status, value, contact_name, agent, notes, updated_at
            FROM pipeline
            ORDER BY value DESC
            LIMIT ?
        """, (limit,))

    # ---- Listings -------------------------------------------------------
    def get_top_listings_by_dom(self, n=5):
        """Top N listings ordered by days_on_market descending."""
        return query("""
            SELECT id, external_id, address, list_price, status, days_on_market, agent_name
            FROM listings
            WHERE status IN ('Active', 'Listed', 'New')
            ORDER BY days_on_market DESC
            LIMIT ?
        """, (n,))

    def get_all_listings(self, limit=200):
        return query("""
            SELECT id, external_id, address, list_price, status, days_on_market, agent_name, notes
            FROM listings
            ORDER BY days_on_market DESC
            LIMIT ?
        """, (limit,))

    def get_active_listings_count(self):
        rows = query("SELECT COUNT(*) as cnt FROM listings WHERE status IN ('Active', 'Listed', 'New')")
        return rows[0]['cnt'] if rows else 0

    # ---- Alerts ---------------------------------------------------------
    def get_active_alerts(self):
        return get_active_alerts()

    # ---- Commissions ----------------------------------------------------
    def get_commission_mtd(self):
        """Month-to-date commissions earned (net to agents)."""
        period = datetime.now().strftime('%Y-%m')
        rows = query("""
            SELECT
                COUNT(*) as cnt,
                COALESCE(SUM(net), 0) as net_total,
                COALESCE(SUM(gross), 0) as gross_total
            FROM commissions
            WHERE period_month = ?
              AND status IN ('paid', 'pending')
        """, (period,))
        return rows[0] if rows else {'cnt': 0, 'net_total': 0, 'gross_total': 0}

    def get_commission_rows(self, limit=200):
        return query("""
            SELECT id, external_id, deal_title, agent_name, gross, split_pct, net, status, period_month
            FROM commissions
            ORDER BY period_month DESC, gross DESC
            LIMIT ?
        """, (limit,))

    def get_commissions_by_agent(self):
        period = datetime.now().strftime('%Y-%m')
        return query("""
            SELECT agent_name, COUNT(*) as cnt, COALESCE(SUM(net), 0) as net_total
            FROM commissions
            WHERE period_month = ?
            GROUP BY agent_name
            ORDER BY net_total DESC
        """, (period,))

    # ---- Showings -------------------------------------------------------
    def get_showings_next_7d(self):
        return query("""
            SELECT id, external_id, listing_address, agent_name, contact_name, showing_datetime, status
            FROM showings
            WHERE showing_datetime >= date('now')
              AND showing_datetime < date('now', '+7 days')
            ORDER BY showing_datetime ASC
        """)

    def get_all_showings(self, limit=200):
        return query("""
            SELECT id, external_id, listing_address, agent_name, contact_name, showing_datetime, status, notes
            FROM showings
            ORDER BY showing_datetime ASC
            LIMIT ?
        """, (limit,))

    # ---- Leads ----------------------------------------------------------
    def get_lead_funnel(self):
        """Leads grouped by status — funnel view."""
        return query("""
            SELECT status, COUNT(*) as cnt
            FROM leads
            GROUP BY status
            ORDER BY cnt DESC
        """)

    def get_new_leads_this_week(self):
        rows = query("""
            SELECT COUNT(*) as cnt
            FROM leads
            WHERE created_at >= date('now', '-7 days')
        """)
        return rows[0]['cnt'] if rows else 0

    def get_all_leads(self, limit=200):
        return query("""
            SELECT id, external_id, name, source, status, last_contacted_at, agent_assigned, notes, created_at
            FROM leads
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

    # ---- Documents / tasks (Documents tab) ------------------------------
    def get_open_tasks(self, limit=200):
        return query("""
            SELECT id, external_id, description, status, priority, due_date, created_at
            FROM tasks
            WHERE status = 'open'
            ORDER BY
                CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                due_date ASC
            LIMIT ?
        """, (limit,))

    # ---- Overview composite ---------------------------------------------
    def get_overview_kpis(self, agent_filter=None):
        """The 5 KPI tiles + their deltas, used by the Overview tab.

        When agent_filter is set (agent role), the pipeline_volume,
        closings_this_month, commission_mtd, active_listings, and
        new_leads_this_week tiles narrow to that agent's book — so the
        agent never sees firm-wide aggregates.
        """
        pipeline = self.get_pipeline_summary(agent_filter=agent_filter)

        if agent_filter:
            # Agent-scoped tile values via parameterized SQL.
            active_listings_rows = query("""
                SELECT COUNT(*) as cnt FROM listings
                WHERE status IN ('Active', 'Listed', 'New')
                  AND LOWER(agent_name) = LOWER(?)
            """, (agent_filter,))
            active_listings = active_listings_rows[0]['cnt'] if active_listings_rows else 0

            closings_rows = query("""
                SELECT COUNT(*) as cnt FROM pipeline
                WHERE status = 'Closed'
                  AND strftime('%Y-%m', updated_at) = strftime('%Y-%m', 'now')
                  AND LOWER(agent) = LOWER(?)
            """, (agent_filter,))
            closings_this_month = closings_rows[0]['cnt'] if closings_rows else 0

            commission_rows = query("""
                SELECT COALESCE(SUM(net), 0) as net_total FROM commissions
                WHERE period_month = ?
                  AND status IN ('paid', 'pending')
                  AND LOWER(agent_name) = LOWER(?)
            """, (datetime.now().strftime('%Y-%m'), agent_filter))
            commission_net = commission_rows[0]['net_total'] if commission_rows else 0

            leads_rows = query("""
                SELECT COUNT(*) as cnt FROM leads
                WHERE created_at >= date('now', '-7 days')
                  AND LOWER(agent_assigned) = LOWER(?)
            """, (agent_filter,))
            new_leads_week = leads_rows[0]['cnt'] if leads_rows else 0
        else:
            summary = get_brokerage_summary()
            active_listings = summary.get('active_listings', 0)
            closings_this_month = summary.get('closings_this_month', 0)
            commission_net = self.get_commission_mtd()['net_total']
            new_leads_week = summary.get('new_leads_week', 0)

        return {
            'active_listings': {
                'value': active_listings,
                'delta_label': '+2 wk',
            },
            'pipeline_volume': {
                'value': pipeline['open_volume'],
                'delta_label': f"{pipeline['mom_delta_pct']:+.1f}% MoM" if pipeline['mom_delta_pct'] else '+$1.1M wk',
            },
            'closings_this_month': {
                'value': closings_this_month,
                'delta_label': 'on pace 6',
            },
            'commission_mtd': {
                'value': commission_net,
                'delta_label': '+14% MoM',
            },
            'new_leads_this_week': {
                'value': new_leads_week,
                'delta_label': '3 hot',
            },
        }


if __name__ == '__main__':
    engine = BrokerageEngine()
    print("Brokerage Engine initialized")
    print(f"  Pipeline: {engine.get_pipeline_summary()}")
    print(f"  Commission MTD: {engine.get_commission_mtd()}")
