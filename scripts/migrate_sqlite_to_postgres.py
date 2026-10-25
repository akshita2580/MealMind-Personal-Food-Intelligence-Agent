"""Copy MealMind's SQLModel tables from SQLite into an empty PostgreSQL DB.

Configure DATABASE_URL with the PostgreSQL destination, then run:

    python scripts/migrate_sqlite_to_postgres.py [path/to/swiggy.db]

The command refuses to copy into a PostgreSQL database containing any rows.
It does not delete or modify the SQLite source.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel, create_engine
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import models  # noqa: F401 - register all table metadata


DEFAULT_SOURCE = PROJECT_ROOT / "data" / "swiggy.db"


def _postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return "postgresql+psycopg://" + raw_url[len("postgres://"):]
    if raw_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw_url[len("postgresql://"):]
    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url
    raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgres:// or postgresql://).")


def migrate(source_path: Path, destination_url: str) -> dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    # Parse once to fail early on malformed URLs without printing credentials.
    make_url(destination_url)
    source_engine = create_engine(f"sqlite:///{source_path.resolve().as_posix()}")
    destination_engine = create_engine(destination_url, pool_pre_ping=True)
    copied: dict[str, int] = {}

    try:
        SQLModel.metadata.create_all(destination_engine)
        source_tables = set(inspect(source_engine).get_table_names())
        tables = [table for table in SQLModel.metadata.sorted_tables if table.name in source_tables]

        # Refuse a partial merge. This keeps repeat runs from duplicating data
        # or overwriting a PostgreSQL database that already has application data.
        with destination_engine.connect() as connection:
            for table in tables:
                count = connection.execute(select(text("count(*)")).select_from(table)).scalar_one()
                if count:
                    raise RuntimeError(
                        f"Destination table {table.name!r} is not empty; migration stopped without copying rows."
                    )

        with source_engine.connect() as source, destination_engine.begin() as destination:
            for table in tables:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    destination.execute(table.insert(), rows)
                copied[table.name] = len(rows)

            # Explicit IDs bypass PostgreSQL sequences during inserts. Advance
            # serial/identity sequences to the largest migrated primary key.
            for table in tables:
                for column in table.primary_key.columns:
                    if not column.autoincrement or not column.type.python_type is int:
                        continue
                    sequence = destination.execute(
                        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                        {"table_name": table.name, "column_name": column.name},
                    ).scalar_one_or_none()
                    if not sequence:
                        continue
                    quoted_table = destination_engine.dialect.identifier_preparer.quote(table.name)
                    quoted_column = destination_engine.dialect.identifier_preparer.quote(column.name)
                    max_value, has_rows = destination.execute(
                        text(f"SELECT MAX({quoted_column}), COUNT(*) > 0 FROM {quoted_table}")
                    ).one()
                    if has_rows:
                        destination.execute(
                            text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                            {"sequence_name": sequence, "value": max_value},
                        )

        return copied
    finally:
        source_engine.dispose()
        destination_engine.dispose()


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        parser.error("Set DATABASE_URL to your PostgreSQL destination before running the migration.")
    try:
        destination_url = _postgres_url(raw_url)
        copied = migrate(args.source, destination_url)
    except Exception as exc:
        # Never echo the connection URL; it may contain credentials.
        parser.exit(1, f"Migration failed: {exc}\n")

    print("Migration completed. SQLite source was left unchanged.")
    for table_name, row_count in copied.items():
        print(f"  {table_name}: {row_count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
