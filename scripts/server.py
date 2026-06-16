"""
Harbor & Vine Realty — FluentOS Server (brokerage, client-build-grade)

Flask backend for the brokerage operations dashboard. Serves the 8-tab
dashboard UI and provides REST API endpoints for the Overview KPIs,
Listings, Pipeline, Showings, Commissions, Documents, Leads tabs, plus
role-switching, alert ack, chat, admin panel, data export, and system
status.

Sandbox: binds to 127.0.0.1:8001 only.

Security posture (client-build-grade — promoted from sandbox 2026-06-16):
- Auth: enabled. Production-style sha256+salt hashing, HMAC-signed
  session tokens. Wired via templates/backend/auth.flask_middleware().
- CSRF: double-submit cookie pattern (X-CSRF-Token header echoes the
  csrf_token cookie, both signed with FLASK_SECRET_KEY). Bypassed on
  /api/login (bootstrap entry).
- FLASK_SECRET_KEY: fail-closed — server refuses to boot without it.
- Connector creds: encrypted at rest via Fernet (enc::v1: tag prefix);
  see engine/secrets_vault.py + engine/encrypt_config.py.

Usage:
    python scripts/server.py
    -> http://127.0.0.1:8001
"""

import os
import sys
import time
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT_DIR)

# Load .env BEFORE anything else so FLASK_SECRET_KEY + AIOS_MASTER_KEY
# are present when the fail-closed checks run.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
except ImportError:
    pass

from flask import Flask, request, jsonify, send_file, send_from_directory, Response, session

from engine.data_os import (
    query,
    execute,
    init_db,
    get_active_alerts,
    create_alert,
    get_brokerage_summary,
    seed_db_from_fixtures,
)
from engine.brokerage_engine import BrokerageEngine
from engine.alert_engine import AlertEngine
from templates.backend.auth import flask_middleware as auth_middleware
from templates.backend.csrf import (
    csrf_install,
    require_csrf,
    inject_csrf_into_html,
)
from templates.backend.export import Exporter
from engine import admin_module, rbac_module

# ---------------------------------------------------------------------------
# App + fail-closed secret
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)

_secret = os.environ.get('FLASK_SECRET_KEY')
if not _secret:
    sys.exit(
        "FATAL: FLASK_SECRET_KEY env var is required. "
        "Set it in .env or environment, or run scripts/startup.py "
        "to auto-generate one."
    )
app.secret_key = _secret

# Auth middleware (registers /login, /api/login, /logout + @before_request gate).
auth_middleware(app)
# CSRF cookie installer (after_request hook + decorator export).
csrf_install(app)

SERVER_VERSION = "2.0.0"
SERVER_START_TIME = time.time()

USERS_PATH = os.path.join(ROOT_DIR, 'data', 'users.json')

# Maximum characters accepted by the /api/chat endpoint (Sentinel rule 16).
MAX_CHAT_MESSAGE_LEN = 4000


def _load_users():
    """Load the users.json file. Safe defaults if it's missing."""
    if not os.path.exists(USERS_PATH):
        return {'users': []}
    try:
        with open(USERS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'users': []}


def _get_user_by_name(name):
    """Look up a user by case-insensitive name match. Returns None on miss."""
    if not name:
        return None
    target = name.strip().lower()
    for u in _load_users().get('users', []):
        if (u.get('name') or '').strip().lower() == target:
            return u
    return None


def _get_user_by_role(role, user_name=None):
    """
    Return a user matching the given role.

    When role has multiple users (e.g. 'agent' -> Jess Holloway, Tomás Vidal),
    pass user_name to disambiguate. Without user_name, returns the FIRST
    user with the role — preserved for compatibility with existing demo
    behavior (defaults to Jess for the agent role) but the role-switch path
    requires user_name explicitly for the agent role.
    """
    users = _load_users().get('users', [])
    if user_name:
        target = user_name.strip().lower()
        for u in users:
            if u.get('role') == role and (u.get('name') or '').strip().lower() == target:
                return u
        # name didn't match this role; fall back to role-only lookup so we
        # don't accidentally elevate to a different role.
    for u in users:
        if u.get('role') == role:
            return u
    return None


def _current_role():
    """Session-backed role; defaults to owner in the sandbox demo."""
    return session.get('role', 'owner')


def _strip_sensitive(user):
    """Remove password_hash / password_salt from a user dict before
    sending it to a client. Defensive — never leak hashes."""
    if not user:
        return user
    safe = {k: v for k, v in user.items()
            if k not in ('password_hash', 'password_salt')}
    return safe


