"""Validate synthetic retail CSVs and load them into the existing Delta tables.

Target: ``workspace.smartstock_retail`` (tables created by ``databricks/sql/01``-``06``).
This module never creates, drops, truncates, or alters tables. It only runs read-only
queries (information_schema, COUNT(*)), ``INSERT INTO``, and, in --allow-nonempty mode,
insert-only ``MERGE INTO``.

Phases:
1. Local preflight (no connection): read every CSV, trim headers, convert values to typed
   Python objects, then check NOT NULL, the CHECK constraints from 06_add_check_constraints.sql,
   primary-key and inventory natural-key uniqueness, and foreign keys across the CSVs.
   If any CSV fails, nothing is written.
2. Remote preflight (read-only): confirm the five tables exist with the expected columns,
   types, and nullability, and count their rows. Non-empty tables are refused unless
   ``allow_nonempty`` is set.
3. Load in foreign-key order, in batches. Each statement is its own Delta commit, so the
   five-table load is NOT atomic: a failure part-way leaves earlier batches committed.
4. Re-count every table and compare with the expected totals.
"""

import csv
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

TARGET_CATALOG = "workspace"
TARGET_SCHEMA = "smartstock_retail"
DEFAULT_BATCH_SIZE = 500
MAX_ERRORS_PER_TABLE = 20

Row = dict[str, Any]


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str  # exactly as in the DDL, e.g. "DECIMAL(10,2)"
    nullable: bool = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[Column, ...]
    primary_key: str
    # Additional business key that must be unique (no UNIQUE constraints in Databricks).
    natural_key: tuple[str, ...] | None = None

    @property
    def fqn(self) -> str:
        return f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{self.name}"

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


# Mirrors databricks/sql/01-05 (kept in sync by tests). Listed in foreign-key load order.
TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "suppliers",
        (
            Column("supplier_id", "STRING"),
            Column("supplier_name", "STRING"),
            Column("contact_email", "STRING"),
            Column("lead_time_days", "INT"),
            Column("minimum_order_quantity", "INT"),
            Column("reliability_score", "DECIMAL(4,3)"),
        ),
        primary_key="supplier_id",
    ),
    TableSpec(
        "products",
        (
            Column("product_id", "STRING"),
            Column("sku", "STRING"),
            Column("product_name", "STRING"),
            Column("category", "STRING"),
            Column("unit_cost", "DECIMAL(10,2)"),
            Column("selling_price", "DECIMAL(10,2)"),
            Column("supplier_id", "STRING"),
            Column("shelf_life_days", "INT", nullable=True),
            Column("created_at", "TIMESTAMP"),
        ),
        primary_key="product_id",
    ),
    TableSpec(
        "sales",
        (
            Column("sale_id", "STRING"),
            Column("sale_date", "DATE"),
            Column("store_id", "STRING"),
            Column("product_id", "STRING"),
            Column("quantity_sold", "INT"),
            Column("unit_selling_price", "DECIMAL(10,2)"),
            Column("promotion_applied", "BOOLEAN"),
        ),
        primary_key="sale_id",
    ),
    TableSpec(
        "inventory",
        (
            Column("inventory_id", "STRING"),
            Column("snapshot_date", "DATE"),
            Column("store_id", "STRING"),
            Column("product_id", "STRING"),
            Column("quantity_on_hand", "INT"),
            Column("quantity_reserved", "INT"),
            Column("reorder_point", "INT"),
            Column("safety_stock", "INT"),
        ),
        primary_key="inventory_id",
        natural_key=("snapshot_date", "store_id", "product_id"),
    ),
    TableSpec(
        "purchase_orders",
        (
            Column("purchase_order_id", "STRING"),
            Column("supplier_id", "STRING"),
            Column("product_id", "STRING"),
            Column("store_id", "STRING"),
            Column("order_date", "DATE"),
            Column("expected_delivery_date", "DATE"),
            Column("actual_delivery_date", "DATE", nullable=True),
            Column("quantity_ordered", "INT"),
            Column("unit_cost", "DECIMAL(10,2)"),
            Column("order_status", "STRING"),
        ),
        primary_key="purchase_order_id",
    ),
)
SPECS_BY_NAME = {spec.name: spec for spec in TABLE_SPECS}

# (table, column, referenced table, referenced column) — mirrors the FOREIGN KEY clauses.
FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("products", "supplier_id", "suppliers", "supplier_id"),
    ("sales", "product_id", "products", "product_id"),
    ("inventory", "product_id", "products", "product_id"),
    ("purchase_orders", "supplier_id", "suppliers", "supplier_id"),
    ("purchase_orders", "product_id", "products", "product_id"),
)

