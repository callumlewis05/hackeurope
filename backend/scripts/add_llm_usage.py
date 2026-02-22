#!/usr/bin/env python3
"""
Small idempotent migration helper to add the `llm_usage` JSONB column to the
`interactions` table.

Usage:
  # Use DATABASE_URL env var
  DATABASE_URL=postgresql://... python backend/scripts/add_llm_usage.py

  # Or pass DB URL explicitly
  python backend/scripts/add_llm_usage.py --database-url postgresql://...

Options:
  --dry-run         Print SQL statements and exit without applying.
  --create-indexes  Also create optional GIN and provider indexes (safe / IF NOT EXISTS).
  --yes             Skip interactive confirmation (use with caution).
  --verbose         Emit more logs.

Notes:
 - The SQL uses `IF NOT EXISTS` so running this script multiple times is safe.
 - Always back up your DB before running migrations in production.
 - This script is deliberately small and dependency-minimal; it uses psycopg2.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import traceback

try:
    import psycopg2
    from psycopg2 import sql
except Exception as exc:  # pragma: no cover - runtime environment may differ
    print("ERROR: psycopg2 is required to run this script.", file=sys.stderr)
    print(
        "Install it in your environment (e.g. pip install psycopg2-binary).",
        file=sys.stderr,
    )
    raise

MIGRATION_SQL = textwrap.dedent(
    """
    -- Add nullable JSONB column to store LLM usage metadata (provider, model,
    -- estimated_tokens, response_time_ms, raw provider meta, etc).
    ALTER TABLE interactions
      ADD COLUMN IF NOT EXISTS llm_usage JSONB NULL;
    """
).strip()

INDEX_SQLS = [
    # General jsonb GIN index (uncomment/create if you expect many JSONB queries)
    "CREATE INDEX IF NOT EXISTS idx_interactions_llm_usage_gin ON interactions USING gin (llm_usage);",
    # Index the 'provider' key for fast equality queries (llm_usage->>'provider')
    "CREATE INDEX IF NOT EXISTS idx_interactions_llm_usage_provider ON interactions ((llm_usage ->> 'provider'));",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Idempotent migration: add interactions.llm_usage JSONB column"
    )
    p.add_argument(
        "--database-url",
        "-d",
        help="Database URL (overrides DATABASE_URL env var).",
        default=os.getenv("DATABASE_URL"),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements and exit without applying them.",
    )
    p.add_argument(
        "--create-indexes",
        action="store_true",
        help="Also create recommended indexes (GIN and provider path).",
    )
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive confirmation prompt.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )
    return p.parse_args()


def confirm(prompt: str = "Apply migration? [y/N]: ") -> bool:
    try:
        resp = input(prompt).strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def main() -> int:
    args = parse_args()
    db_url = args.database_url

    if not db_url:
        print(
            "ERROR: No DATABASE_URL provided (env var or --database-url).",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        print("DRY RUN - SQL to be executed:")
        print("-" * 60)
        print(MIGRATION_SQL)
        if args.create_indexes:
            print()
            print("-- Index statements:")
            for s in INDEX_SQLS:
                print(s)
        print("-" * 60)
        print("Exiting without applying (dry-run).")
        return 0

    print("Migration: add `llm_usage` JSONB column to `interactions` table")
    print("Database:", db_url)
    print()

    if not args.yes:
        print(
            "WARNING: Ensure you have a backup of the target database before proceeding."
        )
        if not confirm():
            print("Aborted by user.")
            return 3

    # Execute statements
    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        print("ERROR: Failed to connect to database:", exc, file=sys.stderr)
        return 4

    try:
        with conn:
            with conn.cursor() as cur:
                if args.verbose:
                    print("Executing ALTER TABLE to add llm_usage column...")
                # Execute the migration SQL
                cur.execute(MIGRATION_SQL)
                if args.verbose:
                    print("ALTER TABLE executed.")

                if args.create_indexes:
                    if args.verbose:
                        print("Creating optional indexes (IF NOT EXISTS)...")
                    for stmt in INDEX_SQLS:
                        cur.execute(stmt)
                    if args.verbose:
                        print("Index statements executed.")

        print("Migration applied successfully.")
        print("Confirmed: `llm_usage` column should now exist (nullable).")
        if args.create_indexes:
            print("Indexes (if requested) were created with IF NOT EXISTS.")
        return 0
    except Exception as exc:
        print("ERROR: Migration failed.", file=sys.stderr)
        traceback.print_exc()
        # Attempt to hint at rollback, but ALTER TABLE with IF NOT EXISTS is safe to re-run.
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
