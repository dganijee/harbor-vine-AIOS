#!/usr/bin/env python3
"""
Harbor & Vine — CSV data export.

Adapted from bundle 1's reference exporter, retargeted to our DB path
(data/harbor-vine.db) and brokerage tables. Wired in scripts/server.py
behind /api/export/csv?tab=<...> with role gating.
"""

import csv
import io
import os
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = _ROOT / "data" / "harbor-vine.db"

# Map a tab slug -> a (table, agent_filter_column or None) pair so the
# server can pass the role-scoped filter through to the exporter.
TAB_TO_TABLE = {
    "listings": ("listings", "agent_name"),
    "pipeline": ("pipeline", "agent"),
    "showings": ("showings", "agent_name"),
    "commissions": ("commissions", "agent_name"),
    "leads": ("leads", "agent_assigned"),
    "contacts": ("contacts", None),
    "tasks": ("tasks", None),
    "alerts": ("alerts", None),
}


class Exporter:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or DEFAULT_DB)

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def get_columns(self, table):
        c = self._conn()
        try:
            cursor = c.execute(f'PRAGMA table_info("{table}")')
            return [r[1] for r in cursor.fetchall()]
        finally:
            c.close()

    def get_tables(self):
        c = self._conn()
        try:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            c.close()

    def table_to_csv(self, table, agent_filter=None, agent_column=None, limit=None):
        """Export a table to CSV. Optionally restrict to agent_column = agent_filter."""
        cols = self.get_columns(table)
        if not cols:
            return ""

        c = self._conn()
        try:
            col_list = ", ".join(f'"{x}"' for x in cols)
            sql = f'SELECT {col_list} FROM "{table}"'
            params = []
            if agent_filter and agent_column and agent_column in cols:
                sql += f' WHERE LOWER("{agent_column}") = LOWER(?)'
                params.append(agent_filter)
            if limit:
                sql += f' LIMIT {int(limit)}'
            rows = c.execute(sql, params).fetchall()
        finally:
            c.close()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        for r in rows:
            writer.writerow([r[col] for col in cols])
        return buf.getvalue()

    def tab_to_csv(self, tab_slug, agent_filter=None):
        """Tab-aware export. Maps tab slug -> table + optional agent col."""
        spec = TAB_TO_TABLE.get(tab_slug.lower())
        if not spec:
            return None
        table, agent_col = spec
        return self.table_to_csv(table, agent_filter=agent_filter, agent_column=agent_col)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Harbor & Vine data export")
    p.add_argument("tab", help="Tab slug (or table name) to export")
    p.add_argument("--agent", help="Filter by agent name")
    p.add_argument("--output", "-o", help="Output file path")
    args = p.parse_args()

    e = Exporter()
    data = e.tab_to_csv(args.tab, agent_filter=args.agent) \
        or e.table_to_csv(args.tab, agent_filter=args.agent)
    if not data:
        print(f"No data for tab/table: {args.tab}")
        sys.exit(1)

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            f.write(data)
        print(f"Exported to {args.output}")
    else:
        sys.stdout.write(data)
