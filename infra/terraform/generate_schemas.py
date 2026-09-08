#!/usr/bin/env python
"""
Generates the BigQuery table schema JSON that main.tf reads, from the
single source of truth in bigquery_sink.py.

Why generate instead of hand-writing: the Python sink and Terraform would
otherwise each carry their own copy of the schema and drift apart
silently — the classic way a load job starts failing in production after
someone adds a column in one place. Run this whenever the *_SCHEMA
constants change; CI checks the output is committed and current.

    python infra/terraform/generate_schemas.py
"""

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SINK = REPO_ROOT / "backend/src/infrastructure/warehouse/bigquery_sink.py"
OUT_DIR = pathlib.Path(__file__).resolve().parent / "schemas"

# Python constant -> BigQuery table name
TABLES = {
    "REVIEWS_SCHEMA": "reviews",
    "CLUSTERS_SCHEMA": "clusters",
    "UPLOAD_METRICS_SCHEMA": "upload_metrics",
}


def main() -> int:
    if not SINK.exists():
        print(f"error: cannot find {SINK}", file=sys.stderr)
        return 1

    source = SINK.read_text(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for const, table in TABLES.items():
        match = re.search(rf"^{const} = \[(.*?)^\]", source, re.S | re.M)
        if not match:
            print(f"error: {const} not found in {SINK.name}", file=sys.stderr)
            return 1

        fields = re.findall(r'\("(\w+)",\s*"(\w+)"\)', match.group(1))
        if not fields:
            print(f"error: no fields parsed from {const}", file=sys.stderr)
            return 1

        schema = [{"name": n, "type": t, "mode": "NULLABLE"} for n, t in fields]
        target = OUT_DIR / f"{table}.json"
        target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(REPO_ROOT)} ({len(schema)} fields)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
