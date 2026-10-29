"""Switching SMARTSTOCK_DATA_SOURCE between csv and databricks, end to end through the real
repository factory, app startup (lifespan), and API. The warehouse is a fake; nothing connects."""

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.data.repository as repository_module
from app.core.config import get_settings
from app.data.repository import CsvRepository, DatabricksRepository, clear_repository_cache
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from tests.test_databricks_repository import FakeWarehouse

SMALL = GeneratorConfig(seed=13, num_suppliers=4, num_products=14, num_stores=2, num_days=15)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture
def csv_dir(dataset, tmp_path: Path) -> Path:
    write_csv(dataset, tmp_path)
    return tmp_path


def configure(monkeypatch, source: str, csv_dir: Path, **env: str) -> None:
    monkeypatch.setenv("SMARTSTOCK_DATA_SOURCE", source)
    monkeypatch.setenv("SMARTSTOCK_DATA_DIR", str(csv_dir))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    clear_repository_cache()


def use_fake_warehouse(monkeypatch, warehouse: FakeWarehouse) -> list[dict]:
    """Route the factory's DatabricksRepository to the fake warehouse; returns the factory kwargs seen."""
    made: list[dict] = []

    def factory(settings, **kwargs):
        made.append(kwargs)
        return DatabricksRepository(settings, connect=warehouse.connect(), **kwargs)

    monkeypatch.setattr(repository_module, "DatabricksRepository", factory)
    return made


def wait_until(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_databricks_mode_startup_and_status_endpoints_query_nothing(monkeypatch, dataset, csv_dir) -> None:
    warehouse = FakeWarehouse(dataset)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)

    with TestClient(create_app()) as client:  # runs the lifespan (startup and shutdown)
        assert client.get("/api/v1/health").json()["data_source"] == "databricks"
        status = client.get("/api/v1/data-source").json()
        assert status["source"] == "databricks" and status["loaded_at"] is None and status["refreshing"] is False
        time.sleep(0.2)
    assert warehouse.connects == 0


def test_factory_uses_configured_refresh_and_wait(monkeypatch, dataset, csv_dir) -> None:
    made = use_fake_warehouse(monkeypatch, FakeWarehouse(dataset))
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_REFRESH_SECONDS="3600", SMARTSTOCK_DATA_WAIT_SECONDS="2")
    repository_module.get_repository(get_settings())
    assert made == [{"refresh_seconds": 3600.0, "wait_seconds": 2.0}]


def test_slow_first_refresh_returns_503_then_matches_csv_mode(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, as_strings=True, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        first = client.get("/api/v1/inventory")
        assert first.status_code == 503
        assert "still loading" in first.json()["detail"] and int(first.headers["Retry-After"]) >= 1
        assert client.get("/api/v1/data-source").json()["refreshing"] is True
        assert client.get("/api/v1/products").status_code == 503
        assert warehouse.connects == 1  # waiting requests share one refresh
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)

    paths = [
        "/api/v1/inventory?page_size=100",
        "/api/v1/inventory?status=out_of_stock&status=critical&page_size=100",
        "/api/v1/products?sort=selling_price&order=desc&page_size=100",
        "/api/v1/purchase-orders?overdue=true&page_size=100",
        "/api/v1/sales?date_from=2026-01-10&date_to=2026-01-11&page_size=100&sort=sale_id",
    ]
    databricks = {path: client.get(path) for path in paths}
    assert all(r.status_code == 200 and r.headers["X-Data-Source"] == "databricks" for r in databricks.values())

    configure(monkeypatch, "csv", csv_dir)  # rollback: same data, CSV source
    csv_client = TestClient(create_app())
    for path in paths:
        csv_body, db_body = csv_client.get(path).json(), databricks[path].json()
        csv_body.pop("source", None)
        assert db_body.pop("source", "databricks") == "databricks"
        assert db_body == csv_body, path
    assert warehouse.connects == 1


def test_rollback_to_csv_needs_only_the_setting_and_a_restart(monkeypatch, dataset, csv_dir) -> None:
    warehouse = FakeWarehouse(dataset)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    assert isinstance(repository_module.get_repository(get_settings()), DatabricksRepository)

    configure(monkeypatch, "csv", csv_dir)  # remove/replace the setting, then restart the API
    client = TestClient(create_app())
    assert isinstance(repository_module.get_repository(get_settings()), CsvRepository)
    response = client.get("/api/v1/products")
    assert response.status_code == 200 and response.headers["X-Data-Source"] == "csv"
    assert client.get("/api/v1/health").json()["data_source"] == "csv"
    assert warehouse.connects == 0


def test_csv_mode_startup_still_preloads_in_the_background(monkeypatch, csv_dir) -> None:
    configure(monkeypatch, "csv", csv_dir)
    with TestClient(create_app()) as client:
        assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
