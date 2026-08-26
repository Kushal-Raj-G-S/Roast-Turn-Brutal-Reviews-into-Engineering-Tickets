"""
Restore the app-owned schema from a schema snapshot JSON file.

This script is intended for a fresh Supabase project. It replays the public
schema only: tables, constraints, indexes, functions, and triggers captured
by export_schema_snapshot.py. Supabase-managed auth tables are intentionally
ignored because they are created and maintained by Supabase itself.

Usage:
    python restore_schema_from_snapshot.py --dry-run
    python restore_schema_from_snapshot.py
    python restore_schema_from_snapshot.py --snapshot schema_snapshot.json --env-file .env
    python restore_schema_from_snapshot.py --database-url postgresql://... --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


DEFAULT_SNAPSHOT = Path(__file__).with_name("schema_snapshot.json")
DEFAULT_ENV = Path(__file__).with_name(".env")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_environment(env_file: Path | None) -> None:
    if env_file and env_file.exists():
        load_dotenv(env_file, override=False)
    elif DEFAULT_ENV.exists():
        load_dotenv(DEFAULT_ENV, override=False)
    else:
        load_dotenv(override=False)


def get_database_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        value = os.getenv(key)
        if value:
            return value
    raise RuntimeError(
        "No database URL found. Set DATABASE_URL or pass --database-url."
    )


def read_snapshot(snapshot_path: Path) -> Dict[str, Any]:
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def public_tables(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in snapshot.get("tables", []) if row["table_schema"] == "public"]


def public_columns(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in snapshot.get("columns", []):
        if row["table_schema"] != "public":
            continue
        grouped[row["table_name"]].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda item: item["ordinal_position"])
    return grouped


def public_constraints(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in snapshot.get("constraints", []):
        if row["table_schema"] != "public":
            continue
        grouped[row["table_name"]].append(row)
    return grouped


def public_indexes(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in snapshot.get("indexes", []):
        if row["table_schema"] != "public":
            continue
        grouped[row["table_name"]].append(row)
    return grouped


def restore_triggers(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in snapshot.get("triggers", []):
        if row["table_schema"] not in {"public", "auth"}:
            continue
        grouped[f"{row['table_schema']}.{row['table_name']}"].append(row)
    return grouped


def public_functions(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in snapshot.get("functions", []) if row["schema_name"] == "public"]


def build_table_sql(table_name: str, columns: Sequence[Dict[str, Any]]) -> str:
    column_lines: List[str] = []
    for column in columns:
        line_parts = [quote_ident(column["column_name"]), column["data_type"]]
        if column["is_nullable"] == "NO":
            line_parts.append("NOT NULL")
        if column["column_default"] is not None:
            line_parts.append(f"DEFAULT {column['column_default']}")
        column_lines.append(" ".join(line_parts))

    joined = ",\n  ".join(column_lines)
    return f"CREATE TABLE IF NOT EXISTS public.{quote_ident(table_name)} (\n  {joined}\n);"


def extract_sequence_name(column_default: str | None) -> str | None:
    if not column_default:
        return None
    match = re.search(r"nextval\('([^']+)'::regclass\)", column_default)
    if not match:
        return None
    return match.group(1)


def build_constraint_sql(table_name: str, constraint_name: str, definition: str) -> str:
    return (
        f"ALTER TABLE public.{quote_ident(table_name)} "
        f"ADD CONSTRAINT {quote_ident(constraint_name)} {definition};"
    )


def normalize_trigger_definition(definition: str) -> str:
    normalized = definition.rstrip(";")
    normalized = re.sub(
        r"EXECUTE FUNCTION\s+([A-Za-z_][A-Za-z0-9_]*)\(",
        r"EXECUTE FUNCTION public.\1(",
        normalized,
    )
    return normalized


def build_index_sql(index_name: str, index_def: str, constraint_names: Iterable[str]) -> str | None:
    if index_name in constraint_names:
        return None
    return index_def + ";"


def build_trigger_sql(table_schema: str, table_name: str, trigger_name: str, definition: str) -> List[str]:
    return [
        f"DROP TRIGGER IF EXISTS {quote_ident(trigger_name)} ON {table_schema}.{quote_ident(table_name)};",
        normalize_trigger_definition(definition) + ";",
    ]


def collect_constraint_sql(snapshot: Dict[str, Any]) -> List[str]:
    constraints_by_table = public_constraints(snapshot)
    statements: List[str] = []

    for constraint_type in ["p", "u", "c", "f"]:
        for table_name in sorted(constraints_by_table):
            for constraint in constraints_by_table[table_name]:
                if constraint["constraint_type"] != constraint_type:
                    continue
                statements.append(
                    build_constraint_sql(
                        table_name,
                        constraint["constraint_name"],
                        constraint["definition"],
                    )
                )

    return statements


def collect_sql(snapshot: Dict[str, Any]) -> List[str]:
    statements: List[str] = []
    tables = public_tables(snapshot)
    columns_by_table = public_columns(snapshot)
    constraints_by_table = public_constraints(snapshot)
    indexes_by_table = public_indexes(snapshot)
    triggers_by_table = restore_triggers(snapshot)
    functions = public_functions(snapshot)

    statements.append('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    sequence_names = sorted(
        {
            sequence_name
            for columns in columns_by_table.values()
            for sequence_name in [extract_sequence_name(column["column_default"]) for column in columns]
            if sequence_name
        }
    )

    for sequence_name in sequence_names:
        statements.append(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name};")

    for table in sorted(tables, key=lambda row: row["table_name"]):
        table_name = table["table_name"]
        table_columns = columns_by_table.get(table_name, [])
        if not table_columns:
            continue
        statements.append(build_table_sql(table_name, table_columns))

    for function in sorted(functions, key=lambda row: row["function_name"]):
        statements.append(function["definition"].rstrip(";") + ";")

    statements.extend(collect_constraint_sql(snapshot))

    constraint_names = {
        constraint["constraint_name"]
        for table_constraints in constraints_by_table.values()
        for constraint in table_constraints
    }

    for table_name in sorted(indexes_by_table):
        for index in indexes_by_table[table_name]:
            sql = build_index_sql(index["index_name"], index["definition"], constraint_names)
            if sql:
                statements.append(sql)

    for table_key in sorted(triggers_by_table):
        table_schema, table_name = table_key.split(".", 1)
        for trigger in triggers_by_table[table_key]:
            statements.extend(
                build_trigger_sql(
                    table_schema,
                    table_name,
                    trigger["trigger_name"],
                    trigger["definition"],
                )
            )

    return statements


def get_existing_objects(cur: RealDictCursor) -> Dict[str, set[str]]:
    cur.execute(
        """
        select
          (n.nspname || '.' || c.relname) as table_key,
          con.conname as constraint_name
        from pg_constraint con
        join pg_class c on c.oid = con.conrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
        """
    )
    constraints = {row["constraint_name"] for row in cur.fetchall()}

    cur.execute(
        """
        select
          n.nspname as table_schema,
          c.relname as table_name,
          t.tgname as trigger_name
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_namespace n on n.oid = c.relnamespace
        where not t.tgisinternal
          and n.nspname = 'public'
        """
    )
    triggers = {
        f"{row['table_schema']}.{row['table_name']}.{row['trigger_name']}"
        for row in cur.fetchall()
    }

    return {"constraints": constraints, "triggers": triggers}


def run_sql(cur: RealDictCursor, statements: Sequence[str], dry_run: bool) -> None:
    if dry_run:
        for statement in statements:
            print(statement)
        return

    for statement in statements:
        cur.execute(statement)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore public schema from schema_snapshot.json")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Path to the schema snapshot JSON file.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV,
        help="Path to an env file containing DATABASE_URL.",
    )
    parser.add_argument(
        "--database-url",
        help="Explicit database URL; overrides env file and environment variables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL that would be executed without touching the database.",
    )
    args = parser.parse_args()

    snapshot = read_snapshot(args.snapshot)
    statements = collect_sql(snapshot)

    if args.dry_run:
        print(f"-- dry run: {len(statements)} statements generated from {args.snapshot}")
        run_sql(None, statements, dry_run=True)
        return 0

    load_environment(args.env_file)
    database_url = get_database_url(args.database_url)

    with psycopg2.connect(database_url) as conn:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            run_sql(cur, statements, dry_run=False)
        conn.commit()

    print(f"Applied {len(statements)} schema statements from {args.snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
