"""Strict conversion and validation of Databricks query results.

Without pyarrow, the connector returns row-based results in which DATE, TIMESTAMP, and DECIMAL
values may arrive as strings; with other configurations they arrive as native Python types.
Both forms are accepted and converted to exactly the types the CSV path produces:

- STRING -> str, INT -> int (bool rejected), BOOLEAN -> bool
- DATE -> datetime.date (a datetime is rejected), TIMESTAMP -> naive datetime in UTC
  (timezone-aware values are converted to UTC), DECIMAL(p,s) -> Decimal with scale s
  (never silently rounded)
- NULL only where the column is nullable

After per-value conversion, the same CHECK-constraint, key, and foreign-key validation used for
the CSV files runs over all five tables.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.synthetic.loader import TABLE_SPECS, Column, TableData, TableSpec, _ErrorLog, convert_value, validate_tables

# cursor.description type codes reported by databricks-sql-connector 4.x (TTypeId names, lower-cased).
EXPECTED_TYPE_CODE = {
    "STRING": "string",
    "INT": "int",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
}
MAX_REPORTED_ERRORS = 5


class ResultValidationError(ValueError):
    """Query results do not match the expected schema or data rules. ``kind`` is 'schema' or 'data'."""

    def __init__(self, kind: str, problems: Sequence[str]):
        super().__init__(f"{len(problems)} problem(s): " + "; ".join(problems[:MAX_REPORTED_ERRORS]))
        self.kind = kind
        self.problems = list(problems)


def validate_description(spec: TableSpec, description: Sequence[Sequence[Any]] | None) -> None:
    """Check column names, order, and types (and DECIMAL precision/scale) of a SELECT result."""
    problems: list[str] = []
    columns = list(description or [])
    names = [str(c[0]) for c in columns]
    if names != spec.column_names:
        problems.append(f"{spec.name}: columns {names} != expected {spec.column_names}")
    else:
        for column, desc in zip(spec.columns, columns):
            type_code = str(desc[1]).lower()
            if column.sql_type.startswith("DECIMAL("):
                precision, scale = column.sql_type[8:-1].split(",")
                if type_code != "decimal" or (desc[4], desc[5]) != (int(precision), int(scale)):
                    problems.append(f"{spec.name}.{column.name}: type {type_code}({desc[4]},{desc[5]}) != {column.sql_type}")
            elif type_code != EXPECTED_TYPE_CODE[column.sql_type]:
                problems.append(f"{spec.name}.{column.name}: type {type_code} != {column.sql_type}")
    if problems:
        raise ResultValidationError("schema", problems)


def coerce_value(value: Any, column: Column) -> Any:
    """Convert one result value to the application type, or raise ValueError."""
    if value is None:
        if column.nullable:
            return None
        raise ValueError("NULL in NOT NULL column")
    if isinstance(value, str):
        # Same strict parser as the CSV path (an empty string means NULL there).
        return convert_value(value, column)

    sql_type = column.sql_type
    if sql_type == "STRING":
        raise ValueError(f"expected text, got {type(value).__name__}")
    if sql_type == "INT":
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError(f"expected an integer, got {type(value).__name__}")
        if isinstance(value, Decimal) and value != value.to_integral_value():
            raise ValueError(f"{value} is not a whole number")
        return convert_value(str(int(value)), column)
    if sql_type == "BOOLEAN":
        if not isinstance(value, bool):
            raise ValueError(f"expected true/false, got {type(value).__name__}")
        return value
    if sql_type == "DATE":
        if isinstance(value, datetime) or not isinstance(value, date):
            raise ValueError(f"expected a date, got {type(value).__name__}")
        return value
    if sql_type == "TIMESTAMP":
        if not isinstance(value, datetime):
            raise ValueError(f"expected a timestamp, got {type(value).__name__}")
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    if sql_type.startswith("DECIMAL("):
        if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
            raise ValueError(f"expected a decimal, got {type(value).__name__}")
        # repr() of a float is its shortest round-tripping form, e.g. 0.84 -> "0.84".
        text = repr(value) if isinstance(value, float) else format(Decimal(value), "f")
        return convert_value(text, column)
    raise ValueError(f"unsupported column type {sql_type}")  # pragma: no cover - specs are fixed


def convert_rows(spec: TableSpec, rows: Iterable[Sequence[Any]], errors: list[str]) -> list[dict[str, Any]]:
    """Convert result rows to dicts keyed by column name; problems are appended to ``errors``."""
    converted = []
    for index, row in enumerate(rows):
        values = list(row)
        if len(values) != len(spec.columns):
            errors.append(f"{spec.name} row {index + 1}: expected {len(spec.columns)} values, got {len(values)}")
            continue
        record: dict[str, Any] = {}
        for column, value in zip(spec.columns, values):
            try:
                record[column.name] = coerce_value(value, column)
            except ValueError as exc:
                errors.append(f"{spec.name} row {index + 1} {column.name}: {exc}")
                record = {}
                break
        if record:
            converted.append(record)
    return converted


def validate_relations(tables: dict[str, list[dict[str, Any]]]) -> None:
    """CHECK constraints, primary/natural key uniqueness, and foreign keys (same rules as CSV preflight)."""
    log = _ErrorLog()
    validate_tables({spec.name: TableData(spec, Path(spec.name), tables[spec.name]) for spec in TABLE_SPECS}, log)
    if log:
        raise ResultValidationError("data", log.finish())
