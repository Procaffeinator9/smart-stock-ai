"""MANUAL, READ-ONLY validation of the Databricks read path against YOUR workspace (Phase 4B).

Stages (run one at a time with --stage; nothing runs without --stage):
  schema  Metadata and planning only: DESCRIBE DETAIL (size, file count), SELECT ... LIMIT 0
          (exact column types the connector reports), and EXPLAIN (scan plan). Reads no rows.
  sample  SELECT ... LIMIT 100 per table: raw value types, strict conversion, and row-by-row
          comparison with the local CSVs by primary key. At most 500 rows.
  full    One refresh through the real DatabricksRepository (all 176,317 rows): strict type,
          constraint, key, and foreign-key validation, per-query timing, freshness metadata,
          record-for-record comparison with the CSVs, and key analytics comparison.
  errors  One SELECT against a table that does not exist, to check error classification and
          redaction. Reads nothing.

Every statement must start with SELECT, DESCRIBE DETAIL, or EXPLAIN; anything else is refused
before it reaches the warehouse. The data-source setting is not changed. Output never includes
the token, hostname, HTTP path, storage locations, or URLs.

Usage (from backend/, with the virtual environment active):
    python scripts/validate_databricks_read.py --stage schema --dry-run   # print SQL, no connection
    python scripts/validate_databricks_read.py --stage schema             # asks you to type 'read'

Exit codes: 0 all checks passed, 1 a check failed or aborted, 2 not configured, 3 refused.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.analytics.inventory import inventory_positions
from app.analytics.stock import is_late, is_open
from app.core.config import get_databricks_settings
from app.core.log_redaction import install_secret_redaction
from app.data.conversion import ResultValidationError, convert_rows, validate_description
from app.data.dataset import RetailDataset
from app.data.repository import CsvRepository, DatabricksRepository, DataSourceUnavailableError
from app.db.databricks import (
    DatabricksNotConfiguredError,
    InvalidIdentifierError,
    classify_error,
    connection_options,
    databricks_connection,
    qualified_table,
    redact,
    sanitize_error,
)
from app.synthetic.loader import TABLE_SPECS

BACKEND_DIR = Path(__file__).resolve().parents[1]
STAGES = ("schema", "sample", "full", "errors")
SAMPLE_ROWS = 100
READ_ONLY_PREFIXES = ("SELECT ", "DESCRIBE DETAIL ", "EXPLAIN SELECT ")
MISSING_TABLE = "smartstock_validation_missing_table"
_ANY_URI = re.compile(r"\b[a-z][a-z0-9+.-]*:/{1,2}\S*", re.IGNORECASE)
_PRIMARY_KEY = {spec.name: spec.primary_key for spec in TABLE_SPECS}


class WriteRefusedError(RuntimeError):
    pass


# --- Statements ----------------------------------------------------------------------------------


def statements(stage: str, settings) -> list[str]:
    """Exact SQL a stage runs, in order (the 'full' stage runs these through the repository)."""
    selects = {spec.name: f"SELECT {', '.join(spec.column_names)} FROM {qualified_table(settings, spec.name)}" for spec in TABLE_SPECS}
    if stage == "schema":
        return (
            [f"DESCRIBE DETAIL {qualified_table(settings, s.name)}" for s in TABLE_SPECS]
            + [f"{selects[s.name]} LIMIT 0" for s in TABLE_SPECS]
            + [f"EXPLAIN {selects[s.name]}" for s in TABLE_SPECS]
        )
    if stage == "sample":
        return [f"{selects[s.name]} LIMIT {SAMPLE_ROWS}" for s in TABLE_SPECS]
    if stage == "full":
        return [selects[s.name] for s in TABLE_SPECS]
    return [f"SELECT 1 FROM {qualified_table(settings, MISSING_TABLE)}"]


def client_info(settings) -> dict[str, Any]:
    """How results will be fetched, for comparing reports. Uses the connector's own pyarrow switch."""
    from importlib.metadata import PackageNotFoundError, version

    from databricks.sql.backend import thrift_backend

    arrow = thrift_backend.pyarrow is not None  # the connector requests Arrow results only if True
    try:
        pyarrow_version = version("pyarrow") if arrow else None
    except PackageNotFoundError:  # pragma: no cover - importable but without metadata
        pyarrow_version = "unknown"
    options = connection_options(settings)
    return {
        "connector": version("databricks-sql-connector"),
        "pyarrow": pyarrow_version,
        "result_format": "arrow" if arrow else "row-based",
        "pandas_conversion": arrow and not options["_disable_pandas"],
        "use_cloud_fetch": options["use_cloud_fetch"],
    }


