"""MANUAL loader: validate synthetic CSVs and insert them into workspace.smartstock_retail.

Never drops, truncates, recreates, or alters tables. The five-table load is NOT atomic:
each batch is committed separately, and a failure part-way leaves earlier batches in place.

Usage (from backend/, with the virtual environment active):
    python scripts/load_synthetic_data.py --validate-only   # local CSV checks only; no connection
    python scripts/load_synthetic_data.py                   # validate, confirm, then load into empty tables
    python scripts/load_synthetic_data.py --allow-nonempty  # resume: insert only rows whose keys are missing

Exit codes: 0 success, 1 load failure / count mismatch / aborted, 2 Databricks not configured,
3 validation failed (CSV or table definition), 4 refused because target tables are not empty.
"""

import argparse
import sys
import time
from pathlib import Path

from app.core.config import get_databricks_settings
from app.core.log_redaction import install_secret_redaction
from app.db.databricks import DatabricksNotConfiguredError, databricks_connection, redact
from app.synthetic.loader import (
    DEFAULT_BATCH_SIZE,
    TABLE_SPECS,
    TARGET_CATALOG,
    TARGET_SCHEMA,
    LoaderError,
    NonEmptyTargetError,
    PreflightError,
    SchemaMismatchError,
    preflight,
    run_load,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
MAX_BATCH_SIZE = 5000


def _batch_size(text: str) -> int:
    value = int(text)
    if not 1 <= value <= MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_BATCH_SIZE}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=BACKEND_DIR / "data" / "synthetic")
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=f"rows per INSERT statement (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="load into tables that already have rows using insert-only MERGE keyed on the primary key "
        "(and inventory's snapshot_date/store_id/product_id); existing rows are never updated or duplicated",
    )
    parser.add_argument("--validate-only", action="store_true", help="run the local CSV preflight and exit")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    print(f"Phase 1/4: validating CSVs in {args.data_dir} (local, nothing is written)")
    try:
        tables = preflight(args.data_dir)
    except PreflightError as exc:
        print(f"ERROR: {exc}. Nothing was written.", file=sys.stderr)
        for line in exc.errors:
            print(f"  {line}", file=sys.stderr)
        return 3
    for spec in TABLE_SPECS:
        print(f"  {spec.name:<16} {len(tables[spec.name].rows):>8,} rows OK")
    print("  Constraints, primary keys, inventory natural key, and foreign keys: OK")

    if args.validate_only:
        print("--validate-only: stopping before connecting to Databricks.")
        return 0

    settings = get_databricks_settings()
    install_secret_redaction(settings)
    target = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"
    if (settings.catalog, settings.schema_name) != (TARGET_CATALOG, TARGET_SCHEMA):
        # The DDL scripts create the tables in workspace.smartstock_retail; the API reads the configured
        # catalog/schema. Refuse to load somewhere the API would not read (or the DDL did not create).
        print(
            f"ERROR: DATABRICKS_CATALOG/DATABRICKS_SCHEMA are {settings.catalog}.{settings.schema_name}, but this "
            f"loader and databricks/sql target {target}. Nothing was written.",
            file=sys.stderr,
        )
        return 3
    if not args.yes:
        mode = "insert-only MERGE (non-empty tables allowed)" if args.allow_nonempty else "INSERT (tables must be empty)"
        print(f"\nAbout to write to your configured Databricks workspace, schema {target}, mode: {mode}, batch size {args.batch_size}.")
        print("This starts your SQL Warehouse if it is stopped and is not atomic across tables.")
        try:
            answer = input("Type 'load' to continue: ")
        except EOFError:
            answer = ""
        if answer.strip().lower() != "load":
            print("Aborted. Nothing was written.")
            return 1

    started = time.monotonic()
    try:
        with databricks_connection(settings) as connection, connection.cursor() as cursor:
            results = run_load(
                cursor,
                tables,
                batch_size=args.batch_size,
                allow_nonempty=args.allow_nonempty,
                out=lambda line: print(redact(line, settings), flush=True),
            )
    except DatabricksNotConfiguredError as exc:
        print(f"ERROR: {exc}. Fill in backend/.env first. Nothing was written.", file=sys.stderr)
        return 2
    except SchemaMismatchError as exc:
        print(f"ERROR: {exc}. Nothing was written.", file=sys.stderr)
        for line in exc.errors:
            print(f"  {redact(line, settings)}", file=sys.stderr)
        return 3
    except NonEmptyTargetError as exc:
        print(f"ERROR: {exc}. Nothing was written.", file=sys.stderr)
        print(
            "  If these rows came from an earlier partial run of this loader, re-run with --allow-nonempty "
            "to insert only the missing rows.",
            file=sys.stderr,
        )
        return 4
    except LoaderError as exc:  # LoadFailedError, CountMismatchError
        print(f"ERROR: {redact(str(exc), settings)}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Connection/auth errors: type and redacted message only (no hostname, HTTP path, token, or URLs).
        print(f"ERROR: {type(exc).__name__}: {redact(str(exc), settings)}", file=sys.stderr)
        print("  Rows written before this error (if any) remain committed.", file=sys.stderr)
        return 1

    print(f"Done. All row counts match ({time.monotonic() - started:,.0f}s).")
    print(f"  {'table':<16} {'csv':>8} {'before':>8} {'inserted':>9} {'skipped':>8} {'after':>8}")
    for r in results:
        print(f"  {r.table:<16} {r.csv_rows:>8,} {r.count_before:>8,} {r.inserted:>9,} {r.skipped:>8,} {r.count_after:>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
