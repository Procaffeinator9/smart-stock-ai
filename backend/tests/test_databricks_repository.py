"""Hardened Databricks repository: timeouts, refresh concurrency, stale-while-revalidate, result
validation, configured identifiers, and sanitized errors. Fake warehouses only; nothing connects."""

import dataclasses
import importlib.util
import io
import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

import app.data.repository as repository_module
from app.core.config import DatabricksSettings, get_databricks_settings, get_settings
from app.core.log_redaction import SecretRedactionFilter
from app.data.conversion import ResultValidationError, coerce_value, validate_description
from app.data.repository import (
    DatabricksRepository,
    DataSourceUnavailableError,
    clear_repository_cache,
    get_repository,
)
from app.db.databricks import (
    DatabricksNotConfiguredError,
    classify_error,
    connection_options,
    databricks_connection,
    qualified_table,
    redact,
    sanitize_error,
)
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from app.synthetic.loader import TABLE_SPECS, Column

SMALL = GeneratorConfig(seed=9, num_suppliers=4, num_products=12, num_stores=2, num_days=10)
HOST = "adb-1234567890123456.7.azuredatabricks.net"
HTTP_PATH = "/sql/1.0/warehouses/abc123def456"
TOKEN = "dapi-mock-token-abc123def456-99"
SPECS = {spec.name: spec for spec in TABLE_SPECS}


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


def make_settings(**overrides) -> DatabricksSettings:
    values = {
        "server_hostname": HOST,
        "http_path": HTTP_PATH,
        "token": SecretStr(TOKEN),
        "catalog": "dev_catalog",
        "DATABRICKS_SCHEMA": "retail_test",
    }
    values.update(overrides)
    return DatabricksSettings(**values)


# --- Fake warehouse ------------------------------------------------------------------------------


def _description(spec, overrides=None):
    codes = {"STRING": "string", "INT": "int", "BOOLEAN": "boolean", "DATE": "date", "TIMESTAMP": "timestamp"}
    rows = []
    for column in spec.columns:
        if column.sql_type.startswith("DECIMAL("):
            precision, scale = (int(x) for x in column.sql_type[8:-1].split(","))
            rows.append((column.name, "decimal", None, None, precision, scale, None))
        else:
            rows.append((column.name, codes[column.sql_type], None, None, None, None, None))
    return (overrides or {}).get(spec.name, rows)


