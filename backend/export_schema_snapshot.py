"""
Export a schema-only snapshot from the live Supabase/Postgres database.

This script reads backend/.env, connects to the database, and prints a
JSON snapshot containing tables, columns, constraints, indexes, triggers,
and public functions. It does not export table data.

Usage:
    python export_schema_snapshot.py
    python export_schema_snapshot.py --output schema_snapshot.json
    python export_schema_snapshot.py --schemas public auth
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


DEFAULT_SCHEMAS = ["public", "auth"]


def load_environment() -> None:
    """Load environment variables from backend/.env if present."""
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)


def get_database_url() -> str:
    """Resolve the database URL from common environment variable names."""
    candidates = ["DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"]
    for key in candidates:
        value = os.getenv(key)
        if value:
            return value
    raise RuntimeError(
        "No database URL found. Set DATABASE_URL in backend/.env or your shell."
    )


def fetch_rows(cur: RealDictCursor, query: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
    cur.execute(query, params)
    return [dict(row) for row in cur.fetchall()]


def build_snapshot(conn, schemas: List[str]) -> Dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        snapshot: Dict[str, Any] = {"schemas": schemas}

        snapshot["tables"] = fetch_rows(
            cur,
            """
            select table_schema, table_name, table_type
            from information_schema.tables
            where table_schema = any(%s)
            order by table_schema, table_name
            """,
            (schemas,),
        )

        snapshot["columns"] = fetch_rows(
            cur,
            """
            select table_schema, table_name, column_name, ordinal_position,
                   data_type, is_nullable, column_default, character_maximum_length,
                   numeric_precision, numeric_scale
            from information_schema.columns
            where table_schema = any(%s)
            order by table_schema, table_name, ordinal_position
            """,
            (schemas,),
        )

        snapshot["constraints"] = fetch_rows(
            cur,
            """
            select n.nspname as table_schema,
                   c.relname as table_name,
                   con.conname as constraint_name,
                   con.contype as constraint_type,
                   pg_get_constraintdef(con.oid) as definition
            from pg_constraint con
            join pg_class c on c.oid = con.conrelid
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s)
            order by n.nspname, c.relname, con.conname
            """,
            (schemas,),
        )

        snapshot["indexes"] = fetch_rows(
            cur,
            """
            select schemaname as table_schema,
                   tablename as table_name,
                   indexname as index_name,
                   indexdef as definition
            from pg_indexes
            where schemaname = any(%s)
            order by schemaname, tablename, indexname
            """,
            (schemas,),
        )

        snapshot["triggers"] = fetch_rows(
            cur,
            """
            select n.nspname as table_schema,
                   c.relname as table_name,
                   t.tgname as trigger_name,
                   pg_get_triggerdef(t.oid) as definition,
                   p.proname as function_name
            from pg_trigger t
            join pg_class c on c.oid = t.tgrelid
            join pg_namespace n on n.oid = c.relnamespace
            join pg_proc p on p.oid = t.tgfoid
            where not t.tgisinternal
              and n.nspname = any(%s)
            order by n.nspname, c.relname, t.tgname
            """,
            (schemas,),
        )

        snapshot["functions"] = fetch_rows(
            cur,
            """
            select n.nspname as schema_name,
                   p.proname as function_name,
                   pg_get_function_identity_arguments(p.oid) as arguments,
                   pg_get_function_result(p.oid) as returns,
                   pg_get_functiondef(p.oid) as definition
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public'
            order by p.proname
            """,
            (),
        )

        return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a schema-only database snapshot.")
    parser.add_argument(
        "--schemas",
        nargs="+",
        default=DEFAULT_SCHEMAS,
        help="Schemas to include in the snapshot (default: public auth)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON snapshot to a file.",
    )
    args = parser.parse_args()

    load_environment()
    database_url = get_database_url()

    with psycopg2.connect(database_url) as conn:
        snapshot = build_snapshot(conn, args.schemas)

    rendered = json.dumps(snapshot, indent=2, default=str)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote schema snapshot to {args.output}")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