def _current_user():
    role = _current_role()
    user_name = session.get('user_name')
    user = _get_user_by_role(role, user_name=user_name)
    if not user:
        user = {'name': 'Marisol Trent', 'role': 'owner', 'tools': ['dashboard']}
    return _strip_sensitive(user)


# Documented per-role resource scope. Used by every list endpoint as the
# 403 gate BEFORE any DB read; mirrored by the dashboard's visible_tabs.
# Source of truth: context/team_context.md.
_ROLE_RESOURCE_ALLOW = {
    'owner':      {'overview', 'listings', 'pipeline', 'showings',
                   'commissions', 'documents', 'leads', 'settings'},
    'president':  {'overview', 'listings', 'pipeline', 'showings',
                   'commissions', 'documents', 'leads', 'settings'},
    'accounting': {'overview', 'commissions', 'settings'},
    'tc':         {'overview', 'listings', 'pipeline', 'showings',
                   'documents', 'settings'},
    'agent':      {'overview', 'listings', 'pipeline', 'showings',
                   'documents', 'leads', 'settings'},
}


def _role_can(role, resource):
    """Return True if `role` is permitted to read `resource`."""
    return resource in _ROLE_RESOURCE_ALLOW.get(role, set())


def _scope_for_role(role):
    """Return the visible-tabs allowlist + agent-name filter (if any) per role."""
    if role == 'owner':
        return {
            'visible_tabs': ['Overview', 'Listings', 'Pipeline', 'Showings',
                             'Commissions', 'Documents', 'Leads', 'Settings'],
            'agent_filter': None,
            'hide_commissions': False,
        }
    if role == 'president':
        return {
            'visible_tabs': ['Overview', 'Listings', 'Pipeline', 'Showings',
                             'Commissions', 'Documents', 'Leads', 'Settings'],
            'agent_filter': None,
            'hide_commissions': False,  # totals only — split detail enforced in payload
        }
    if role == 'accounting':
        return {
            'visible_tabs': ['Overview', 'Commissions', 'Settings'],
            'agent_filter': None,
            'hide_commissions': False,
        }
    if role == 'tc':
        return {
            'visible_tabs': ['Overview', 'Pipeline', 'Showings', 'Documents', 'Settings'],
            'agent_filter': None,
            'hide_commissions': True,
        }
    if role == 'agent':
        user = _current_user()
        return {
            'visible_tabs': ['Overview', 'Listings', 'Pipeline', 'Showings',
                             'Documents', 'Leads', 'Settings'],
            'agent_filter': user.get('name'),
            'hide_commissions': True,
        }
    return {
        'visible_tabs': ['Overview', 'Settings'],
        'agent_filter': None,
        'hide_commissions': True,
    }


def _filter_by_agent(rows, agent_name, key='agent'):
    """Filter row dicts by an agent-name key. If agent_name is None, passthrough."""
    if not agent_name:
        return rows
    return [r for r in rows if (r.get(key) or '').lower() == agent_name.lower()]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/')
def serve_dashboard():
    dashboard_path = os.path.join(ROOT_DIR, 'outputs', 'dashboard.html')
    if not os.path.exists(dashboard_path):
        return jsonify({'error': 'Dashboard not found', 'detail': dashboard_path}), 404
    # Inject CSRF script + meta into the HTML at serve-time so the on-disk
    # dashboard.html stays untouched. The injected script wraps window.fetch
    # to attach the X-CSRF-Token header on every POST/PUT/DELETE/PATCH.
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        html = f.read()
    cookie_token = request.cookies.get('csrf_token')
    html = inject_csrf_into_html(html, csrf_token=cookie_token)
    return Response(html, mimetype='text/html; charset=utf-8')


@app.route('/brand.css')
def serve_brand_css():
    return send_from_directory(ROOT_DIR, 'brand.css')


@app.route('/manifest.json')
def serve_manifest():
    deploy_dir = os.path.join(ROOT_DIR, 'deploy')
    if os.path.exists(os.path.join(deploy_dir, 'manifest.json')):
        return send_from_directory(deploy_dir, 'manifest.json')
    return jsonify({'name': 'Harbor & Vine Realty', 'short_name': 'HarborVine'})


@app.route('/icon-192.png')
@app.route('/icon-512.png')
def serve_pwa_icon():
    import base64
    pixel = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mM89p/hPwAH"
        "vgL/hYqO3AAAAABJRU5ErkJggg=="
    )
    return Response(pixel, mimetype='image/png')


# ---------------------------------------------------------------------------
# Role switch
# ---------------------------------------------------------------------------