_EMAIL_LIKE = re.compile(r".+@.+\..+", re.S)  # SQL: contact_email LIKE '%_@_%._%'
_PO_STATUSES = {"PLACED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}

# Python mirrors of databricks/sql/06_add_check_constraints.sql, keyed by constraint name.
CHECK_CONSTRAINTS: dict[str, dict[str, Callable[[Row], bool]]] = {
    "suppliers": {
        "suppliers_lead_time_positive": lambda r: r["lead_time_days"] > 0,
        "suppliers_moq_positive": lambda r: r["minimum_order_quantity"] > 0,
        "suppliers_reliability_range": lambda r: 0 <= r["reliability_score"] <= 1,
        "suppliers_email_format": lambda r: bool(_EMAIL_LIKE.fullmatch(r["contact_email"])),
    },
    "products": {
        "products_unit_cost_non_negative": lambda r: r["unit_cost"] >= 0,
        "products_selling_price_positive": lambda r: r["selling_price"] > 0,
        "products_shelf_life_positive": lambda r: r["shelf_life_days"] is None or r["shelf_life_days"] > 0,
    },
    "sales": {
        "sales_quantity_positive": lambda r: r["quantity_sold"] > 0,
        "sales_price_non_negative": lambda r: r["unit_selling_price"] >= 0,
    },
    "inventory": {
        "inventory_on_hand_non_negative": lambda r: r["quantity_on_hand"] >= 0,
        "inventory_reserved_within_on_hand": lambda r: 0 <= r["quantity_reserved"] <= r["quantity_on_hand"],
        "inventory_reorder_point_non_negative": lambda r: r["reorder_point"] >= 0,
        "inventory_safety_stock_non_negative": lambda r: r["safety_stock"] >= 0,
    },
    "purchase_orders": {
        "purchase_orders_quantity_positive": lambda r: r["quantity_ordered"] > 0,
        "purchase_orders_unit_cost_non_negative": lambda r: r["unit_cost"] >= 0,
        "purchase_orders_status_valid": lambda r: r["order_status"] in _PO_STATUSES,
        "purchase_orders_expected_after_order": lambda r: r["expected_delivery_date"] >= r["order_date"],
        "purchase_orders_actual_after_order": lambda r: (
            r["actual_delivery_date"] is None or r["actual_delivery_date"] >= r["order_date"]
        ),
        "purchase_orders_delivery_matches_status": lambda r: (
            (r["order_status"] == "DELIVERED") == (r["actual_delivery_date"] is not None)
        ),
    },
}


# --- Errors -------------------------------------------------------------------------------


class LoaderError(Exception):
    """Base class for loader failures."""


class PreflightError(LoaderError):
    """Local CSV validation failed; nothing was written."""

    def __init__(self, errors: Sequence[str]):
        super().__init__(f"CSV preflight failed with {len(errors)} problem(s)")
        self.errors = list(errors)


class SchemaMismatchError(LoaderError):
    """A target table is missing or its columns differ from the expected definition; nothing was written."""

    def __init__(self, errors: Sequence[str]):
        super().__init__(f"Target schema check failed with {len(errors)} problem(s)")
        self.errors = list(errors)


class NonEmptyTargetError(LoaderError):
    """Target tables already contain rows and --allow-nonempty was not given; nothing was written."""

    def __init__(self, counts: dict[str, int]):
        listed = ", ".join(f"{name}={count:,}" for name, count in counts.items())
        super().__init__(f"Refusing to load: target tables are not empty ({listed})")
        self.counts = counts


class LoadFailedError(LoaderError):
    """A write failed part-way. Earlier batches remain committed."""


class CountMismatchError(LoaderError):
    """Post-load row counts differ from the expected counts."""


# --- Value conversion ---------------------------------------------------------------------

INT_MIN, INT_MAX = -(2**31), 2**31 - 1
_INT_RE = re.compile(r"[+-]?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d{1,6})?")
_DECIMAL_TYPE_RE = re.compile(r"DECIMAL\((\d+),(\d+)\)")


def convert_value(raw: str, column: Column) -> Any:
    """Convert one CSV cell to a typed Python value, or raise ValueError with a short reason.

    Surrounding whitespace is trimmed and an empty cell means NULL.
    """
    value = raw.strip()
    if value == "":
        if column.nullable:
            return None
        raise ValueError("empty value in NOT NULL column")

    sql_type = column.sql_type
    if sql_type == "STRING":
        return value
    if sql_type == "INT":
        if not _INT_RE.fullmatch(value):
            raise ValueError(f"{value!r} is not an integer")
        number = int(value)
        if not INT_MIN <= number <= INT_MAX:
            raise ValueError(f"{value} is outside the INT range")
        return number
    if sql_type == "BOOLEAN":
        lowered = value.lower()
        if lowered not in ("true", "false"):
            raise ValueError(f"{value!r} is not true/false")
        return lowered == "true"
    if sql_type == "DATE":
        try:
            if not _DATE_RE.fullmatch(value):
                raise ValueError
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{value!r} is not a valid YYYY-MM-DD date") from None
    if sql_type == "TIMESTAMP":
        try:
            if not _TIMESTAMP_RE.fullmatch(value):
                raise ValueError
            return datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(
                f"{value!r} is not a valid 'YYYY-MM-DD HH:MM:SS[.ffffff]' timestamp without offset"
            ) from None
    if match := _DECIMAL_TYPE_RE.fullmatch(sql_type):
        precision, scale = int(match.group(1)), int(match.group(2))
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"{value!r} is not a decimal number") from None
        if not number.is_finite():
            raise ValueError(f"{value!r} is not a finite number")
        if -number.as_tuple().exponent > scale:
            raise ValueError(f"{value} has more than {scale} decimal places")
        quantized = number.quantize(Decimal(1).scaleb(-scale))
        if len(quantized.as_tuple().digits) > precision:
            raise ValueError(f"{value} does not fit {sql_type}")
        return quantized
    raise ValueError(f"unsupported column type {sql_type}")  # pragma: no cover - specs are fixed