def ensure_read_only(sql: str) -> None:
    if not sql.startswith(READ_ONLY_PREFIXES) or ";" in sql:
        raise WriteRefusedError(f"Refusing non-read-only statement: {sql[:60]}")


class TimedReadOnlyCursor:
    """Wraps a connector cursor: refuses anything but reads and records per-statement timings."""

    def __init__(self, cursor, timings: list[dict]):
        self._cursor = cursor
        self._timings = timings

    @property
    def description(self):
        return self._cursor.description

    def execute(self, sql: str, parameters=None):
        ensure_read_only(sql)
        started = time.perf_counter()
        result = self._cursor.execute(sql)
        self._timings.append({"sql": sql, "execute_s": round(time.perf_counter() - started, 3), "fetch_s": 0.0, "rows": 0})
        return result

    def _record_fetch(self, started: float, rows: list) -> list:
        self._timings[-1]["fetch_s"] = round(self._timings[-1]["fetch_s"] + time.perf_counter() - started, 3)
        self._timings[-1]["rows"] += len(rows)
        return rows

    def fetchall(self):
        started = time.perf_counter()
        return self._record_fetch(started, self._cursor.fetchall())

    def fetchmany(self, size):
        started = time.perf_counter()
        return self._record_fetch(started, self._cursor.fetchmany(size))


def timed_connect(timings: list[dict]):
    """A connection factory for DatabricksRepository whose cursors are read-only and timed."""

    @contextmanager
    def connect(settings):
        with databricks_connection(settings) as connection:

            class Connection:
                @contextmanager
                def cursor(self, **kwargs):
                    with connection.cursor(**kwargs) as cursor:
                        yield TimedReadOnlyCursor(cursor, timings)

            yield Connection()

    return connect


# --- Stages --------------------------------------------------------------------------------------


def _row_dicts(cursor) -> list[dict[str, Any]]:
    names = [d[0] for d in cursor.description or []]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _plan_summary(plan: str, settings) -> list[str]:
    """Operator lines of an EXPLAIN plan with storage paths and URIs removed."""
    lines = []
    for line in plan.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=="):
            continue
        cleaned = _ANY_URI.sub("[path]", redact(stripped, settings))
        cleaned = re.sub(r"\[[^\]]*\[path\][^\]]*\]", "[path]", cleaned)
        lines.append(cleaned[:140])
    return lines[:12]


def stage_schema(cursor, settings, report: dict) -> list[str]:
    problems: list[str] = []
    details, plans = {}, {}
    for spec in TABLE_SPECS:
        cursor.execute(f"DESCRIBE DETAIL {qualified_table(settings, spec.name)}")
        detail = (_row_dicts(cursor) or [{}])[0]
        # Location is deliberately not read: it is a storage path.
        details[spec.name] = {k: detail.get(k) for k in ("format", "numFiles", "sizeInBytes", "clusteringColumns")}
        if str(detail.get("format", "")).lower() != "delta":
            problems.append(f"{spec.name}: format is {detail.get('format')!r}, expected delta")
    for spec in TABLE_SPECS:
        cursor.execute(statements("full", settings)[TABLE_SPECS.index(spec)] + " LIMIT 0")
        try:
            validate_description(spec, cursor.description)
        except ResultValidationError as exc:
            problems.extend(exc.problems)
        cursor.fetchall()
    for spec in TABLE_SPECS:
        cursor.execute("EXPLAIN " + statements("full", settings)[TABLE_SPECS.index(spec)])
        rows = cursor.fetchall()
        plans[spec.name] = _plan_summary(str(rows[0][0]) if rows else "", settings)
    report["schema"] = {"details": details, "plans": plans}
    total_bytes = sum(int(d["sizeInBytes"] or 0) for d in details.values())
    report["schema"]["total_size_bytes"] = total_bytes
    return problems


