"""
manager.py — Runs all active connectors for Harbor & Vine Realty.

Called on startup and by the heartbeat / refresh cycle.
Returns summary of what was pulled.

Sandbox note: all 4 connectors ship with `active: false` in
data/connectors.json and connect() returns False for each. To prime the
SQLite cache and dashboard with realistic fixture data in the sandbox,
use seed_fixtures() — it bypasses the is_active gate and calls pull() on
every connector in REGISTRY.
"""

import json
from pathlib import Path

from tools.connectors.gmail_connector import GmailConnector
from tools.connectors.google_calendar import GoogleCalendarConnector
from tools.connectors.google_sheets import GoogleSheetsConnector
from tools.connectors.qbo_connector import QBOConnector

REGISTRY = {
    "gmail":           GmailConnector,
    "google_calendar": GoogleCalendarConnector,
    "google_sheets":   GoogleSheetsConnector,
    "qbo":             QBOConnector,
}

_CONNECTORS_FILE = Path(__file__).parent.parent.parent / "data" / "connectors.json"


def run_all_connectors() -> dict:
    """Pull from all active connectors. Returns summary keyed by connector name."""
    results = {}

    if not _CONNECTORS_FILE.exists():
        return results

    with open(_CONNECTORS_FILE) as f:
        config = json.load(f)

    for name, ConnectorClass in REGISTRY.items():
        connector_config = config["connectors"].get(name, {})
        if connector_config.get("active"):
            try:
                connector = ConnectorClass()
                result = connector.pull()
                results[name] = {
                    "status": "success",
                    "counts": {k: len(v) for k, v in result.items()},
                }
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}

    return results


def activate_connector(name: str, credentials: dict) -> bool:
    """Activate a connector with provided credentials. In sandbox this always
    returns False because each connector's connect() is a stub."""
    if name not in REGISTRY:
        return False
    connector = REGISTRY[name]()
    return connector.connect(credentials)


def seed_fixtures() -> dict:
    """
    Sandbox-only helper. Iterates REGISTRY and calls pull() on each connector
    REGARDLESS of `is_active()` so the SQLite cache + dashboard see fixture
    data offline. This is the explicit bypass that makes the sandbox dry-run
    look like a live system without ever touching a real API.

    DO NOT call this in a production build — it pulls even from connectors
    the operator hasn't opted into. Production paths must use
    run_all_connectors() which respects the active flag.
    """
    results = {}
    for name, ConnectorClass in REGISTRY.items():
        try:
            connector = ConnectorClass()
            result = connector.pull()
            results[name] = {
                "status": "success",
                "counts": {k: len(v) for k, v in result.items()},
            }
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)}
    return results


def get_connection_instructions(tool_name: str) -> dict:
    """
    Returns what the brokerage operator needs to provide for each tool.
    Used by the onboarding flow to tell the operator exactly what to share
    (and with whom) to wire each connector live.
    """
    instructions = {
        "gmail": {
            "connector": "gmail",
            "steps": [
                "Share access to the Harbor & Vine team mailbox (Marisol + team) by adding our service account as a delegate (Gmail settings -> Accounts -> 'Grant access to your account').",
                "Confirm the brokerage owner-account email so we know which mailbox to read.",
                "Authorize the read/label scopes when the consent screen pops up.",
            ],
            "credentials_needed": ["mailbox_email", "oauth_consent"],
        },
        "google_calendar": {
            "connector": "google_calendar",
            "steps": [
                "Open Google Calendar -> Settings -> the brokerage shared calendar -> 'Share with specific people'.",
                "Add our service account email with 'See all event details' permission.",
                "Send us the calendar's email address (usually the brokerage Gmail). We need it to scope queries to your calendar only.",
            ],
            "credentials_needed": ["calendar_id", "oauth_consent"],
        },
        "google_sheets": {
            "connector": "google_sheets",
            "steps": [
                "Open the Harbor & Vine pipeline tracker sheet -> Share -> add our service account email as Viewer (or Editor if you want us to write back deal updates).",
                "Send us the sheet URL.",
                "Tell us which tab holds the live pipeline rows (we'll auto-detect column headers).",
            ],
            "credentials_needed": ["sheet_url"],
            "optional": ["tab_name"],
        },
        "qbo": {
            "connector": "qbo",
            "steps": [
                "In QuickBooks Online -> Manage Users -> add our app as a read-only user on the commissions company file.",
                "Approve the OAuth2 consent screen when prompted (we'll send the link).",
                "Confirm which QBO entity (realm) holds the commission ledger so we read the right book.",
            ],
            "credentials_needed": ["realm_id", "oauth_consent"],
        },
    }

    tool_lower = tool_name.lower()
    for key in instructions:
        if key in tool_lower or tool_lower in key:
            return instructions[key]

    # Fuzzy aliases
    if any(w in tool_lower for w in ["sheet", "gsheet", "google sheet"]):
        return instructions["google_sheets"]
    if any(w in tool_lower for w in ["calendar", "gcal", "google cal"]):
        return instructions["google_calendar"]
    if any(w in tool_lower for w in ["mail", "inbox", "email"]):
        return instructions["gmail"]
    if any(w in tool_lower for w in ["quickbooks", "qb", "books", "accounting"]):
        return instructions["qbo"]

    return {
        "connector": None,
        "steps": [
            f"I don't have a direct connector for {tool_name} yet. "
            "I'll track manually and we can add it later."
        ],
        "credentials_needed": [],
    }