def to_parameter(value: Any) -> Any:
    """Python value -> connector parameter. DECIMAL and TIMESTAMP are sent as canonical strings
    and converted by an explicit CAST in SQL, avoiding the connector's type inference."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


# --- Local preflight ----------------------------------------------------------------------


@dataclass
class TableData:
    spec: TableSpec
    path: Path
    rows: list[Row]


class _ErrorLog:
    """Collects errors, keeping the first few per table plus a total count."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._per_table: Counter[str] = Counter()

    def add(self, table: str, message: str) -> None:
        self._per_table[table] += 1
        if self._per_table[table] <= MAX_ERRORS_PER_TABLE:
            self.messages.append(f"[{table}] {message}")

    def finish(self) -> list[str]:
        result = list(self.messages)
        for table, count in self._per_table.items():
            if count > MAX_ERRORS_PER_TABLE:
                result.append(f"[{table}] ... and {count - MAX_ERRORS_PER_TABLE:,} more problem(s)")
        return result

    def __bool__(self) -> bool:
        return bool(self._per_table)


def read_table_csv(path: Path, spec: TableSpec, errors: _ErrorLog) -> list[Row]:
    """Read one CSV: trim header names, map columns by name, and convert every value."""
    table = spec.name
    if not path.is_file():
        errors.add(table, f"file not found: {path}")
        return []

    rows: list[Row] = []
    # utf-8-sig strips a byte-order mark (e.g. from files re-saved in Excel).
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            errors.add(table, f"{path.name} is empty (no header row)")
            return []
        header = [name.strip() for name in header]

        duplicates = sorted(name for name, n in Counter(header).items() if n > 1)
        missing = [name for name in spec.column_names if name not in header]
        unexpected = [name for name in header if name not in spec.column_names]
        if duplicates or missing or unexpected:
            errors.add(
                table,
                f"{path.name} header mismatch: missing={missing} unexpected={unexpected} duplicated={duplicates}",
            )
            return []

        positions = [(column, header.index(column.name)) for column in spec.columns]
        for line_number, record in enumerate(reader, start=2):
            if not record:  # blank line
                continue
            if len(record) != len(header):
                errors.add(table, f"{path.name}:{line_number}: expected {len(header)} fields, got {len(record)}")
                continue
            row: Row = {}
            ok = True
            for column, index in positions:
                try:
                    row[column.name] = convert_value(record[index], column)
                except ValueError as exc:
                    errors.add(table, f"{path.name}:{line_number} {column.name}: {exc}")
                    ok = False
            if ok:
                rows.append(row)
    return rows