def stage_sample(cursor, settings, csv: RetailDataset, report: dict) -> list[str]:
    problems: list[str] = []
    raw_types: dict[str, dict[str, list[str]]] = {}
    for spec in TABLE_SPECS:
        cursor.execute(f"{statements('full', settings)[TABLE_SPECS.index(spec)]} LIMIT {SAMPLE_ROWS}")
        validate_description(spec, cursor.description)
        rows = cursor.fetchall()
        raw_types[spec.name] = {
            c.name: sorted({type(row[i]).__name__ for row in rows}) for i, c in enumerate(spec.columns)
        }
        errors: list[str] = []
        converted = convert_rows(spec, rows, errors)
        problems.extend(errors[:5])
        expected = {getattr(r, spec.primary_key): r for r in getattr(csv, spec.name)}
        record_type = type(next(iter(expected.values())))
        for record in converted:
            key = record[spec.primary_key]
            if key not in expected:
                problems.append(f"{spec.name} {key}: not in the CSV data")
            elif record_type(**record) != expected[key]:
                problems.append(f"{spec.name} {key}: differs from the CSV row")
    report["sample"] = {"rows_per_table": SAMPLE_ROWS, "raw_value_types": raw_types}
    return problems[:20]


def key_metrics(ds: RetailDataset) -> dict[str, Any]:
    as_of = ds.as_of
    positions = inventory_positions(ds, as_of)
    cost = {p.product_id: p.unit_cost for p in ds.products}
    latest = [s for s in ds.inventory if s.snapshot_date == as_of]
    return {
        "as_of": as_of.isoformat(),
        "rows": {name: len(getattr(ds, name)) for name in _PRIMARY_KEY},
        "status_counts": dict(sorted(Counter(p.status for p in positions).items())),
        "inventory_value_at_cost": str(sum((cost[s.product_id] * s.quantity_on_hand for s in latest), Decimal(0))),
        "open_purchase_orders": sum(is_open(po) for po in ds.purchase_orders),
        "overdue_purchase_orders": sum(is_open(po) and is_late(po, as_of) for po in ds.purchase_orders),
        "open_po_quantity_on_positions": sum(p.open_po_quantity for p in positions),
        "total_revenue": str(sum((s.unit_selling_price * s.quantity_sold for s in ds.sales), Decimal(0))),
        "total_units_sold": sum(s.quantity_sold for s in ds.sales),
        "top_8_by_severity": [f"{p.store_id}/{p.product_id}" for p in sorted(positions, key=lambda p: p.severity_key)[:8]],
    }


def compare_datasets(csv: RetailDataset, db: RetailDataset) -> list[str]:
    problems = []
    for name, key in _PRIMARY_KEY.items():
        left, right = Counter(getattr(csv, name)), Counter(getattr(db, name))
        if left != right:
            only_csv = sorted(getattr(r, key) for r in (left - right).elements())[:3]
            only_db = sorted(getattr(r, key) for r in (right - left).elements())[:3]
            problems.append(f"{name}: records differ (CSV-only {only_csv}, Databricks-only {only_db})")
    sort_key = lambda p: (p.store_id, p.product_id)  # noqa: E731
    if sorted(inventory_positions(csv, csv.as_of), key=sort_key) != sorted(inventory_positions(db, db.as_of), key=sort_key):
        problems.append("inventory positions (status, cover, open POs) differ")
    return problems


def stage_full(settings, csv: RetailDataset, report: dict) -> list[str]:
    timings: list[dict] = []
    repo = DatabricksRepository(
        settings, connect=timed_connect(timings), start=lambda fn: fn(), wait_seconds=0, refresh_seconds=3600
    )
    started = time.perf_counter()
    try:
        db = repo.dataset()
    except DataSourceUnavailableError as exc:
        report["full"] = {"refresh_s": round(time.perf_counter() - started, 2), "queries": timings, "error": str(exc)}
        return [f"repository refresh failed: {exc}"]
    refresh_s = round(time.perf_counter() - started, 2)
    freshness = repo.freshness()
    csv_metrics, db_metrics = key_metrics(csv), key_metrics(db)
    problems = compare_datasets(csv, db)
    problems += [f"metric {k}: CSV {csv_metrics[k]} != Databricks {db_metrics[k]}" for k in csv_metrics if csv_metrics[k] != db_metrics[k]]
    report["full"] = {
        "refresh_s": refresh_s,
        "queries": [{**t, "sql": t["sql"].split(" FROM ")[-1]} for t in timings],
        "rows_total": sum(t["rows"] for t in timings),
        "freshness": {"stale": freshness.stale, "loaded_at": freshness.loaded_at.isoformat() if freshness.loaded_at else None,
                      "last_error": freshness.last_error},
        "metrics": db_metrics,
    }
    return problems


