"""
gmail_connector.py — Gmail data connector (sandbox / offline-branch)

In the sandbox build, this connector NEVER makes a live API call. connect()
returns False so the connector stays `active: false` in data/connectors.json;
pull() reads from fixtures/<fixture>.json (filename resolved via the
`fixture` field in connectors.json — defaults to "<name>.json") and returns
the canonical {contacts, pipeline, tasks, metrics} shape so the dashboard
sees real data without any external dependency.

Phase D Stage 2/3 will replace connect() with the OAuth2 flow; pull() will
swap the fixture read for a Gmail API call. The return shape is the contract.
"""

import json
from pathlib import Path

from tools.connectors.base_connector import BaseConnector

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

EMPTY_RESULT = {"contacts": [], "pipeline": [], "tasks": [], "metrics": []}


class GmailConnector(BaseConnector):
    name = "gmail"

    def connect(self, credentials: dict) -> bool:
        """
        Sandbox stub: never actually connects. Returns False so the
        connector stays inactive in data/connectors.json. In Phase D
        Stage 2/3 this will run the OAuth2 flow and set `active: True`.
        """
        return False

    def pull(self) -> dict:
        """
        Offline branch: load fixture and return it in the canonical shape.
        On any error (missing file, bad JSON), returns the empty shape;
        never raises.
        """
        try:
            cfg = self.read_config()
            fixture_name = cfg.get("fixture") or f"{self.name}.json"
            fixture_path = FIXTURES_DIR / fixture_name
            with open(fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {
                "contacts": data.get("contacts", []) or [],
                "pipeline": data.get("pipeline", []) or [],
                "tasks":    data.get("tasks", [])    or [],
                "metrics":  data.get("metrics", [])  or [],
            }
            self.mark_synced()
            return result
        except Exception:
            return dict(EMPTY_RESULT)
