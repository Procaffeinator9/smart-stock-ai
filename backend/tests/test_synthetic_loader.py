"""Tests for the CSV -> Delta loader. Databricks is replaced by FakeCursor; nothing connects."""

import csv
import importlib.util
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from app.synthetic.loader import (
    CHECK_CONSTRAINTS,
    FOREIGN_KEYS,
    SPECS_BY_NAME,
    TABLE_SPECS,
    Column,
    CountMismatchError,
    LoadFailedError,
    NonEmptyTargetError,
    PreflightError,
    SchemaMismatchError,
    build_insert_sql,
    build_merge_sql,
    build_parameters,
    convert_value,
    preflight,
    run_load,
    to_parameter,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
SQL_DIR = BACKEND_DIR.parent / "databricks" / "sql"
SMALL = GeneratorConfig(seed=11, num_suppliers=4, num_products=16, num_stores=2, num_days=14)
FAKE_TOKEN = "dapi-fake-token-for-tests"


# --- Fixtures and helpers -----------------------------------------------------------------


@pytest.fixture(scope="module")
def generated_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("synthetic")
    write_csv(generate_dataset(SMALL), directory)
    return directory


@pytest.fixture
def data_dir(generated_dir: Path, tmp_path: Path) -> Path:
    """A fresh, writable copy of valid generated CSVs for each test."""
    for path in generated_dir.glob("*.csv"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    return tmp_path


def rewrite_csv(path: Path, mutate) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    mutate(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def preflight_errors(directory: Path) -> str:
    with pytest.raises(PreflightError) as exc_info:
        preflight(directory)
    return "\n".join(exc_info.value.errors)


class FakeCursor:
    """In-memory stand-in for a databricks.sql cursor, keyed by primary key (first column)."""

    WRITE_RE = re.compile(r"^(INSERT|MERGE) INTO workspace\.smartstock_retail\.(\w+)")

    def __init__(self, existing=None, schema=None, fail_on_table=None, lose_rows_in=None, report_inserted=True):
        self.rows: dict[str, set[str]] = {spec.name: set() for spec in TABLE_SPECS}
        for table, keys in (existing or {}).items():
            self.rows[table].update(keys)
        self.schema = schema if schema is not None else [
            (spec.name, c.name, c.sql_type.lower(), "YES" if c.nullable else "NO")
            for spec in TABLE_SPECS
            for c in spec.columns
        ]
        self.fail_on_table = fail_on_table
        self.lose_rows_in = lose_rows_in
        self.report_inserted = report_inserted
        self.executed: list[tuple[str, dict | None]] = []
        self.description = None
        self._results: list[tuple] = []

    def execute(self, operation, parameters=None):
        self.executed.append((operation, parameters))
        self.description, self._results = None, []
        if operation.startswith("SET TIME ZONE"):
            return self
        if "information_schema.columns" in operation:
            self._results = list(self.schema)
            return self
        if operation.startswith("SELECT COUNT(*) FROM"):
            table = operation.rsplit(".", 1)[1]
            lost = 1 if table == self.lose_rows_in and self.rows[table] else 0
            self._results = [(len(self.rows[table]) - lost,)]
            return self
        match = self.WRITE_RE.match(operation)
        if match:
            kind, table = match.groups()
            if table == self.fail_on_table:
                raise RuntimeError(f"simulated warehouse error (token {FAKE_TOKEN})")
            width = len(SPECS_BY_NAME[table].columns)
            keys = [parameters[f"r{i}_0"] for i in range(len(parameters) // width)]
            new = [k for k in keys if k not in self.rows[table]] if kind == "MERGE" else keys
            self.rows[table].update(new)
            if self.report_inserted:
                self.description = [("num_affected_rows",), ("num_inserted_rows",)]
                self._results = [(len(new), len(new))]
            return self
        raise AssertionError(f"unexpected SQL: {operation[:80]}")

    def fetchone(self):
        return self._results.pop(0) if self._results else None

    def fetchall(self):
        results, self._results = self._results, []
        return results

    def writes(self) -> list[str]:
        return [sql for sql, _ in self.executed if self.WRITE_RE.match(sql)]


# --- Header normalisation -----------------------------------------------------------------


def test_headers_are_trimmed_and_bom_is_ignored(data_dir: Path) -> None:
    path = data_dir / "suppliers.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    padded = ",".join(f"  {name}\t" for name in lines[0].split(","))
    path.write_text("﻿" + "\n".join([padded, *lines[1:]]) + "\n", encoding="utf-8")

    tables = preflight(data_dir)

    assert len(tables["suppliers"].rows) == SMALL.num_suppliers
    assert list(tables["suppliers"].rows[0]) == SPECS_BY_NAME["suppliers"].column_names


def test_columns_are_matched_by_name_not_position(data_dir: Path) -> None:
    path = data_dir / "suppliers.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    reordered = list(reversed(SPECS_BY_NAME["suppliers"].column_names))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=reordered, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    assert preflight(data_dir)["suppliers"].rows[0]["supplier_id"] == "SUP-0001"


def test_missing_and_unexpected_headers_are_reported(data_dir: Path) -> None:
    path = data_dir / "suppliers.csv"
    text = path.read_text(encoding="utf-8").replace("reliability_score", "reliability", 1)
    path.write_text(text, encoding="utf-8")

    errors = preflight_errors(data_dir)

    assert "missing=['reliability_score']" in errors
    assert "unexpected=['reliability']" in errors


def test_missing_file_is_reported(data_dir: Path) -> None:
    (data_dir / "purchase_orders.csv").unlink()
    assert "file not found" in preflight_errors(data_dir)


# --- Type conversion ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "column", "expected"),
    [
        ("42", Column("x", "INT"), 42),
        (" -7 ", Column("x", "INT"), -7),
        ("true", Column("x", "BOOLEAN"), True),
        ("FALSE", Column("x", "BOOLEAN"), False),
        ("2026-01-05", Column("x", "DATE"), date(2026, 1, 5)),
        ("2025-03-12 08:11:00", Column("x", "TIMESTAMP"), datetime(2025, 3, 12, 8, 11)),
        ("2025-03-12T08:11:00.5", Column("x", "TIMESTAMP"), datetime(2025, 3, 12, 8, 11, 0, 500000)),
        ("0.84", Column("x", "DECIMAL(10,2)"), Decimal("0.84")),
        ("3", Column("x", "DECIMAL(10,2)"), Decimal("3.00")),
        ("0.9", Column("x", "DECIMAL(4,3)"), Decimal("0.900")),
        ("  Fresh Apples ", Column("x", "STRING"), "Fresh Apples"),
        ("", Column("x", "INT", nullable=True), None),
        ("  ", Column("x", "DATE", nullable=True), None),
    ],
)
def test_convert_value_accepts_valid_input(raw: str, column: Column, expected) -> None:
    result = convert_value(raw, column)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    ("raw", "column", "reason"),
    [
        ("1.5", Column("x", "INT"), "not an integer"),
        ("2147483648", Column("x", "INT"), "outside the INT range"),
        ("yes", Column("x", "BOOLEAN"), "not true/false"),
        ("2026/01/05", Column("x", "DATE"), "not a valid YYYY-MM-DD date"),
        ("20260105", Column("x", "DATE"), "not a valid YYYY-MM-DD date"),
        ("2026-02-30", Column("x", "DATE"), "not a valid YYYY-MM-DD date"),
        ("2025-03-12 08:11:00+05:00", Column("x", "TIMESTAMP"), "without offset"),
        ("2025-03-12 25:00:00", Column("x", "TIMESTAMP"), "not a valid"),
        ("1.234", Column("x", "DECIMAL(10,2)"), "more than 2 decimal places"),
        ("NaN", Column("x", "DECIMAL(10,2)"), "not a finite number"),
        ("abc", Column("x", "DECIMAL(10,2)"), "not a decimal number"),
        ("123456789", Column("x", "DECIMAL(10,2)"), "does not fit DECIMAL(10,2)"),
        ("10", Column("x", "DECIMAL(4,3)"), "does not fit DECIMAL(4,3)"),
        ("", Column("x", "STRING"), "NOT NULL"),
    ],
)
def test_convert_value_rejects_invalid_input(raw: str, column: Column, reason: str) -> None:
    with pytest.raises(ValueError, match=re.escape(reason)):
        convert_value(raw, column)


def test_to_parameter_sends_decimal_and_timestamp_as_canonical_strings() -> None:
    assert to_parameter(Decimal("0.80")) == "0.80"
    assert to_parameter(convert_value("1E+1", Column("x", "DECIMAL(10,2)"))) == "10.00"
    assert to_parameter(datetime(2025, 3, 12, 8, 11)) == "2025-03-12 08:11:00"
    assert to_parameter(date(2026, 1, 5)) == date(2026, 1, 5)
    assert to_parameter(True) is True
    assert to_parameter(None) is None


def test_bad_cell_is_reported_with_file_line_and_column(data_dir: Path) -> None:
    rewrite_csv(data_dir / "sales.csv", lambda rows: rows[2].update(quantity_sold="three"))
    assert "sales.csv:4 quantity_sold: 'three' is not an integer" in preflight_errors(data_dir)


# --- Constraint validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "mutation", "constraint"),
    [
        ("suppliers", {"reliability_score": "1.500"}, "suppliers_reliability_range"),
        ("suppliers", {"lead_time_days": "0"}, "suppliers_lead_time_positive"),
        ("suppliers", {"contact_email": "not-an-email"}, "suppliers_email_format"),
        ("products", {"selling_price": "0.00"}, "products_selling_price_positive"),
        ("products", {"shelf_life_days": "-3"}, "products_shelf_life_positive"),
        ("sales", {"quantity_sold": "0"}, "sales_quantity_positive"),
        ("inventory", {"quantity_on_hand": "1", "quantity_reserved": "5"}, "inventory_reserved_within_on_hand"),
        ("purchase_orders", {"order_status": "LOST"}, "purchase_orders_status_valid"),
        ("purchase_orders", {"order_date": "2030-01-01"}, "purchase_orders_expected_after_order"),
    ],
)
def test_check_constraint_violations_are_reported(data_dir: Path, table: str, mutation: dict, constraint: str) -> None:
    rewrite_csv(data_dir / f"{table}.csv", lambda rows: rows[0].update(mutation))
    assert constraint in preflight_errors(data_dir)


def test_delivered_order_without_delivery_date_is_rejected(data_dir: Path) -> None:
    def mutate(rows):
        delivered = next(r for r in rows if r["order_status"] == "DELIVERED")
        delivered["actual_delivery_date"] = ""

    rewrite_csv(data_dir / "purchase_orders.csv", mutate)
    assert "purchase_orders_delivery_matches_status" in preflight_errors(data_dir)


def test_error_output_is_capped_per_table(data_dir: Path) -> None:
    rewrite_csv(data_dir / "inventory.csv", lambda rows: [r.update(safety_stock="-1") for r in rows])
    errors = preflight_errors(data_dir)
    assert errors.count("inventory_safety_stock_non_negative") == 20
    assert "more problem(s)" in errors


# --- Keys and foreign keys ----------------------------------------------------------------


def test_unknown_supplier_on_product_is_rejected(data_dir: Path) -> None:
    rewrite_csv(data_dir / "products.csv", lambda rows: rows[0].update(supplier_id="SUP-9999"))
    assert "supplier_id=SUP-9999 (1 row(s)) not found in suppliers.supplier_id" in preflight_errors(data_dir)


def test_unknown_product_on_sale_and_purchase_order_is_rejected(data_dir: Path) -> None:
    rewrite_csv(data_dir / "sales.csv", lambda rows: rows[0].update(product_id="PRD-99999"))
    rewrite_csv(data_dir / "purchase_orders.csv", lambda rows: rows[0].update(product_id="PRD-99999"))
    errors = preflight_errors(data_dir)
    assert "[sales] product_id=PRD-99999" in errors
    assert "[purchase_orders] product_id=PRD-99999" in errors


def test_duplicate_primary_key_is_rejected(data_dir: Path) -> None:
    rewrite_csv(data_dir / "sales.csv", lambda rows: rows[1].update(sale_id=rows[0]["sale_id"]))
    assert "duplicate key (sale_id=SAL-00000001) appears 2 times" in preflight_errors(data_dir)


def test_duplicate_inventory_snapshot_key_is_rejected(data_dir: Path) -> None:
    def mutate(rows):
        first = rows[0]
        rows[1].update(snapshot_date=first["snapshot_date"], store_id=first["store_id"], product_id=first["product_id"])

    rewrite_csv(data_dir / "inventory.csv", mutate)
    errors = preflight_errors(data_dir)

    assert "duplicate key (snapshot_date=" in errors
    assert "inventory_id" not in errors  # the inventory_ids themselves are still unique


def test_generated_data_passes_preflight(data_dir: Path) -> None:
    dataset = generate_dataset(SMALL)
    tables = preflight(data_dir)
    for name, records in dataset.tables().items():
        assert len(tables[name].rows) == len(records)


# --- Specs stay in sync with databricks/sql -----------------------------------------------


def _ddl_columns() -> dict[str, list[tuple[str, str, bool]]]:
    create_re = re.compile(r"CREATE TABLE IF NOT EXISTS workspace\.smartstock_retail\.(\w+) \((.*?)\n\)", re.S)
    column_re = re.compile(r"^  (\w+)\s+(STRING|INT|BOOLEAN|DATE|TIMESTAMP|DECIMAL\(\d+,\d+\))\s+(NOT NULL)?", re.M)
    tables = {}
    for path in sorted(SQL_DIR.glob("0[1-5]_*.sql")):
        for name, body in create_re.findall(path.read_text(encoding="utf-8")):
            tables[name] = [(col, sql_type, not not_null) for col, sql_type, not_null in column_re.findall(body)]
    return tables


def test_table_specs_match_ddl_types_and_nullability() -> None:
    ddl = _ddl_columns()
    assert [spec.name for spec in TABLE_SPECS] == ["suppliers", "products", "sales", "inventory", "purchase_orders"]
    for spec in TABLE_SPECS:
        assert [(c.name, c.sql_type, c.nullable) for c in spec.columns] == ddl[spec.name]


def test_foreign_keys_match_ddl() -> None:
    fk_re = re.compile(r"FOREIGN KEY \((\w+)\)\s+REFERENCES workspace\.smartstock_retail\.(\w+) \((\w+)\)")
    ddl_fks = set()
    for path in SQL_DIR.glob("0[1-5]_*.sql"):
        table = re.search(r"smartstock_retail\.(\w+) \(", path.read_text(encoding="utf-8")).group(1)
        for column, ref_table, ref_column in fk_re.findall(path.read_text(encoding="utf-8")):
            ddl_fks.add((table, column, ref_table, ref_column))
    assert set(FOREIGN_KEYS) == ddl_fks


def test_check_constraints_match_sql_file() -> None:
    sql = re.sub(r"--[^\n]*", "", (SQL_DIR / "06_add_check_constraints.sql").read_text(encoding="utf-8"))
    in_sql = set(re.findall(r"ADD CONSTRAINT (\w+)", sql))
    assert len(in_sql) == 19
    in_python = {name for checks in CHECK_CONSTRAINTS.values() for name in checks}
    assert in_python == in_sql


# --- SQL building -------------------------------------------------------------------------


def test_insert_sql_is_parameterised_and_fully_qualified(data_dir: Path) -> None:
    spec = SPECS_BY_NAME["sales"]
    rows = preflight(data_dir)["sales"].rows[:3]

    sql = build_insert_sql(spec, len(rows))
    params = build_parameters(spec, rows)

    assert sql.startswith("INSERT INTO workspace.smartstock_retail.sales (sale_id, sale_date,")
    assert "CAST(c5 AS DECIMAL(10,2)) AS unit_selling_price" in sql
    assert set(re.findall(r":(r\d+_\d+)", sql)) == set(params)
    assert len(params) == 3 * len(spec.columns)
    assert rows[0]["sale_id"] not in sql  # values travel only as parameters


def test_merge_sql_is_insert_only_and_uses_inventory_natural_key() -> None:
    sql = build_merge_sql(SPECS_BY_NAME["inventory"], 2)

    assert sql.startswith("MERGE INTO workspace.smartstock_retail.inventory AS t")
    assert "ON t.inventory_id = s.inventory_id OR (t.snapshot_date = s.snapshot_date AND " in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "WHEN MATCHED" not in sql
    assert "DELETE" not in sql and "UPDATE" not in sql


# --- Remote phases (mocked) ---------------------------------------------------------------


def test_load_into_empty_tables_inserts_everything_in_fk_order(data_dir: Path) -> None:
    tables = preflight(data_dir)
    cursor = FakeCursor()
    lines: list[str] = []

    results = run_load(cursor, tables, batch_size=100, out=lines.append)

    assert cursor.executed[0][0] == "SET TIME ZONE 'UTC'"
    written_order = list(dict.fromkeys(FakeCursor.WRITE_RE.match(sql).group(2) for sql in cursor.writes()))
    assert written_order == ["suppliers", "products", "sales", "inventory", "purchase_orders"]
    assert all(sql.startswith("INSERT INTO") for sql in cursor.writes())
    for result in results:
        assert result.inserted == result.csv_rows == result.count_after
        assert result.skipped == 0
    expected_batches = sum(-(-len(t.rows) // 100) for t in tables.values())
    assert len(cursor.writes()) == expected_batches
    assert any("rows processed (100%)" in line for line in lines)


def test_load_never_issues_destructive_sql(data_dir: Path) -> None:
    cursor = FakeCursor()
    run_load(cursor, preflight(data_dir), batch_size=500, out=lambda _: None)

    for sql, _ in cursor.executed:
        assert not re.search(r"\b(DROP|TRUNCATE|ALTER|CREATE|DELETE|UPDATE|REPLACE)\b", sql.upper()), sql


def test_refuses_to_load_into_non_empty_tables(data_dir: Path) -> None:
    cursor = FakeCursor(existing={"sales": {"SAL-00000001"}})

    with pytest.raises(NonEmptyTargetError) as exc_info:
        run_load(cursor, preflight(data_dir), out=lambda _: None)

    assert exc_info.value.counts == {"sales": 1}
    assert cursor.writes() == []


def test_allow_nonempty_merges_and_skips_existing_keys(data_dir: Path) -> None:
    tables = preflight(data_dir)
    existing = {row["sale_id"] for row in tables["sales"].rows[:5]}
    cursor = FakeCursor(existing={"sales": existing})

    results = {r.table: r for r in run_load(cursor, tables, batch_size=100, allow_nonempty=True, out=lambda _: None)}

    sales = results["sales"]
    assert (sales.count_before, sales.skipped, sales.count_after) == (5, 5, sales.csv_rows)
    assert all(sql.startswith("MERGE INTO workspace.smartstock_retail.sales") for sql in cursor.writes() if ".sales " in sql)
    assert all(sql.startswith("INSERT INTO") for sql in cursor.writes() if ".sales " not in sql)


def test_rerun_with_allow_nonempty_after_full_load_inserts_nothing(data_dir: Path) -> None:
    tables = preflight(data_dir)
    cursor = FakeCursor()
    run_load(cursor, tables, out=lambda _: None)

    results = run_load(cursor, tables, allow_nonempty=True, out=lambda _: None)

    assert all(r.inserted == 0 and r.count_after == r.csv_rows for r in results)


def test_schema_mismatch_stops_before_any_write(data_dir: Path) -> None:
    schema = [
        (spec.name, c.name, "bigint" if c.name == "quantity_sold" else c.sql_type.lower(), "YES" if c.nullable else "NO")
        for spec in TABLE_SPECS
        if spec.name != "purchase_orders"
        for c in spec.columns
    ]
    cursor = FakeCursor(schema=schema)

    with pytest.raises(SchemaMismatchError) as exc_info:
        run_load(cursor, preflight(data_dir), out=lambda _: None)

    errors = "\n".join(exc_info.value.errors)
    assert "purchase_orders does not exist" in errors
    assert "sales columns differ" in errors
    assert cursor.writes() == []


def test_count_mismatch_is_an_error(data_dir: Path) -> None:
    cursor = FakeCursor(lose_rows_in="inventory")

    with pytest.raises(CountMismatchError, match="inventory: expected"):
        run_load(cursor, preflight(data_dir), out=lambda _: None)


def test_merge_without_inserted_row_metrics_is_an_error(data_dir: Path) -> None:
    cursor = FakeCursor(existing={"suppliers": {"SUP-0001"}}, report_inserted=False)

    with pytest.raises(LoadFailedError, match="num_inserted_rows"):
        run_load(cursor, preflight(data_dir), allow_nonempty=True, out=lambda _: None)


def test_failure_mid_load_explains_partial_state(data_dir: Path) -> None:
    cursor = FakeCursor(fail_on_table="inventory")

    with pytest.raises(LoadFailedError) as exc_info:
        run_load(cursor, preflight(data_dir), out=lambda _: None)

    message = str(exc_info.value)
    assert "workspace.smartstock_retail.inventory failed after 0 of" in message
    assert "Tables fully loaded before this one: suppliers, products, sales" in message
    assert "NOT rolled back" in message
    assert "--allow-nonempty" in message


# --- CLI ----------------------------------------------------------------------------------


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("load_synthetic_data", BACKEND_DIR / "scripts" / "load_synthetic_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_validate_only_never_connects(cli, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("validate-only must not connect")

    monkeypatch.setattr(cli, "databricks_connection", forbidden)

    assert cli.main(["--data-dir", str(data_dir), "--validate-only"]) == 0
    assert "Constraints, primary keys, inventory natural key, and foreign keys: OK" in capsys.readouterr().out


def test_cli_exits_3_on_invalid_csv(cli, data_dir: Path) -> None:
    rewrite_csv(data_dir / "sales.csv", lambda rows: rows[0].update(quantity_sold="-1"))
    assert cli.main(["--data-dir", str(data_dir), "--validate-only"]) == 3


def test_cli_exits_2_when_databricks_not_configured(cli, data_dir: Path) -> None:
    assert cli.main(["--data-dir", str(data_dir), "--yes"]) == 2


def test_cli_aborts_without_confirmation(cli, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "no")
    monkeypatch.setattr(cli, "databricks_connection", lambda *a, **k: pytest.fail("must not connect"))
    assert cli.main(["--data-dir", str(data_dir)]) == 1


def _configure_fake_databricks(cli, monkeypatch: pytest.MonkeyPatch, cursor: FakeCursor) -> None:
    from contextlib import contextmanager

    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/fake")
    monkeypatch.setenv("DATABRICKS_TOKEN", FAKE_TOKEN)

    class FakeConnection:
        def cursor(self):
            @contextmanager
            def manager():
                yield cursor

            return manager()

    @contextmanager
    def fake_connection(settings):
        yield FakeConnection()

    monkeypatch.setattr(cli, "databricks_connection", fake_connection)


def test_cli_exits_4_when_tables_are_not_empty(cli, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    cursor = FakeCursor(existing={"products": {"PRD-00001"}})
    _configure_fake_databricks(cli, monkeypatch, cursor)

    assert cli.main(["--data-dir", str(data_dir), "--yes"]) == 4
    assert "--allow-nonempty" in capsys.readouterr().err
    assert cursor.writes() == []


def test_cli_full_load_reports_counts(cli, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _configure_fake_databricks(cli, monkeypatch, FakeCursor())

    assert cli.main(["--data-dir", str(data_dir), "--yes", "--batch-size", "250"]) == 0
    out = capsys.readouterr().out
    assert "All row counts match" in out
    assert FAKE_TOKEN not in out


def test_cli_never_prints_the_token_on_failure(cli, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _configure_fake_databricks(cli, monkeypatch, FakeCursor(fail_on_table="sales"))

    assert cli.main(["--data-dir", str(data_dir), "--yes"]) == 1
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out + captured.err
    assert "simulated warehouse error" in captured.err and "[redacted]" in captured.err


def test_cli_rejects_out_of_range_batch_size(cli, data_dir: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--data-dir", str(data_dir), "--batch-size", "0"])