@app.route('/api/role_switch', methods=['POST'])
@require_csrf
def api_role_switch():
    data = request.get_json(silent=True) or {}
    role = data.get('role', 'owner')
    user_name = (data.get('user_name') or '').strip() or None
    valid = {'owner', 'president', 'accounting', 'tc', 'agent'}
    if role not in valid:
        return jsonify({'error': f'unknown role: {role}'}), 400

    # Multiple agents on the firm — Jess vs Tomás — must be disambiguated
    # so we can scope to the right book. If no user_name supplied, fall back
    # to the first agent in users.json (existing demo behavior) so the role
    # switcher stays one-click usable, but the lookup is no longer
    # first-match: it honors user_name when given.
    if role == 'agent' and user_name:
        candidate = _get_user_by_name(user_name)
        if candidate is None or candidate.get('role') != 'agent':
            return jsonify({
                'error': f'no agent named "{user_name}" found in roster',
            }), 400

    session['role'] = role
    if user_name:
        session['user_name'] = user_name
    else:
        session.pop('user_name', None)

    user = _current_user()
    scope = _scope_for_role(role)
    return jsonify({
        'role': role,
        'user': user,
        'scope': scope,
    })


@app.route('/api/me')
def api_me():
    role = _current_role()
    return jsonify({
        'role': role,
        'user': _current_user(),
        'scope': _scope_for_role(role),
    })


@app.route('/api/users')
def api_users():
    """Return the roster (name, role) for the dashboard's role-switch picker.
    Used by the dashboard to populate Jess vs Tomás as distinct options."""
    users = _load_users().get('users', [])
    return jsonify({
        'users': [
            {'name': u.get('name'), 'role': u.get('role')}
            for u in users
        ],
    })


# ---------------------------------------------------------------------------
# Overview — composed payload (KPIs + alerts + top listings)
# ---------------------------------------------------------------------------