def validate_tables(tables: dict[str, TableData], errors: _ErrorLog) -> None:
    """Row-level CHECK constraints, key uniqueness, and cross-table foreign keys."""
    for name, data in tables.items():
        checks = CHECK_CONSTRAINTS[name]
        for index, row in enumerate(data.rows):
            for constraint, predicate in checks.items():
                if not predicate(row):
                    key = row[data.spec.primary_key]
                    errors.add(name, f"{data.spec.primary_key}={key} (data row {index + 1}) violates {constraint}")

        keys = [(data.spec.primary_key,)]
        if data.spec.natural_key:
            keys.append(data.spec.natural_key)
        for key_columns in keys:
            counts = Counter(tuple(row[c] for c in key_columns) for row in data.rows)
            for value, count in counts.items():
                if count > 1:
                    shown = ", ".join(f"{c}={v}" for c, v in zip(key_columns, value))
                    errors.add(name, f"duplicate key ({shown}) appears {count} times")

    for table, column, ref_table, ref_column in FOREIGN_KEYS:
        if table not in tables or ref_table not in tables:
            continue
        known = {row[ref_column] for row in tables[ref_table].rows}
        missing = Counter(row[column] for row in tables[table].rows if row[column] not in known)
        for value, count in sorted(missing.items()):
            errors.add(table, f"{column}={value} ({count} row(s)) not found in {ref_table}.{ref_column}")


def preflight(data_dir: Path) -> dict[str, TableData]:
    """Read and validate all five CSVs. Raises PreflightError listing every problem found."""
    errors = _ErrorLog()
    tables: dict[str, TableData] = {}
    for spec in TABLE_SPECS:
        path = data_dir / f"{spec.name}.csv"
        tables[spec.name] = TableData(spec, path, read_table_csv(path, spec, errors))
    if not errors:
        validate_tables(tables, errors)
    if errors:
        raise PreflightError(errors.finish())
    return tables


# --- SQL building -------------------------------------------------------------------------


def _source_query(spec: TableSpec, row_count: int) -> str:
    """SELECT over an inline VALUES table of named parameters, casting each column once."""
    width = len(spec.columns)
    values = ", ".join(
        "(" + ", ".join(f":r{i}_{j}" for j in range(width)) + ")" for i in range(row_count)
    )
    aliases = ", ".join(f"c{j}" for j in range(width))
    casts = ", ".join(f"CAST(c{j} AS {col.sql_type}) AS {col.name}" for j, col in enumerate(spec.columns))
    return f"SELECT {casts} FROM VALUES {values} AS src({aliases})"


def build_insert_sql(spec: TableSpec, row_count: int) -> str:
    columns = ", ".join(spec.column_names)
    return f"INSERT INTO {spec.fqn} ({columns}) {_source_query(spec, row_count)}"


def build_merge_sql(spec: TableSpec, row_count: int) -> str:
    """Insert-only MERGE: rows whose key already exists are skipped, never updated or deleted."""
    conditions = [f"t.{spec.primary_key} = s.{spec.primary_key}"]
    if spec.natural_key:
        conditions.append("(" + " AND ".join(f"t.{c} = s.{c}" for c in spec.natural_key) + ")")
    columns = ", ".join(spec.column_names)
    source_columns = ", ".join(f"s.{c}" for c in spec.column_names)
    return (
        f"MERGE INTO {spec.fqn} AS t USING ({_source_query(spec, row_count)}) AS s "
        f"ON {' OR '.join(conditions)} "
        f"WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({source_columns})"
    )


def build_parameters(spec: TableSpec, rows: Sequence[Row]) -> dict[str, Any]:
    return {
        f"r{i}_{j}": to_parameter(row[column.name])
        for i, row in enumerate(rows)
        for j, column in enumerate(spec.columns)
    }


# --- Remote phases ------------------------------------------------------------------------


class Cursor(Protocol):  # the subset of databricks.sql Cursor used here
    description: Any

    def execute(self, operation: str, parameters: dict[str, Any] | None = None) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...


def check_remote_schema(cursor: Cursor) -> None:
    """Read-only: confirm every target table exists with exactly the expected columns."""
    cursor.execute(
        f"SELECT table_name, column_name, full_data_type, is_nullable "
        f"FROM {TARGET_CATALOG}.information_schema.columns "
        f"WHERE table_schema = :schema_name ORDER BY table_name, ordinal_position",
        {"schema_name": TARGET_SCHEMA},
    )
    actual: dict[str, list[tuple[str, str, bool]]] = {}
    for table_name, column_name, data_type, is_nullable in cursor.fetchall():
        actual.setdefault(table_name, []).append(
            (column_name, data_type.replace(" ", "").lower(), str(is_nullable).upper() == "YES")
        )

    errors = []
    for spec in TABLE_SPECS:
        expected = [(c.name, c.sql_type.lower(), c.nullable) for c in spec.columns]
        if spec.name not in actual:
            errors.append(f"{spec.fqn} does not exist (run databricks/sql/01-06 first)")
        elif actual[spec.name] != expected:
            errors.append(f"{spec.fqn} columns differ. expected={expected} actual={actual[spec.name]}")
    if errors:
        raise SchemaMismatchError(errors)


