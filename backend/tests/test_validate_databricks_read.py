"""The Phase 4B read-only validation script, exercised against a fake warehouse (nothing connects)."""

import importlib.util
import json
import re
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import get_databricks_settings
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from app.synthetic.loader import TABLE_SPECS

SMALL = GeneratorConfig(seed=4, num_suppliers=4, num_products=12, num_stores=2, num_days=12)
HOST = "adb-9999999999999999.9.azuredatabricks.net"
HTTP_PATH = "/sql/1.0/warehouses/feedfacecafe"
TOKEN = "dapi-mock-token-feedfacecafe-99"
STORAGE = "abfss://lake@storageacct.dfs.core.windows.net/__unitystorage/catalogs/abc/tables/def"
SPECS = {s.name: s for s in TABLE_SPECS}
SECRETS = (HOST, HTTP_PATH, TOKEN, "storageacct", "abfss://")


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture
def csv_dir(dataset, tmp_path: Path) -> Path:
    write_csv(dataset, tmp_path)
    return tmp_path


@pytest.fixture
def script(monkeypatch):
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", HOST)
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", HTTP_PATH)
    monkeypatch.setenv("DATABRICKS_TOKEN", TOKEN)
    get_databricks_settings.cache_clear()
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_databricks_read.py"
    spec = importlib.util.spec_from_file_location("validate_databricks_read", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    get_databricks_settings.cache_clear()


def _wire(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


def _description(spec):
    codes = {"STRING": "string", "INT": "int", "BOOLEAN": "boolean", "DATE": "date", "TIMESTAMP": "timestamp"}
    out = []
    for c in spec.columns:
        if c.sql_type.startswith("DECIMAL("):
            p, s = (int(x) for x in c.sql_type[8:-1].split(","))
            out.append((c.name, "decimal", None, None, p, s, None))
        else:
            out.append((c.name, codes[c.sql_type], None, None, None, None, None))
    return out


class FakeWarehouse:
    def __init__(self, dataset, mutate=None):
        self.tables = {
            name: [tuple(_wire(getattr(r, c)) for c in SPECS[name].column_names) for r in records]
            for name, records in dataset.tables().items()
        }
        if mutate:
            mutate(self.tables)
        self.statements: list[str] = []
        self.connects = 0

    def connect(self):
        @contextmanager
        def _connect(settings):
            self.connects += 1
            yield _Connection(self)

        return _connect


class _Connection:
    def __init__(self, warehouse):
        self.warehouse = warehouse

    @contextmanager
    def cursor(self, **kwargs):
        yield _Cursor(self.warehouse)


class _Cursor:
    def __init__(self, warehouse):
        self.w = warehouse
        self.description = None
        self.rows: list = []

    def execute(self, sql, parameters=None):
        self.w.statements.append(sql)
        table = re.search(r"`([^`]+)`(?: LIMIT \d+)?$", sql).group(1)
        if table not in SPECS:
            raise RuntimeError(f"[TABLE_OR_VIEW_NOT_FOUND] {table} cannot be found. See https://{HOST}{HTTP_PATH} token {TOKEN}")
        spec = SPECS[table]
        if sql.startswith("DESCRIBE DETAIL"):
            self.description = [(n, "string", None, None, None, None, None) for n in ("format", "location", "numFiles", "sizeInBytes", "clusteringColumns")]
            self.rows = [("delta", STORAGE, 1, 1234 * len(self.w.tables[table]), ["sale_date"] if table == "sales" else [])]
        elif sql.startswith("EXPLAIN"):
            self.description = [("plan", "string", None, None, None, None, None)]
            self.rows = [(f"== Physical Plan ==\n*(1) ColumnarToRow\n+- PhotonScan parquet {table}[{','.join(spec.column_names)}] Location: PreparedDeltaFileIndex(1 paths)[{STORAGE}]",)]
        else:
            self.description = _description(spec)
            limit = re.search(r"LIMIT (\d+)$", sql)
            self.rows = list(self.w.tables[table][: int(limit.group(1))] if limit else self.w.tables[table])

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def fetchmany(self, size):
        batch, self.rows = self.rows[:size], self.rows[size:]
        return batch


def run(script, monkeypatch, warehouse, *args) -> int:
    monkeypatch.setattr(script, "databricks_connection", warehouse.connect())
    return script.main(list(args))


def test_dry_run_prints_read_only_sql_and_never_connects(script, monkeypatch, dataset, capsys) -> None:
    warehouse = FakeWarehouse(dataset)
    for stage, count in (("schema", 15), ("sample", 5), ("full", 5), ("errors", 1)):
        assert run(script, monkeypatch, warehouse, "--stage", stage, "--dry-run") == 0
        out = capsys.readouterr().out
        sql = [line.strip() for line in out.splitlines() if line.startswith("  ")]
        assert len(sql) == count and all(s.startswith(script.READ_ONLY_PREFIXES) for s in sql)
        assert all("`workspace`.`smartstock_retail`." in s for s in sql)
    assert warehouse.connects == 0


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO `workspace`.`smartstock_retail`.`sales` VALUES (1)",
        "DROP TABLE `workspace`.`smartstock_retail`.`sales`",
        "SELECT 1; DELETE FROM `workspace`.`smartstock_retail`.`sales`",
        "MERGE INTO x USING y ON 1=1",
        "DESCRIBE HISTORY `workspace`.`smartstock_retail`.`sales`",
    ],
)
def test_read_only_guard_refuses_anything_else(script, sql: str) -> None:
    with pytest.raises(script.WriteRefusedError):
        script.ensure_read_only(sql)