@app.route('/api/overview')
def api_overview():
    try:
        role = _current_role()
        if not _role_can(role, 'overview'):
            return jsonify({'error': 'forbidden'}), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()

        agent_filter = scope['agent_filter']

        # B4 fix: pipeline_volume + pipeline_by_stage MUST narrow to the
        # active agent — otherwise the agent role sees firm-wide pipeline
        # totals on the Overview tab, which leaks Tomás's deals to Jess
        # (and vice versa).
        kpis = engine.get_overview_kpis(agent_filter=agent_filter)
        alerts = engine.get_active_alerts()
        top_listings = engine.get_top_listings_by_dom(5)
        pipeline_by_stage = engine.get_pipeline_by_stage(agent_filter=agent_filter)

        # Scope to agent if RBAC restricts
        if agent_filter:
            top_listings = _filter_by_agent(top_listings, agent_filter, 'agent_name')

        # Needs-your-attention surface: open high-priority tasks + a couple of
        # synthesised pain-point items the operator wants surfaced loudly.
        needs_attention = query("""
            SELECT description, priority, due_date
            FROM tasks
            WHERE status = 'open' AND priority = 'high'
            ORDER BY due_date ASC
            LIMIT 6
        """)

        user = _current_user()
        return jsonify({
            'role': role,
            'user': user,
            'scope': scope,
            'kpis': kpis,
            'alerts': alerts,
            'top_listings': top_listings,
            'pipeline_by_stage': pipeline_by_stage,
            'needs_attention': needs_attention,
            'date': datetime.now().strftime('%A, %B %-d') if os.name != 'nt'
                    else datetime.now().strftime('%A, %B %d').replace(' 0', ' '),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Tab endpoints
# ---------------------------------------------------------------------------

@app.route('/api/listings')
def api_listings():
    try:
        role = _current_role()
        if not _role_can(role, 'listings'):
            return jsonify({'error': 'forbidden'}), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()
        rows = engine.get_all_listings()
        if scope['agent_filter']:
            rows = _filter_by_agent(rows, scope['agent_filter'], 'agent_name')
        return jsonify({'listings': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pipeline')
def api_pipeline():
    try:
        role = _current_role()
        if not _role_can(role, 'pipeline'):
            return jsonify({'error': 'forbidden'}), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()
        rows = engine.get_pipeline_rows()
        if scope['agent_filter']:
            rows = _filter_by_agent(rows, scope['agent_filter'], 'agent')
        return jsonify({
            'pipeline': rows,
            'by_stage': engine.get_pipeline_by_stage(agent_filter=scope['agent_filter']),
            'count': len(rows),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/showings')
def api_showings():
    try:
        role = _current_role()
        if not _role_can(role, 'showings'):
            return jsonify({'error': 'forbidden'}), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()
        rows = engine.get_all_showings()
        if scope['agent_filter']:
            rows = _filter_by_agent(rows, scope['agent_filter'], 'agent_name')
        return jsonify({'showings': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/commissions')
def api_commissions():
    try:
        role = _current_role()
        if not _role_can(role, 'commissions'):
            return jsonify({
                'error': 'forbidden',
                'detail': 'Commissions tab is not visible for your role.',
            }), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()
        rows = engine.get_commission_rows()
        if scope['agent_filter']:
            rows = _filter_by_agent(rows, scope['agent_filter'], 'agent_name')

        # President sees totals per agent but NOT split percentages.
        if role == 'president':
            for r in rows:
                r.pop('split_pct', None)

        return jsonify({
            'commissions': rows,
            'by_agent': engine.get_commissions_by_agent(),
            'mtd': engine.get_commission_mtd(),
            'count': len(rows),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents')
def api_documents():
    try:
        role = _current_role()
        if not _role_can(role, 'documents'):
            return jsonify({'error': 'forbidden'}), 403
        engine = BrokerageEngine()
        tasks = engine.get_open_tasks()
        return jsonify({'documents': tasks, 'count': len(tasks)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/leads')
def api_leads():
    try:
        role = _current_role()
        if not _role_can(role, 'leads'):
            return jsonify({'error': 'forbidden'}), 403
        scope = _scope_for_role(role)
        engine = BrokerageEngine()
        rows = engine.get_all_leads()
        if scope['agent_filter']:
            rows = _filter_by_agent(rows, scope['agent_filter'], 'agent_assigned')
        return jsonify({
            'leads': rows,
            'funnel': engine.get_lead_funnel(),
            'count': len(rows),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Alerts ack
# ---------------------------------------------------------------------------

@app.route('/api/alerts/<int:alert_id>/ack', methods=['POST'])
@require_csrf
def api_alert_ack(alert_id):
    try:
        data = request.get_json(silent=True) or {}
        ack_by = data.get('acknowledged_by') or _current_user().get('name', 'unknown')
        existing = query("SELECT id FROM alerts WHERE id = ?", (alert_id,))
        if not existing:
            return jsonify({'error': f'Alert {alert_id} not found'}), 404
        execute("""
            UPDATE alerts
            SET acknowledged = 1, acknowledged_by = ?
            WHERE id = ?
        """, (ack_by, alert_id))
        return jsonify({'success': True, 'alert_id': alert_id, 'acknowledged_by': ack_by})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Chat (placeholder — sandbox)
# ---------------------------------------------------------------------------

@app.route('/api/chat', methods=['POST'])
@require_csrf
def api_chat():
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({'error': 'message is required'}), 400
        if len(message) > MAX_CHAT_MESSAGE_LEN:
            return jsonify({
                'error': f'message too long; max {MAX_CHAT_MESSAGE_LEN} chars'
            }), 400

        now = datetime.now().isoformat()
        execute("INSERT INTO chat_history (role, content) VALUES (?, ?)",
                ('user', message))

        if os.environ.get('ANTHROPIC_API_KEY'):
            # Real Claude wiring lands in Stage 3; sandbox keeps it placeholder.
            response_text = _placeholder_response(message, claude_available=True)
        else:
            response_text = _placeholder_response(message, claude_available=False)

        execute("INSERT INTO chat_history (role, content) VALUES (?, ?)",
                ('assistant', response_text))

        return jsonify({'response': response_text, 'timestamp': now})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _placeholder_response(message, claude_available):
    m = message.lower()
    if 'pipeline' in m or 'deals' in m:
        return ("Pipeline rollup is on the Overview and Pipeline tabs. "
                "Open volume + stage breakdown are sourced from the Google "
                "Sheets pipeline tracker.")
    if 'commission' in m or 'split' in m:
        return ("Commissions for this period live on the Commissions tab. "
                "Disputes and pending splits surface on the Overview alerts panel.")
    if 'showing' in m or 'conflict' in m:
        return ("Showings for the next 7 days are on the Showings tab. "
                "Double-bookings raise a high-severity alert and appear in "
                "the right rail.")
    if 'lead' in m:
        return ("Leads tab shows the inbound funnel. Anything silent for 5+ "
                "days raises a follow-up alert against the assigned agent.")
    if 'listing' in m or 'dom' in m:
        return ("Listings tab is sorted by days on market by default; the "
                "Overview right rail surfaces anything past the 90-day "
                "threshold.")
    if 'help' in m or 'what can you do' in m:
        return ("I'm the Harbor & Vine Realty operations assistant. I track "
                "pipeline volume, listing DOM, showings conflicts, commission "
                "disputes, and lead follow-up. Try the 8 dashboard tabs to "
                "drill in, or ask me about a specific deal.")
    if not claude_available:
        return ("The full Claude wiring lands in Stage 3 of this build. For "
                "now, all data is live on the dashboard tabs — try the "
                "Overview tab for KPIs + alerts.")
    return ("Acknowledged. The dashboard is the primary surface; the chat "
            "endpoint will become conversational once the Claude key is "
            "wired in Stage 3.")


# ---------------------------------------------------------------------------
# Admin panel (owner-only)
# ---------------------------------------------------------------------------

@app.route('/api/admin/users')
def api_admin_users():
    try:
        role = _current_role()
        if role != 'owner':
            return jsonify({'error': 'forbidden', 'detail': 'admin requires owner role'}), 403
        return jsonify({
            'users': admin_module.get_user_roster(),
            'rbac_matrix': {
                r: rbac_module.list_resources_for(r)
                for r in rbac_module.ROLE_RESOURCE_ALLOW
            },
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Data export (role-gated CSV per tab)
# ---------------------------------------------------------------------------

@app.route('/api/export/csv')
def api_export_csv():
    try:
        role = _current_role()
        tab = (request.args.get('tab') or '').strip().lower()
        if not tab:
            return jsonify({'error': 'tab query param is required'}), 400

        # Role gate: must have read access to the tab resource.
        resource = tab if tab != 'contacts' else 'overview'
        if not _role_can(role, resource):
            return jsonify({'error': 'forbidden'}), 403

        # Agent role only exports its own book.
        scope = _scope_for_role(role)
        exporter = Exporter()
        csv_data = exporter.tab_to_csv(tab, agent_filter=scope.get('agent_filter'))
        if csv_data is None:
            return jsonify({'error': f'unknown tab: {tab}'}), 400

        filename = f"harbor-vine-{tab}-{datetime.now().strftime('%Y%m%d')}.csv"
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Health (small, unauthenticated-friendly summary)
# ---------------------------------------------------------------------------

@app.route('/api/health')
def api_health():
    try:
        db_ok = False
        try:
            query("SELECT 1")
            db_ok = True
        except Exception:
            pass
        return jsonify({
            'status': 'healthy' if db_ok else 'degraded',
            'version': SERVER_VERSION,
            'database': 'connected' if db_ok else 'error',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@app.route('/api/status')
def api_status():
    try:
        uptime = time.time() - SERVER_START_TIME
        h = int(uptime // 3600); m = int((uptime % 3600) // 60); s = int(uptime % 60)

        db_ok = False
        db_err = None
        try:
            query("SELECT 1")
            db_ok = True
        except Exception as e:
            db_err = str(e)

        try:
            from tools.connectors.manager import REGISTRY
            connectors = list(REGISTRY.keys())
        except Exception:
            connectors = []

        dashboard_exists = os.path.exists(
            os.path.join(ROOT_DIR, 'outputs', 'dashboard.html')
        )

        return jsonify({
            'status': 'healthy' if db_ok else 'degraded',
            'version': SERVER_VERSION,
            'uptime': f"{h}h {m}m {s}s",
            'uptime_seconds': round(uptime, 1),
            'database': {'status': 'connected' if db_ok else 'error', 'error': db_err},
            'connectors': connectors,
            'dashboard': {'available': dashboard_exists},
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found', 'status': 404}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'error': 'Method not allowed', 'status': 405}), 405


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error', 'status': 500}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("  Harbor & Vine Realty — FluentOS Server")
    print(f"  Version: {SERVER_VERSION}")
    print(f"  Root:    {ROOT_DIR}")
    print("=" * 60)

    print("\n[init] Initializing database...")
    try:
        init_db()
        print("[init] Database ready.")
    except Exception as e:
        print(f"[init] Database error: {e}")
        sys.exit(1)

    # Sandbox: seed brokerage tables from fixtures so the dashboard isn't blank.
    try:
        seed_db_from_fixtures()
        print("[init] Fixtures seeded into brokerage tables.")
    except Exception as e:
        print(f"[init] Fixture seed WARN: {e}")

    dashboard_path = os.path.join(ROOT_DIR, 'outputs', 'dashboard.html')
    print(f"[init] Dashboard {'found' if os.path.exists(dashboard_path) else 'MISSING'} at outputs/dashboard.html")

    print("\n[start] Listening on http://127.0.0.1:8001")
    print("[start] Press Ctrl+C to stop.\n")

    # Sandbox: localhost only.
    app.run(host='127.0.0.1', port=8001, debug=False)
