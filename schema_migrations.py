"""
Schema migration support.

Tracks a ``schema_version`` in ``PRAGMA user_version`` and applies
idempotent, ordered migration steps. Adding a migration:

1. bump ``SCHEMA_VERSION``,
2. append a ``(version, migrate_fn)`` tuple to ``MIGRATIONS``,
3. the runner applies anything newer than the stored version in order.

Every migration runs inside its own transaction and is committed only on
success, so a failed migration never leaves a half-applied schema.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

SCHEMA_VERSION = 2


def _migration_2_add_status_columns(conn) -> None:
    """Add application-status columns (older databases lack them)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "status" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'new'")
    if "applied_at" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN applied_at TEXT")


MIGRATIONS: list[tuple[int, Callable[[Any], None]]] = [
    (2, _migration_2_add_status_columns),
]


def get_schema_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_schema_version(conn, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()


def migrate(conn) -> None:
    """Apply all pending migrations in order, then stamp the schema version."""
    current = get_schema_version(conn)
    for version, fn in sorted(MIGRATIONS):
        if version > current:
            fn(conn)
            conn.commit()
            set_schema_version(conn, version)
            print(f"[migration] applied schema v{version}")