def test_confirmation_is_required(script, monkeypatch, dataset) -> None:
    warehouse = FakeWarehouse(dataset)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert run(script, monkeypatch, warehouse, "--stage", "schema") == 1
    assert warehouse.connects == 0


def test_schema_stage_reports_size_and_plan_without_storage_paths(script, monkeypatch, dataset, capsys) -> None:
    warehouse = FakeWarehouse(dataset)
    assert run(script, monkeypatch, warehouse, "--stage", "schema", "--yes") == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"): out.rindex("}") + 1])
    assert report["schema"]["details"]["sales"]["format"] == "delta"
    assert report["schema"]["total_size_bytes"] > 0
    assert any("PhotonScan" in line for line in report["schema"]["plans"]["inventory"])
    assert len(warehouse.statements) == 15 and not any(s.startswith("SELECT") and "LIMIT 0" not in s for s in warehouse.statements)
    for secret in SECRETS:
        assert secret not in out


def test_sample_stage_records_raw_types_and_matches_csv(script, monkeypatch, dataset, csv_dir, capsys) -> None:
    assert run(script, monkeypatch, FakeWarehouse(dataset), "--stage", "sample", "--yes", "--data-dir", str(csv_dir)) == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"): out.rindex("}") + 1])
    assert report["sample"]["raw_value_types"]["products"]["unit_cost"] == ["str"]  # wire format without pyarrow
    assert "RESULT: all checks passed" in out


def test_full_stage_matches_csv_records_and_analytics(script, monkeypatch, dataset, csv_dir, capsys, tmp_path) -> None:
    report_path = tmp_path / "report.json"
    code = run(script, monkeypatch, FakeWarehouse(dataset), "--stage", "full", "--yes", "--data-dir", str(csv_dir), "--report", str(report_path))
    out = capsys.readouterr().out
    assert code == 0, out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    full = report["full"]
    assert full["rows_total"] == sum(len(records) for records in dataset.tables().values())
    assert len(full["queries"]) == 5 and all(q["execute_s"] >= 0 and q["rows"] >= 0 for q in full["queries"])
    assert full["freshness"]["stale"] is False and full["freshness"]["last_error"] is None
    assert full["metrics"]["rows"]["inventory"] == len(dataset.inventory)
    assert report["problems"] == []
    client = report["client"]
    assert client["result_format"] in ("arrow", "row-based") and client["use_cloud_fetch"] is False
    assert client["pandas_conversion"] is False
    assert (client["pyarrow"] is None) == (client["result_format"] == "row-based")
    for secret in SECRETS:
        assert secret not in out and secret not in report_path.read_text(encoding="utf-8")


def test_full_stage_reports_a_mismatch_by_key(script, monkeypatch, dataset, csv_dir, capsys) -> None:
    def change_price(tables):
        row = list(tables["products"][3])
        row[5] = "99.99"  # selling_price
        tables["products"][3] = tuple(row)

    code = run(script, monkeypatch, FakeWarehouse(dataset, mutate=change_price), "--stage", "full", "--yes", "--data-dir", str(csv_dir))
    out = capsys.readouterr().out
    assert code == 1
    assert "products: records differ" in out and dataset.products[3].product_id in out


def test_client_info_follows_the_connectors_pyarrow_switch(script, monkeypatch, capsys) -> None:
    from databricks.sql.backend import thrift_backend

    monkeypatch.setattr(thrift_backend, "pyarrow", None)  # what the connector sees without pyarrow
    info = script.client_info(script.get_databricks_settings())
    assert info["result_format"] == "row-based" and info["pyarrow"] is None and info["pandas_conversion"] is False
    assert script.main(["--stage", "schema", "--dry-run"]) == 0
    assert "pyarrow not installed, row-based results, CloudFetch off" in capsys.readouterr().out


def test_errors_stage_classifies_and_redacts(script, monkeypatch, dataset, capsys) -> None:
    assert run(script, monkeypatch, FakeWarehouse(dataset), "--stage", "errors", "--yes") == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"): out.rindex("}") + 1])
    assert report["errors"]["category"] == "not_found"
    for secret in SECRETS:
        assert secret not in out
