"""Standalone script to purge all data from the database.

Usage:
    python purge_db.py

This drops ALL tables managed by SQLModel and recreates them empty.
⚠️  This is destructive — every row in every table will be lost.
"""

import sys

from src.db import purge_all_data


def main() -> None:
    confirm = input(
        "⚠️  This will DELETE ALL DATA in the database. Type 'yes' to confirm: "
    )
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(1)

    purge_all_data()
    print("✅ All tables purged and recreated.")


if __name__ == "__main__":
    main()
