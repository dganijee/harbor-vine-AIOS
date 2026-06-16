"""
Harbor & Vine backend helpers.

Shared utilities used by auth.py + csrf.py + rate_limit.py.
"""

import os
import json
from pathlib import Path


def cookie_secure(req=None):
    """Decide whether to set the Secure flag on cookies.

    Atlas finding #3 fix: env-gated, with sandbox defaulting to False so
    HTTP loopback dev still works while production flips it on. Order:

      1. `AIOS_SECURE_COOKIES` env var truthy → True (operator override).
      2. Current request served over HTTPS (`request.is_secure`) → True.
      3. `data/config.json -> cookies.secure` true → True.
      4. Otherwise → False (sandbox / HTTP-loopback default).
    """
    env = (os.environ.get("AIOS_SECURE_COOKIES", "") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        if req is not None and getattr(req, "is_secure", False):
            return True
    except Exception:
        pass
    try:
        # Resolve config.json relative to this file (templates/backend → up 2).
        cfg_path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            return bool(cfg.get("cookies", {}).get("secure", False))
    except Exception:
        pass
    return False


def cookie_samesite():
    """SameSite policy. Lax is always safe; can be tightened via config."""
    try:
        cfg_path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            val = cfg.get("cookies", {}).get("samesite")
            if val in ("Strict", "Lax", "None"):
                return val
    except Exception:
        pass
    return "Lax"