def stage_errors(cursor, settings, report: dict) -> list[str]:
    try:
        cursor.execute(statements("errors", settings)[0])
        cursor.fetchall()
    except WriteRefusedError:
        raise
    except Exception as exc:
        sanitized = sanitize_error(exc, settings)
        leaks = [s for s in (settings.server_hostname, settings.http_path) if s and s in sanitized]
        if settings.token and settings.token.get_secret_value() in sanitized:
            leaks.append("token")
        report["errors"] = {"category": classify_error(exc), "sanitized_message": sanitized}
        problems = [] if classify_error(exc) == "not_found" else [f"expected category not_found, got {classify_error(exc)}"]
        return problems + (["sanitized message still contains a secret"] if leaks else [])
    return ["querying a missing table unexpectedly succeeded"]


# --- CLI -----------------------------------------------------------------------------------------

IMPACT = {
    "schema": "15 metadata/planning statements; reads no table rows.",
    "sample": f"5 SELECTs with LIMIT {SAMPLE_ROWS}; at most {5 * SAMPLE_ROWS} rows.",
    "full": "5 full-table SELECTs; 176,317 rows (all project data) through the repository refresh path.",
    "errors": "1 SELECT against a missing table; fails at planning time, reads nothing.",
}


def _redact_tree(value: Any, settings) -> Any:
    if isinstance(value, str):
        return _ANY_URI.sub("[path]", redact(value, settings))
    if isinstance(value, dict):
        return {k: _redact_tree(v, settings) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_tree(v, settings) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the SQL and expected impact; do not connect")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--data-dir", type=Path, default=BACKEND_DIR / "data" / "synthetic", help="CSV data to compare with")
    parser.add_argument("--report", type=Path, help="also write the (secret-free) report as JSON")
    args = parser.parse_args(argv)

    settings = get_databricks_settings()
    install_secret_redaction(settings)
    try:
        planned = statements(args.stage, settings)
    except InvalidIdentifierError as exc:
        print(f"Invalid DATABRICKS_CATALOG / DATABRICKS_SCHEMA: {exc}", file=sys.stderr)
        return 3
    for sql in planned:
        ensure_read_only(sql)

    client = client_info(settings)
    print(
        f"Client: connector {client['connector']}, pyarrow {client['pyarrow'] or 'not installed'}, "
        f"{client['result_format']} results, CloudFetch {'on' if client['use_cloud_fetch'] else 'off'}"
    )
    print(f"Stage '{args.stage}' on {settings.catalog}.{settings.schema_name}: {IMPACT[args.stage]}")
    for sql in planned:
        print(f"  {sql}")
    if args.dry_run:
        print("--dry-run: not connecting.")
        return 0
    if not args.yes:
        print("This starts your SQL warehouse if it is stopped; it then runs until its auto-stop timeout.")
        try:
            answer = input("Type 'read' to continue: ")
        except EOFError:
            answer = ""
        if answer.strip().lower() != "read":
            print("Aborted. Nothing was queried.")
            return 1

    report: dict[str, Any] = {"stage": args.stage, "target": f"{settings.catalog}.{settings.schema_name}", "client": client}
    started = time.perf_counter()
    try:
        csv = CsvRepository(args.data_dir).dataset() if args.stage in ("sample", "full") else None
        if args.stage == "full":
            problems = stage_full(settings, csv, report)
        else:
            timings: list[dict] = []
            with databricks_connection(settings) as connection, connection.cursor() as raw_cursor:
                cursor = TimedReadOnlyCursor(raw_cursor, timings)
                if args.stage == "schema":
                    problems = stage_schema(cursor, settings, report)
                elif args.stage == "sample":
                    problems = stage_sample(cursor, settings, csv, report)
                else:
                    problems = stage_errors(cursor, settings, report)
            report["queries"] = [{**t, "sql": t["sql"][:80]} for t in timings]
    except DatabricksNotConfiguredError as exc:
        print(f"Not configured: {exc}. Fill in backend/.env first.", file=sys.stderr)
        return 2
    except WriteRefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    except DataSourceUnavailableError as exc:
        print(f"Local CSV data unavailable: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Failed: {sanitize_error(exc, settings)}", file=sys.stderr)
        return 1

    report["elapsed_s"] = round(time.perf_counter() - started, 2)
    report["problems"] = problems
    # Redact each string value (not the serialized text, which redaction patterns could corrupt).
    text = json.dumps(_redact_tree(report, settings), indent=2, default=str)
    print(text)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    print("RESULT: " + ("all checks passed" if not problems else f"{len(problems)} problem(s)"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
