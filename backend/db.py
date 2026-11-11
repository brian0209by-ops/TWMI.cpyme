import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).resolve().parents[1] / "database" / "migrations"


def connect():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)


def migrate():
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(140000)")
        db.execute("CREATE TABLE IF NOT EXISTS schema_migration (name text PRIMARY KEY)")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if not db.execute("SELECT 1 FROM schema_migration WHERE name=%s", (path.name,)).fetchone():
                db.execute(path.read_text())
                db.execute("INSERT INTO schema_migration VALUES (%s)", (path.name,))
