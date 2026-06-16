"""
base_connector.py — Abstract base for all data connectors

Every connector implements connect() and pull().
The refresh cycle calls pull() on all active connectors.
Adding new connectors later = implement these two methods.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

CONNECTORS_FILE = Path(__file__).parent.parent.parent / "data" / "connectors.json"


class BaseConnector(ABC):
    name: str = "base"

    def read_config(self) -> dict:
        with open(CONNECTORS_FILE) as f:
            cfg = json.load(f)["connectors"].get(self.name, {})
        # Transparent decryption: any field whose value is tagged
        # `enc::v1:` is decrypted on the fly. Plain values pass through.
        # This keeps connector code agnostic to encryption-at-rest.
        try:
            from engine.secrets_vault import decrypt, is_encrypted
            def _walk(obj):
                if isinstance(obj, dict):
                    return {k: _walk(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_walk(v) for v in obj]
                if isinstance(obj, str) and is_encrypted(obj):
                    return decrypt(obj)
                return obj
            return _walk(cfg)
        except ImportError:
            # secrets_vault not installed → return raw (sandbox-safe default).
            return cfg

    def write_config(self, updates: dict):
        with open(CONNECTORS_FILE) as f:
            data = json.load(f)
        data["connectors"][self.name].update(updates)
        with open(CONNECTORS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def mark_synced(self):
        self.write_config({"last_sync": datetime.now(timezone.utc).isoformat()})

    def is_active(self) -> bool:
        return self.read_config().get("active", False)

    @abstractmethod
    def connect(self, credentials: dict) -> bool:
        """Validate credentials and activate connector. Returns True if successful."""
        pass

    @abstractmethod
    def pull(self) -> dict:
        """Pull latest data. Returns dict with keys: contacts, pipeline, metrics, tasks."""
        pass
