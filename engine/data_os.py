"""
Harbor & Vine Realty — Data Layer
SQLite schema for brokerage operations. The connectors (Gmail, Google Calendar,
Google Sheets, QBO) feed the canonical pipeline / listings / showings / commissions
tables; the dashboard, alert engine, and brief engine read from here.

In production this DB caches the upstream sources; in sandbox it is the source
of truth (populated via tools.connectors.manager.seed_fixtures()).
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ops.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ----- Listings (brokerage inventory) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            address TEXT NOT NULL,
            list_price REAL DEFAULT 0,
            status TEXT DEFAULT 'Active',
            days_on_market INTEGER DEFAULT 0,
            agent_name TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Pipeline / deals -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS pipeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'New',
            value REAL DEFAULT 0,
            contact_name TEXT,
            agent TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Showings (calendar events scoped to property showings) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS showings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            listing_address TEXT,
            agent_name TEXT,
            contact_name TEXT,
            showing_datetime TEXT,
            status TEXT DEFAULT 'scheduled',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Commissions (QBO ledger) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            deal_external_id TEXT,
            deal_title TEXT,
            agent_name TEXT,
            gross REAL DEFAULT 0,
            split_pct REAL DEFAULT 0,
            net REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            period_month TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Contacts (people across leads / clients / referrals) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            name TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            email TEXT,
            role TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Leads (inbound lead funnel) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            name TEXT NOT NULL,
            source TEXT,
            status TEXT DEFAULT 'new',
            last_contacted_at TEXT,
            agent_assigned TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Alerts (cross-entity) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            severity TEXT DEFAULT 'medium',
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            entity_id TEXT,
            acknowledged INTEGER DEFAULT 0,
            acknowledged_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        )
    """)

    # ----- Tasks (cross-connector follow-ups) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'medium',
            due_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Daily snapshots (KPIs over time) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            active_listings INTEGER DEFAULT 0,
            pipeline_volume REAL DEFAULT 0,
            closings_count INTEGER DEFAULT 0,
            commission_total REAL DEFAULT 0,
            new_leads INTEGER DEFAULT 0,
            showings_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Chat history -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Briefs (generated morning / executive digests) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brief_type TEXT NOT NULL,
            recipient TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Audit log (exception scanner findings) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_at TEXT DEFAULT CURRENT_TIMESTAMP,
            category TEXT NOT NULL,
            entity_id TEXT,
            severity TEXT,
            title TEXT,
            body TEXT
        )
    """)

    # ----- Users (mirror of data/users.json roster; queryable for admin) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            email TEXT,
            setup_status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----- Login attempts (Atlas finding #4: per-IP rate limit on /api/login) -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            username TEXT,
            failed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_time "
        "ON login_attempts (ip, failed_at)"
    )

    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def query(sql, params=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, params or [])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def execute(sql, params=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, params or [])
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id


# ---------------------------------------------------------------------------
# Upsert helpers — used by Pattern A connectors when seed_fixtures() runs
# ---------------------------------------------------------------------------

def upsert_contact(contact: dict):
    """Idempotent insert of a contact row keyed on external_id."""
    return execute("""
        INSERT INTO contacts (external_id, name, company, phone, email, role, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            name=excluded.name,
            company=excluded.company,
            phone=excluded.phone,
            email=excluded.email,
            role=excluded.role,
            notes=excluded.notes
    """, (
        contact.get('external_id'),
        contact.get('name', ''),
        contact.get('company'),
        contact.get('phone'),
        contact.get('email'),
        contact.get('role'),
        contact.get('notes'),
    ))


def upsert_pipeline_item(item: dict):
    """Idempotent insert of a pipeline / deal row keyed on external_id."""
    now = datetime.now().isoformat()
    return execute("""
        INSERT INTO pipeline (external_id, title, status, value, contact_name, agent, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            title=excluded.title,
            status=excluded.status,
            value=excluded.value,
            contact_name=excluded.contact_name,
            agent=excluded.agent,
            notes=excluded.notes,
            updated_at=excluded.updated_at
    """, (
        item.get('external_id'),
        item.get('title', ''),
        item.get('status', 'New'),
        float(item.get('value') or 0),
        item.get('contact_name'),
        item.get('agent'),
        item.get('notes'),
        now,
    ))


def upsert_listing(listing: dict):
    """Idempotent insert of a listing row."""
    now = datetime.now().isoformat()
    return execute("""
        INSERT INTO listings (external_id, address, list_price, status, days_on_market, agent_name, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            address=excluded.address,
            list_price=excluded.list_price,
            status=excluded.status,
            days_on_market=excluded.days_on_market,
            agent_name=excluded.agent_name,
            notes=excluded.notes,
            updated_at=excluded.updated_at
    """, (
        listing.get('external_id'),
        listing.get('address', ''),
        float(listing.get('list_price') or 0),
        listing.get('status', 'Active'),
        int(listing.get('days_on_market') or 0),
        listing.get('agent_name'),
        listing.get('notes'),
        now,
    ))


def upsert_showing(showing: dict):
    """Idempotent insert of a showing row."""
    return execute("""
        INSERT INTO showings (external_id, listing_address, agent_name, contact_name, showing_datetime, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            listing_address=excluded.listing_address,
            agent_name=excluded.agent_name,
            contact_name=excluded.contact_name,
            showing_datetime=excluded.showing_datetime,
            status=excluded.status,
            notes=excluded.notes
    """, (
        showing.get('external_id'),
        showing.get('listing_address'),
        showing.get('agent_name'),
        showing.get('contact_name'),
        showing.get('showing_datetime'),
        showing.get('status', 'scheduled'),
        showing.get('notes'),
    ))


def upsert_commission(commission: dict):
    """Idempotent insert of a commission row."""
    return execute("""
        INSERT INTO commissions (external_id, deal_external_id, deal_title, agent_name, gross, split_pct, net, status, period_month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            deal_external_id=excluded.deal_external_id,
            deal_title=excluded.deal_title,
            agent_name=excluded.agent_name,
            gross=excluded.gross,
            split_pct=excluded.split_pct,
            net=excluded.net,
            status=excluded.status,
            period_month=excluded.period_month
    """, (
        commission.get('external_id'),
        commission.get('deal_external_id'),
        commission.get('deal_title'),
        commission.get('agent_name'),
        float(commission.get('gross') or 0),
        float(commission.get('split_pct') or 0),
        float(commission.get('net') or 0),
        commission.get('status', 'pending'),
        commission.get('period_month'),
    ))


def upsert_lead(lead: dict):
    """Idempotent insert of a lead row."""
    return execute("""
        INSERT INTO leads (external_id, name, source, status, last_contacted_at, agent_assigned, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            name=excluded.name,
            source=excluded.source,
            status=excluded.status,
            last_contacted_at=excluded.last_contacted_at,
            agent_assigned=excluded.agent_assigned,
            notes=excluded.notes
    """, (
        lead.get('external_id'),
        lead.get('name', ''),
        lead.get('source'),
        lead.get('status', 'new'),
        lead.get('last_contacted_at'),
        lead.get('agent_assigned'),
        lead.get('notes'),
    ))


def upsert_task(task: dict):
    """Idempotent insert of a task row."""
    return execute("""
        INSERT INTO tasks (external_id, description, status, priority, due_date)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
            description=excluded.description,
            status=excluded.status,
            priority=excluded.priority,
            due_date=excluded.due_date
    """, (
        task.get('external_id'),
        task.get('description', ''),
        task.get('status', 'open'),
        task.get('priority', 'medium'),
        task.get('due_date'),
    ))


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------

def create_alert(severity, alert_type, title, body=None, entity_id=None):
    """Insert an alert row. Returns the new alert id."""
    return execute("""
        INSERT INTO alerts (severity, type, title, body, entity_id)
        VALUES (?, ?, ?, ?, ?)
    """, (severity, alert_type, title, body, entity_id))


def get_active_alerts(severity=None):
    sql = "SELECT * FROM alerts WHERE resolved_at IS NULL"
    params = []
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    sql += " ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, created_at DESC"
    return query(sql, params)


# ---------------------------------------------------------------------------
# Brokerage summary (replaces fleet_summary)
# ---------------------------------------------------------------------------

def get_brokerage_summary():
    """One-shot rollup used by the dashboard Overview tab."""
    rows = query("""
        SELECT
            (SELECT COUNT(*) FROM listings WHERE status IN ('Active', 'Listed', 'New')) as active_listings,
            (SELECT COALESCE(SUM(value), 0) FROM pipeline WHERE status NOT IN ('Closed', 'Lost', 'Cancelled')) as pipeline_volume,
            (SELECT COUNT(*) FROM pipeline WHERE status = 'Closed' AND strftime('%Y-%m', updated_at) = strftime('%Y-%m', 'now')) as closings_this_month,
            (SELECT COALESCE(SUM(net), 0) FROM commissions WHERE status = 'paid' AND period_month = strftime('%Y-%m', 'now')) as commission_mtd,
            (SELECT COUNT(*) FROM leads WHERE created_at >= date('now', '-7 days')) as new_leads_week,
            (SELECT COUNT(*) FROM showings WHERE showing_datetime >= date('now') AND showing_datetime < date('now', '+7 days')) as showings_next_7d
    """)
    return rows[0] if rows else {}


# ---------------------------------------------------------------------------
# Sandbox seeding — populate brokerage tables from fixtures/*.json
# ---------------------------------------------------------------------------

def seed_db_from_fixtures():
    """
    Sandbox-only. Reads the four Stage 1 fixtures (gmail / gcal / sheets / qbo)
    and inserts brokerage rows into the new tables (listings, pipeline,
    showings, commissions, leads, contacts, tasks).

    Drives the dashboard with realistic data without a real API call.
    """
    fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'fixtures')
    init_db()

    # -- Sheets pipeline -> pipeline + listings ----------------------------
    sheets_path = os.path.join(fixtures_dir, 'sheets_pipeline.json')
    if os.path.exists(sheets_path):
        with open(sheets_path, 'r', encoding='utf-8') as f:
            sheets = json.load(f)
        for row in sheets.get('pipeline', []):
            # Idempotent pipeline row
            upsert_pipeline_item({
                'external_id': row.get('external_id'),
                'title': row.get('title'),
                'status': row.get('status', 'New'),
                'value': row.get('value', 0),
                'contact_name': row.get('contact_name'),
                'agent': row.get('agent'),
                'notes': row.get('notes'),
            })
            # Active rows also surface as listings (status in active set)
            status = (row.get('status') or '').lower()
            if status in ('listed', 'active', 'new', 'showing'):
                # Synthesize a DOM from the row index so the wireframe's
                # top-DOM widget has variety; deterministic so reseeds match.
                ext_id = row.get('external_id', '')
                try:
                    seed = int(ext_id.rsplit('-', 1)[-1])
                except ValueError:
                    seed = 30
                dom_seed = ((seed * 7) % 95) + 5   # 5..99
                upsert_listing({
                    'external_id': 'listing:' + str(ext_id),
                    'address': row.get('title'),
                    'list_price': row.get('value', 0),
                    'status': row.get('status', 'Active'),
                    'days_on_market': dom_seed,
                    'agent_name': row.get('agent'),
                    'notes': row.get('notes'),
                })

    # -- Gcal -> showings + tasks ----------------------------------------
    gcal_path = os.path.join(fixtures_dir, 'gcal.json')
    if os.path.exists(gcal_path):
        with open(gcal_path, 'r', encoding='utf-8') as f:
            gcal = json.load(f)
        for t in gcal.get('tasks', []):
            upsert_task(t)
            desc = t.get('description', '')
            if desc.lower().startswith('showing'):
                # Parse "Showing — <address> (<agent>, w/ <client>)"
                body = desc.split('—', 1)[-1].strip() if '—' in desc else desc
                address = body.split('(')[0].strip() if '(' in body else body
                agent = ''
                client = ''
                if '(' in body and ')' in body:
                    paren = body[body.index('(') + 1: body.rindex(')')]
                    pieces = paren.split(',')
                    agent = pieces[0].strip()
                    if len(pieces) > 1:
                        client = pieces[1].replace('w/', '').strip()
                upsert_showing({
                    'external_id': t.get('external_id'),
                    'listing_address': address,
                    'agent_name': agent,
                    'contact_name': client,
                    'showing_datetime': t.get('due_date'),
                    'status': t.get('status', 'scheduled'),
                    'notes': desc,
                })

    # -- Gmail -> contacts + leads + tasks --------------------------------
    gmail_path = os.path.join(fixtures_dir, 'gmail.json')
    if os.path.exists(gmail_path):
        with open(gmail_path, 'r', encoding='utf-8') as f:
            gmail = json.load(f)
        for c in gmail.get('contacts', []):
            upsert_contact(c)
            role = (c.get('role') or '').lower()
            if 'lead' in role:
                upsert_lead({
                    'external_id': 'lead:' + str(c.get('external_id', '')),
                    'name': c.get('name'),
                    'source': 'gmail',
                    'status': 'hot' if 'buyer' in role else 'warm',
                    'last_contacted_at': None,
                    'agent_assigned': None,
                    'notes': c.get('notes'),
                })
        for t in gmail.get('tasks', []):
            upsert_task(t)

    # -- QBO -> commissions + tasks --------------------------------------
    qbo_path = os.path.join(fixtures_dir, 'qbo_commissions.json')
    if os.path.exists(qbo_path):
        with open(qbo_path, 'r', encoding='utf-8') as f:
            qbo = json.load(f)
        # Raw rows live under _meta.raw_rows
        for r in qbo.get('_meta', {}).get('raw_rows', []):
            upsert_commission({
                'external_id': r.get('external_id'),
                'deal_external_id': r.get('deal_id'),
                'deal_title': r.get('deal_title'),
                'agent_name': r.get('agent_name'),
                'gross': r.get('gross_commission', 0),
                'split_pct': r.get('split_pct', 0),
                'net': r.get('net_to_agent', 0),
                'status': r.get('status', 'pending'),
                'period_month': r.get('period_month'),
            })
        for t in qbo.get('tasks', []):
            upsert_task(t)

    return True


if __name__ == '__main__':
    init_db()
    seed_db_from_fixtures()
    print(f"Database initialized + fixtures seeded at {os.path.abspath(DB_PATH)}")
