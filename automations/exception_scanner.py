"""
Harbor & Vine — Exception scanner automation.

Cron entry point. Runs AuditEngine.scan_exceptions() and persists the
findings to the audit_log table.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.audit_engine import AuditEngine
from engine.data_os import init_db


def run():
    init_db()
    engine = AuditEngine()
    summary = engine.scan_exceptions()
    print(f"[exception_scanner] {summary['total']} exception(s) logged")
    return summary


if __name__ == "__main__":
    run()