def _as_wire_string(value):
    """What row-based (no pyarrow) results look like: DATE/TIMESTAMP/DECIMAL as text."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


class FakeWarehouse:
    def __init__(self, dataset, *, as_strings=False, error=None, gate=None, descriptions=None, mutate=None):
        self.tables = {}
        for name, records in dataset.tables().items():
            rows = [tuple(getattr(r, c) for c in SPECS[name].column_names) for r in records]
            if as_strings:
                rows = [tuple(_as_wire_string(v) for v in row) for row in rows]
            self.tables[name] = rows
        if mutate:
            mutate(self.tables)
        self.error = error
        self.gate = gate
        self.descriptions = descriptions
        self.connects = 0
        self.statements: list[str] = []
        self.cursor_kwargs: list[dict] = []

    def connect(self):
        @contextmanager
        def _connect(settings):
            self.connects += 1
            if self.gate is not None:
                assert self.gate.wait(10), "test gate never released"
            if self.error is not None:
                raise self.error
            yield _FakeConnection(self)

        return _connect


class _FakeConnection:
    def __init__(self, warehouse):
        self.warehouse = warehouse

    @contextmanager
    def cursor(self, **kwargs):
        self.warehouse.cursor_kwargs.append(kwargs)
        yield _FakeCursor(self.warehouse)


class _FakeCursor:
    def __init__(self, warehouse):
        self.warehouse = warehouse
        self.description = None
        self._rows: list = []

    def execute(self, sql, parameters=None):
        self.warehouse.statements.append(sql)
        table = re.search(r"FROM `[^`]+`\.`[^`]+`\.`([^`]+)`$", sql).group(1)
        self.description = _description(SPECS[table], self.warehouse.descriptions)
        self._rows = list(self.warehouse.tables[table])

    def fetchmany(self, size):
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def sync_repo(warehouse, clock=None, **kwargs) -> DatabricksRepository:
    """Refreshes run synchronously in the calling thread (still outside the lock)."""
    return DatabricksRepository(
        make_settings(), connect=warehouse.connect(), clock=clock or FakeClock(), start=lambda fn: fn(), **kwargs
    )


# --- Connection options and bounded retries ------------------------------------------------------


def test_connection_options_are_bounded_and_within_connector_policy() -> None:
    from databricks.sql.backend.thrift_backend import DEFAULT_SOCKET_TIMEOUT, _retry_policy

    options = connection_options(DatabricksSettings())
    assert options["_socket_timeout"] == 30 < DEFAULT_SOCKET_TIMEOUT
    assert options["_retry_stop_after_attempts_count"] == 3
    assert options["_retry_stop_after_attempts_duration"] == 60
    assert options["enable_telemetry"] is False
    assert options["_disable_pandas"] is True
    assert options["use_cloud_fetch"] is False
    assert options["session_configuration"] == {"STATEMENT_TIMEOUT": "60", "TIMEZONE": "UTC"}
    # Every retry value is inside the connector's accepted range, so it is used as-is (not clamped).
    for key, (_type, default, low, high) in _retry_policy.items():
        if key in options:
            assert low <= options[key] <= high, key
            assert options[key] <= default or key == "_retry_delay_min", key


def test_cloud_fetch_setting_is_passed_through(monkeypatch) -> None:
    assert connection_options(DatabricksSettings())["use_cloud_fetch"] is False
    monkeypatch.setenv("DATABRICKS_USE_CLOUD_FETCH", "true")
    assert connection_options(DatabricksSettings())["use_cloud_fetch"] is True


def test_every_connection_option_is_read_by_the_installed_connector() -> None:
    """Guards against a misspelled option silently doing nothing."""
    import databricks.sql

    package = Path(databricks.sql.__file__).parent
    source = "".join(
        (package / name).read_text(encoding="utf-8") for name in ("client.py", "session.py", "backend/thrift_backend.py")
    )
    for key in connection_options(DatabricksSettings()):
        assert f'"{key}"' in source or f"{key}:" in source or f"{key}=" in source, key


def test_databricks_connection_passes_credentials_and_options(monkeypatch, caplog) -> None:
    import databricks.sql

    calls = {}

    class Connection:
        def close(self):
            calls["closed"] = True

    def fake_connect(**kwargs):
        calls.update(kwargs)
        return Connection()

    monkeypatch.setattr(databricks.sql, "connect", fake_connect)
    caplog.set_level(logging.DEBUG)
    with databricks_connection(make_settings()):
        pass

    assert calls["server_hostname"] == HOST and calls["access_token"] == TOKEN and calls["closed"]
    assert calls["_socket_timeout"] == 30 and calls["enable_telemetry"] is False
    assert calls["_disable_pandas"] is True and calls["use_cloud_fetch"] is False
    assert (calls["catalog"], calls["schema"]) == ("dev_catalog", "retail_test")
    for secret in (HOST, HTTP_PATH, TOKEN):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    ("env", "value"),
    [
        ("DATABRICKS_SOCKET_TIMEOUT_SECONDS", "900"),
        ("DATABRICKS_RETRY_MAX_ATTEMPTS", "30"),
        ("DATABRICKS_RETRY_MAX_DURATION_SECONDS", "900"),
        ("DATABRICKS_STATEMENT_TIMEOUT_SECONDS", "0"),
    ],
)
def test_unbounded_timeout_settings_are_rejected(monkeypatch, env: str, value: str) -> None:
    monkeypatch.setenv(env, value)
    with pytest.raises(ValidationError):
        DatabricksSettings()


def test_missing_credentials_fail_before_importing_or_connecting() -> None:
    with pytest.raises(DatabricksNotConfiguredError):
        with databricks_connection(DatabricksSettings()):
            pass


# --- Configured identifiers -----------------------------------------------------------------------


def test_queries_use_configured_catalog_and_schema(dataset) -> None:
    warehouse = FakeWarehouse(dataset)
    sync_repo(warehouse).dataset()

    assert warehouse.statements == [
        f"SELECT {', '.join(spec.column_names)} FROM `dev_catalog`.`retail_test`.`{spec.name}`" for spec in TABLE_SPECS
    ]
    assert warehouse.cursor_kwargs == [{"arraysize": 50_000, "row_limit": 1_000_001}]


@pytest.mark.parametrize("catalog", ["dev-catalog", "x`; DROP TABLE y; --", "1abc", ""])
def test_unsafe_identifiers_are_rejected_without_connecting(dataset, catalog: str) -> None:
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(make_settings(catalog=catalog), connect=warehouse.connect(), clock=FakeClock(), start=lambda fn: fn())
    with pytest.raises(DataSourceUnavailableError, match="simple identifiers"):
        repo.dataset()
    assert warehouse.connects == 0
    with pytest.raises(ValueError):
        qualified_table(make_settings(catalog=catalog), "suppliers")


# --- Result conversion and validation -------------------------------------------------------------


@pytest.mark.parametrize("as_strings", [False, True], ids=["native-types", "string-wire-format"])
def test_rows_convert_to_the_same_records_as_the_generator(dataset, as_strings: bool) -> None:
    loaded = sync_repo(FakeWarehouse(dataset, as_strings=as_strings)).dataset()
    assert loaded.source == "databricks"
    for name, records in dataset.tables().items():
        assert getattr(loaded, name) == records, name


@pytest.mark.parametrize(
    ("value", "sql_type", "nullable", "expected"),
    [
        ("2026-01-05", "DATE", False, date(2026, 1, 5)),
        (date(2026, 1, 5), "DATE", False, date(2026, 1, 5)),
        ("2025-08-11 18:26:07", "TIMESTAMP", False, datetime(2025, 8, 11, 18, 26, 7)),
        (datetime(2026, 1, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))), "TIMESTAMP", False, datetime(2026, 1, 1)),
        (datetime(2026, 1, 1, 9, 0), "TIMESTAMP", False, datetime(2026, 1, 1, 9, 0)),
        ("14.96", "DECIMAL(10,2)", False, Decimal("14.96")),
        (Decimal("3"), "DECIMAL(10,2)", False, Decimal("3.00")),
        (0.84, "DECIMAL(10,2)", False, Decimal("0.84")),
        (10, "DECIMAL(4,3)", False, None),  # 10.000 needs 5 digits: must be rejected (handled below)
        (42, "INT", False, 42),
        (Decimal("42"), "INT", False, 42),
        ("42", "INT", False, 42),
        (True, "BOOLEAN", False, True),
        ("false", "BOOLEAN", False, False),
        (None, "INT", True, None),
        ("Fresh Apples", "STRING", False, "Fresh Apples"),
    ],
)
def test_coerce_value_accepts_native_and_string_forms(value, sql_type, nullable, expected) -> None:
    column = Column("x", sql_type, nullable=nullable)
    if expected is None and value is not None:
        with pytest.raises(ValueError):
            coerce_value(value, column)
        return
    result = coerce_value(value, column)
    assert result == expected and type(result) is type(expected)
    if isinstance(result, datetime):
        assert result.tzinfo is None


@pytest.mark.parametrize(
    ("value", "sql_type", "reason"),
    [
        (None, "STRING", "NULL in NOT NULL"),
        (True, "INT", "expected an integer"),
        (Decimal("1.5"), "INT", "not a whole number"),
        (datetime(2026, 1, 1), "DATE", "expected a date"),
        (date(2026, 1, 1), "TIMESTAMP", "expected a timestamp"),
        (Decimal("1.234"), "DECIMAL(10,2)", "more than 2 decimal places"),
        (1, "BOOLEAN", "expected true/false"),
        (5, "STRING", "expected text"),
        (2**31, "INT", "outside the INT range"),
    ],
)
def test_coerce_value_rejects_wrong_types(value, sql_type: str, reason: str) -> None:
    with pytest.raises(ValueError, match=re.escape(reason)):
        coerce_value(value, Column("x", sql_type))


def test_description_checks_names_types_and_decimal_scale() -> None:
    spec = SPECS["products"]
    good = _description(spec)
    validate_description(spec, good)

    renamed = [("name" if d[0] == "product_name" else d[0], *d[1:]) for d in good]
    wrong_type = [(d[0], "string" if d[0] == "shelf_life_days" else d[1], *d[2:]) for d in good]
    wrong_scale = [(*d[:4], 12, 4, None) if d[0] == "unit_cost" else d for d in good]
    for description, fragment in [(renamed, "columns"), (wrong_type, "shelf_life_days"), (wrong_scale, "unit_cost")]:
        with pytest.raises(ResultValidationError, match=fragment) as exc_info:
            validate_description(spec, description)
        assert exc_info.value.kind == "schema"


def test_schema_mismatch_is_a_clear_503(dataset) -> None:
    bad = {"sales": [d if d[0] != "quantity_sold" else ("quantity_sold", "bigint", None, None, None, None, None) for d in _description(SPECS["sales"])]}
    repo = sync_repo(FakeWarehouse(dataset, descriptions=bad))
    with pytest.raises(DataSourceUnavailableError, match="schema did not match"):
        repo.dataset()


def test_null_in_required_column_and_broken_foreign_key_are_rejected(dataset) -> None:
    def null_name(tables):
        tables["products"][0] = (tables["products"][0][0], tables["products"][0][1], None, *tables["products"][0][3:])

    def orphan_sale(tables):
        row = list(tables["sales"][0])
        row[3] = "PRD-99999"
        tables["sales"][0] = tuple(row)

    for mutate in (null_name, orphan_sale):
        with pytest.raises(DataSourceUnavailableError, match="did not match the expected definition"):
            sync_repo(FakeWarehouse(dataset, mutate=mutate)).dataset()


def test_row_cap_bounds_memory(dataset, monkeypatch) -> None:
    monkeypatch.setattr(repository_module, "MAX_ROWS_PER_TABLE", 10)
    with pytest.raises(DataSourceUnavailableError):
        sync_repo(FakeWarehouse(dataset)).dataset()


# --- Refresh concurrency, bounded waits, backoff, stale-while-revalidate -------------------------


def test_concurrent_first_requests_share_one_refresh(dataset) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), wait_seconds=5)
    results, errors = [], []

    def call():
        try:
            results.append(repo.dataset())
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    assert warehouse.connects == 1  # one refresh in flight while six requests wait
    gate.set()
    for t in threads:
        t.join(5)
    assert not errors and len(results) == 6 and all(r is results[0] for r in results)
    assert warehouse.connects == 1


def test_first_request_wait_is_bounded(dataset) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), wait_seconds=0.3)
    try:
        started = time.monotonic()
        with pytest.raises(DataSourceUnavailableError, match="still loading") as exc_info:
            repo.dataset()
        assert time.monotonic() - started < 2
        assert exc_info.value.retry_after and exc_info.value.retry_after >= 1
        # A second request does not start another refresh.
        with pytest.raises(DataSourceUnavailableError):
            repo.dataset()
        assert warehouse.connects == 1
    finally:
        gate.set()


def test_failures_back_off_instead_of_retrying_on_every_request(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset, error=TimeoutError("read timed out"))
    repo = sync_repo(warehouse, clock=clock)

    with pytest.raises(DataSourceUnavailableError, match="did not respond within the configured timeout") as first:
        repo.dataset()
    assert first.value.retry_after == 15
    for _ in range(5):
        with pytest.raises(DataSourceUnavailableError):
            repo.dataset()
    assert warehouse.connects == 1  # no retry storm during the backoff

    clock.advance(16)
    with pytest.raises(DataSourceUnavailableError) as second:
        repo.dataset()
    assert warehouse.connects == 2 and second.value.retry_after == 30  # backoff doubled

    warehouse.error = None
    clock.advance(31)
    assert repo.dataset().products == dataset.products
    assert repo.freshness().last_error is None


def test_stale_snapshot_is_served_when_refresh_fails(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = sync_repo(warehouse, clock=clock, refresh_seconds=300)
    original = repo.dataset()

    clock.advance(301)
    warehouse.error = ConnectionRefusedError("connection refused")
    assert repo.dataset() is original  # refresh failed, previous validated snapshot served
    fresh = repo.freshness()
    assert fresh.stale and not fresh.refreshing
    assert fresh.last_error == "Databricks could not be reached."
    assert fresh.age_seconds == pytest.approx(301) and fresh.next_retry_in_seconds == pytest.approx(15)
    assert warehouse.connects == 2


def test_requests_never_wait_on_a_background_refresh_when_a_snapshot_exists(dataset) -> None:
    clock = FakeClock()
    gate = threading.Event()
    gate.set()
    warehouse = FakeWarehouse(dataset, gate=gate)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), clock=clock, refresh_seconds=300, wait_seconds=5)
    original = repo.dataset()

    gate.clear()  # the next refresh blocks inside "network I/O"
    clock.advance(301)
    started = time.monotonic()
    assert repo.dataset() is original
    assert repo.dataset() is original
    assert time.monotonic() - started < 0.5  # no lock held during the blocked refresh
    assert repo.freshness().refreshing and warehouse.connects == 2

    gate.set()
    deadline = time.monotonic() + 5
    while repo.freshness().refreshing and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not repo.freshness().stale and warehouse.connects == 2


# --- Error sanitising ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "category"),
    [
        (TimeoutError("timed out"), "timeout"),
        (type("MaxRetryDurationError", (Exception,), {})("retry budget exceeded"), "timeout"),
        (Exception("HTTP 403 Forbidden: PERMISSION_DENIED"), "auth"),
        (Exception("Invalid access token"), "auth"),
        (Exception("[TABLE_OR_VIEW_NOT_FOUND] The table cannot be found"), "not_found"),
        (ConnectionRefusedError("refused"), "network"),
        (Exception("division by zero"), "query"),
        (DatabricksNotConfiguredError("missing"), "not_configured"),
    ],
)
def test_classify_error(exc: Exception, category: str) -> None:
    assert classify_error(exc) == category


def test_redact_removes_configured_secrets_urls_and_tokens() -> None:
    settings = make_settings()
    text = (
        f"POST https://{HOST}{HTTP_PATH}?x=1 failed; host={HOST} path={HTTP_PATH} "
        f"Authorization: Bearer {TOKEN} token={TOKEN} other dapiabcdef0123456789abcdef"
    )
    cleaned = redact(text, settings)
    for secret in (HOST, HTTP_PATH, TOKEN, "dapiabcdef0123456789abcdef", "https://"):
        assert secret not in cleaned
    assert len(sanitize_error(Exception("x" * 5000), settings)) <= 300


def test_sanitized_errors_in_logs_and_api_responses(dataset, caplog) -> None:
    leaky = RuntimeError(f"Error during request to https://{HOST}{HTTP_PATH} with token {TOKEN} for {HOST}")
    repo = sync_repo(FakeWarehouse(dataset, error=leaky))
    caplog.set_level(logging.DEBUG)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    response = client.get("/api/v1/inventory")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "15"
    assert response.json()["detail"] == "A Databricks query failed. Retrying in about 15 s."
    for secret in (HOST, HTTP_PATH, TOKEN):
        assert secret not in response.text
        assert secret not in caplog.text
    assert "[redacted]" in caplog.text or "[url]" in caplog.text


def test_log_filter_redacts_any_logger_including_tracebacks() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactionFilter(make_settings()))
    log = logging.getLogger("databricks.sql.test_redaction")
    log.addHandler(handler)
    log.propagate = False
    try:
        try:
            raise RuntimeError(f"bad token {TOKEN}")
        except RuntimeError:
            log.exception("connecting to %s via %s", HOST, HTTP_PATH)
    finally:
        log.removeHandler(handler)
    output = stream.getvalue()
    assert "connecting to [redacted] via [redacted]" in output
    for secret in (HOST, HTTP_PATH, TOKEN):
        assert secret not in output


# --- API freshness metadata ------------------------------------------------------------------------


def test_stale_responses_carry_freshness_headers_and_status(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = sync_repo(warehouse, clock=clock, refresh_seconds=300)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo

    ok = client.get("/api/v1/products", params={"page_size": 1})
    assert ok.status_code == 200
    assert ok.headers["X-Data-Source"] == "databricks" and ok.headers["X-Data-Stale"] == "false"
    assert "X-Data-Refresh-Failed" not in ok.headers

    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    stale = client.get("/api/v1/products", params={"page_size": 1})
    assert stale.status_code == 200 and stale.json()["total"] == SMALL.num_products
    assert stale.headers["X-Data-Stale"] == "true" and stale.headers["X-Data-Refresh-Failed"] == "true"
    assert stale.headers["X-Data-Age-Seconds"] == "400"

    status = client.get("/api/v1/data-source").json()
    assert status["source"] == "databricks" and status["stale"] is True
    assert status["last_error"] == "Databricks did not respond within the configured timeout."


def test_csv_mode_status_endpoint_never_triggers_a_load(monkeypatch, dataset, tmp_path: Path) -> None:
    write_csv(dataset, tmp_path)
    monkeypatch.setenv("SMARTSTOCK_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    clear_repository_cache()
    client = TestClient(create_app())

    assert client.get("/api/v1/data-source").json()["loaded_at"] is None
    products = client.get("/api/v1/products")
    assert products.headers["X-Data-Source"] == "csv" and products.headers["X-Data-Stale"] == "false"
    status = client.get("/api/v1/data-source").json()
    assert status["source"] == "csv" and status["loaded_at"] is not None and status["last_error"] is None


# --- Manual scripts ----------------------------------------------------------------------------------


def _load_script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def databricks_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", HOST)
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", HTTP_PATH)
    monkeypatch.setenv("DATABRICKS_TOKEN", TOKEN)
    get_databricks_settings.cache_clear()
    yield
    get_databricks_settings.cache_clear()


def test_check_script_sanitizes_connection_errors(databricks_env, monkeypatch, capsys) -> None:
    script = _load_script("check_databricks_connection")

    @contextmanager
    def failing(settings):
        raise RuntimeError(f"cannot reach https://{HOST}{HTTP_PATH} (host {HOST}, token {TOKEN})")
        yield  # pragma: no cover

    monkeypatch.setattr(script, "databricks_connection", failing)
    assert script.main() == 1
    output = capsys.readouterr()
    for secret in (HOST, HTTP_PATH, TOKEN):
        assert secret not in output.out + output.err
    assert "Connection failed: RuntimeError" in output.err


@pytest.mark.parametrize(("tables", "code"), [(["suppliers", "products", "sales", "inventory", "purchase_orders"], 0), (["suppliers"], 3)])
def test_check_script_reports_expected_tables(databricks_env, monkeypatch, capsys, tables, code) -> None:
    script = _load_script("check_databricks_connection")
    Row = dataclasses.make_dataclass("Row", ["database", "tableName", "isTemporary"])

    class Cursor:
        def execute(self, sql):
            self.sql = sql

        def fetchone(self):
            return ("workspace", "smartstock_retail", 1)

        def fetchall(self):
            assert self.sql == "SHOW TABLES IN `workspace`.`smartstock_retail`"
            return [Row("smartstock_retail", t, False) for t in tables]

    @contextmanager
    def connect(settings):
        class Connection:
            @contextmanager
            def cursor(self):
                yield Cursor()

        yield Connection()

    monkeypatch.setattr(script, "databricks_connection", connect)
    assert script.main() == code
    out = capsys.readouterr().out
    assert "Timeouts: socket 30s, up to 3 attempts within 60s, statement 60s" in out
    assert HOST not in out


def test_loader_refuses_a_schema_the_ddl_does_not_create(databricks_env, monkeypatch, dataset, tmp_path, capsys) -> None:
    write_csv(dataset, tmp_path)
    monkeypatch.setenv("DATABRICKS_SCHEMA", "some_other_schema")
    get_databricks_settings.cache_clear()
    script = _load_script("load_synthetic_data")
    monkeypatch.setattr(script, "databricks_connection", lambda *a, **k: pytest.fail("must not connect"))

    assert script.main(["--data-dir", str(tmp_path), "--yes"]) == 3
    assert "workspace.smartstock_retail" in capsys.readouterr().err
