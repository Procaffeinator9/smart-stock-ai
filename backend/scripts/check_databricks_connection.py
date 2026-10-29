"""MANUAL connectivity check against YOUR Databricks SQL Warehouse. Not run by tests or the app.

Runs one read-only query (current catalog/schema and a literal) and lists tables in the
configured schema, reporting which of the five SmartStock tables are present. It does not
create, modify, or write anything.

Uses the same bounded timeouts and retries as the API (DATABRICKS_SOCKET_TIMEOUT_SECONDS,
DATABRICKS_RETRY_MAX_ATTEMPTS, DATABRICKS_RETRY_MAX_DURATION_SECONDS), so an unreachable
workspace fails within about a minute instead of 15. Errors are printed with the hostname,
HTTP path, token, and URLs redacted.

Note: running this starts your SQL Warehouse if it is stopped, which may incur cost.

Usage (from backend/, with backend/.env filled in):
    python scripts/check_databricks_connection.py
"""

import sys

from app.core.config import get_databricks_settings
from app.core.log_redaction import install_secret_redaction
from app.db.databricks import (
    DatabricksNotConfiguredError,
    InvalidIdentifierError,
    databricks_connection,
    qualified_schema,
    sanitize_error,
)
from app.synthetic.loader import TABLE_SPECS

EXPECTED_TABLES = [spec.name for spec in TABLE_SPECS]


def main() -> int:
    settings = get_databricks_settings()
    install_secret_redaction(settings)
    try:
        schema = qualified_schema(settings)
    except InvalidIdentifierError as exc:
        print(f"Invalid DATABRICKS_CATALOG / DATABRICKS_SCHEMA: {exc}", file=sys.stderr)
        return 2
    print(
        f"Timeouts: socket {settings.socket_timeout_seconds:.0f}s, up to {settings.retry_max_attempts} attempts "
        f"within {settings.retry_max_duration_seconds:.0f}s, statement {settings.statement_timeout_seconds}s"
    )
    try:
        with databricks_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_catalog(), current_schema(), 1")
            catalog, current_schema, one = cursor.fetchone()
            print(f"Connected. catalog={catalog} schema={current_schema} probe={one}")

            cursor.execute(f"SHOW TABLES IN {schema}")
            # SHOW TABLES columns: database, tableName, isTemporary.
            tables = sorted(row.tableName if hasattr(row, "tableName") else row[1] for row in cursor.fetchall())
            print(f"Tables in {settings.catalog}.{settings.schema_name}: {', '.join(tables) or '(none)'}")
    except DatabricksNotConfiguredError as exc:
        print(f"Not configured: {exc}. Fill in backend/.env first.", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Connection failed: {sanitize_error(exc, settings)}", file=sys.stderr)
        return 1

    missing = [t for t in EXPECTED_TABLES if t not in tables]
    if missing:
        print(f"Missing SmartStock tables: {', '.join(missing)}. Run databricks/sql/00-06 in the SQL editor.")
        return 3
    print("All five SmartStock tables exist. Row counts and column definitions were not checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