def fetch_row_counts(cursor: Cursor) -> dict[str, int]:
    counts = {}
    for spec in TABLE_SPECS:
        cursor.execute(f"SELECT COUNT(*) FROM {spec.fqn}")
        counts[spec.name] = int(cursor.fetchone()[0])
    return counts


def _inserted_rows(cursor: Cursor) -> int | None:
    """Read num_inserted_rows from an INSERT/MERGE result, if the server reported it."""
    names = [d[0] for d in (cursor.description or [])]
    if "num_inserted_rows" not in names:
        return None
    row = cursor.fetchone()
    return None if row is None else int(row[names.index("num_inserted_rows")])


@dataclass
class TableLoadResult:
    table: str
    csv_rows: int
    count_before: int
    inserted: int
    count_after: int | None = None

    @property
    def skipped(self) -> int:
        return self.csv_rows - self.inserted

    @property
    def expected_after(self) -> int:
        return self.count_before + self.inserted


def run_load(
    cursor: Cursor,
    tables: dict[str, TableData],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    allow_nonempty: bool = False,
    out: Callable[[str], None] = print,
) -> list[TableLoadResult]:
    """Phases 2-4. Assumes ``tables`` already passed ``preflight``."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    # Session-scoped only: TIMESTAMP strings without an offset are interpreted as UTC.
    cursor.execute("SET TIME ZONE 'UTC'")

    out("Phase 2/4: checking target table definitions and row counts (read-only)")
    check_remote_schema(cursor)
    before = fetch_row_counts(cursor)
    for name, count in before.items():
        out(f"  {SPECS_BY_NAME[name].fqn}: {count:,} rows")
    nonempty = {name: count for name, count in before.items() if count > 0}
    if nonempty and not allow_nonempty:
        raise NonEmptyTargetError(nonempty)
    if nonempty:
        out("--allow-nonempty: using insert-only MERGE; rows whose key already exists are skipped.")

    out(f"Phase 3/4: loading in batches of up to {batch_size:,} rows (each batch commits separately)")
    results: list[TableLoadResult] = []
    for spec in TABLE_SPECS:
        rows = tables[spec.name].rows
        result = TableLoadResult(spec.name, len(rows), before[spec.name], inserted=0)
        results.append(result)
        use_merge = allow_nonempty and before[spec.name] > 0
        build_sql = build_merge_sql if use_merge else build_insert_sql
        out(f"  {spec.fqn}: {len(rows):,} rows ({'MERGE insert-only' if use_merge else 'INSERT'})")

        next_milestone = 10
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            try:
                cursor.execute(build_sql(spec, len(batch)), build_parameters(spec, batch))
                inserted = _inserted_rows(cursor)
            except Exception as exc:
                raise LoadFailedError(
                    _failure_message(spec, result, results, f"{type(exc).__name__}: {exc}")
                ) from exc
            if inserted is None:
                if use_merge:
                    raise LoadFailedError(
                        _failure_message(spec, result, results, "server did not report num_inserted_rows for MERGE")
                    )
                inserted = len(batch)  # an INSERT either writes every row or fails
            result.inserted += inserted

            done = start + len(batch)
            percent = 100 * done // len(rows)
            if percent >= next_milestone:
                out(f"    {done:,}/{len(rows):,} rows processed ({percent}%)")
                next_milestone = (percent // 10 + 1) * 10

    out("Phase 4/4: verifying row counts (read-only)")
    after = fetch_row_counts(cursor)
    mismatches = []
    for result in results:
        result.count_after = after[result.table]
        if result.count_after != result.expected_after:
            mismatches.append(f"{result.table}: expected {result.expected_after:,}, found {result.count_after:,}")
        if not allow_nonempty and result.inserted != result.csv_rows:
            mismatches.append(f"{result.table}: inserted {result.inserted:,} of {result.csv_rows:,} CSV rows")
    if mismatches:
        raise CountMismatchError("Row count verification failed: " + "; ".join(mismatches))
    return results


def _failure_message(spec: TableSpec, current: TableLoadResult, results: list[TableLoadResult], cause: str) -> str:
    completed = [r.table for r in results if r is not current]
    return (
        f"Write to {spec.fqn} failed after {current.inserted:,} of {current.csv_rows:,} rows were committed "
        f"for this table. Cause: {cause}. Tables fully loaded before this one: {', '.join(completed) or 'none'}. "
        "Batches already written are committed and were NOT rolled back. After fixing the cause, re-run "
        "with --allow-nonempty to insert only the rows whose keys are missing."
    )
