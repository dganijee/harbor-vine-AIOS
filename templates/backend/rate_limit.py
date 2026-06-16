"""
Harbor & Vine — Login rate-limiter (in-process, SQLite-backed).

Per-IP throttle on /api/login. Fixes Atlas finding #4 (LOW): argon2 cost
alone isn't a brute-force defense without a per-IP attempt cap. Don't
defer to "the reverse proxy" — the sandbox runs without one, and some
client deploys won't sit behind one either.

Policy
------
- MAX_ATTEMPTS = 5 failed attempts in WINDOW_SECONDS = 900 (15 min) per IP.
- On the 6th attempt: return 429 + a `Retry-After` header (seconds to wait).
- A successful login clears the IP's failure counter.

Storage
-------
SQLite table `login_attempts(ip TEXT, username TEXT, failed_at TIMESTAMP)`
in the project's ops.db. Cheap, persistent across restarts (a brute-force
loop can't escape by restarting the server), no Redis dep.

Felix standing rule #38: rate-limit auth-related endpoints from day one.
"""

import time
import sqlite3
import os
from datetime import datetime, timedelta


# Resolve DB path the same way engine/data_os.py does so the table lives
# alongside the existing schema.
_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "data", "ops.db"))


def _conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_table():
    """Create login_attempts table if missing. Safe to call repeatedly."""
    conn = _conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                username TEXT,
                failed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_time "
            "ON login_attempts (ip, failed_at)"
        )
        conn.commit()
    finally:
        conn.close()


class LoginRateLimiter:
    """Per-IP failed-login throttle backed by SQLite."""

    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 900  # 15 minutes

    def __init__(self):
        init_table()

    def _count_recent(self, ip):
        """Count failures from this IP within the window. Returns (count, oldest_ts)."""
        if not ip:
            return 0, None
        cutoff = (datetime.utcnow() - timedelta(seconds=self.WINDOW_SECONDS)).isoformat()
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT failed_at FROM login_attempts "
                "WHERE ip = ? AND failed_at >= ? "
                "ORDER BY failed_at ASC",
                (ip, cutoff),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return 0, None
        return len(rows), rows[0]["failed_at"]

    def check(self, ip):
        """Return (allowed: bool, retry_after_seconds: int).

        allowed=True means caller may proceed with auth verification.
        allowed=False means the IP has hit MAX_ATTEMPTS failures within
        the window; return the seconds until the oldest in-window
        failure expires so the client gets a useful Retry-After header.
        """
        if not ip:
            return True, 0
        count, oldest = self._count_recent(ip)
        if count < self.MAX_ATTEMPTS:
            return True, 0
        # Compute Retry-After: when does the oldest in-window failure expire?
        try:
            oldest_dt = datetime.fromisoformat(oldest)
        except Exception:
            return False, self.WINDOW_SECONDS
        expires_at = oldest_dt + timedelta(seconds=self.WINDOW_SECONDS)
        delta = (expires_at - datetime.utcnow()).total_seconds()
        return False, max(1, int(delta))

    def record_failure(self, ip, username=None):
        """Insert a failure row. No-op if ip is falsy."""
        if not ip:
            return
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO login_attempts (ip, username, failed_at) "
                "VALUES (?, ?, ?)",
                (ip, (username or "")[:64], datetime.utcnow().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def clear(self, ip):
        """Wipe all in-window failures for this IP — called on success."""
        if not ip:
            return
        conn = _conn()
        try:
            conn.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
            conn.commit()
        finally:
            conn.close()


# Single module-level instance — cheap, no per-request construction.
limiter = LoginRateLimiter()
