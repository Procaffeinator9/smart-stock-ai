"""GET /api/v1/overview: equivalence with the offline export and across data sources, caching per
data snapshot (and invalidation), loading/empty/stale states, and the documented schema.
The Databricks warehouse is a fake; nothing connects."""

import csv
import dataclasses
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.v1.endpoints.overview as overview_endpoint
from app.analytics.overview import build_overview_snapshot
from app.data.repository import DatabricksRepository, get_repository
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from tests.test_databricks_mode import configure, use_fake_warehouse, wait_until
from tests.test_databricks_repository import FakeClock, FakeWarehouse, make_settings

SMALL = GeneratorConfig(seed=17, num_suppliers=4, num_products=16, num_stores=3, num_days=21)
SOURCE_FIELDS = ("source", "seed", "generator")


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture
def csv_dir(dataset, tmp_path: Path) -> Path:
    write_csv(dataset, tmp_path)
    return tmp_path


def metrics(body: dict) -> dict:
    """The overview minus envelope, freshness, and source labels (what must match across sources)."""
    out = {k: v for k, v in body.items() if k not in ("status", "freshness", "products")}
    out["meta"] = {k: v for k, v in out["meta"].items() if k not in SOURCE_FIELDS}
    return out


@pytest.fixture
def count_builds(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = overview_endpoint.build_overview_for

    def counting(dataset):
        calls.append(1)
        return original(dataset)

    monkeypatch.setattr(overview_endpoint, "build_overview_for", counting)
    return calls


def test_csv_overview_matches_the_offline_export(monkeypatch, dataset, csv_dir) -> None:
    configure(monkeypatch, "csv", csv_dir)
    response = TestClient(create_app()).get("/api/v1/overview")

    assert response.status_code == 200 and response.headers["X-Data-Source"] == "csv"
    body = response.json()
    assert body["status"] == "ok" and body["meta"]["source"] == "csv"
    assert body["meta"]["seed"] is None and body["meta"]["as_of"] == SMALL.end_date.isoformat()
    assert "products" not in body
    assert metrics(body) == metrics(build_overview_snapshot(dataset))


def test_databricks_and_csv_modes_produce_identical_metrics(monkeypatch, dataset, csv_dir) -> None:
    configure(monkeypatch, "csv", csv_dir)
    csv_body = TestClient(create_app()).get("/api/v1/overview").json()

    warehouse = FakeWarehouse(dataset, as_strings=True)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    response = TestClient(create_app()).get("/api/v1/overview")

    assert response.status_code == 200 and response.headers["X-Data-Source"] == "databricks"
    db_body = response.json()
    assert db_body["meta"]["source"] == "databricks" and db_body["freshness"]["source"] == "databricks"
    assert metrics(db_body) == metrics(csv_body)
    assert warehouse.connects == 1


def test_overview_is_computed_once_per_csv_snapshot_and_recomputed_when_files_change(
    monkeypatch, csv_dir, count_builds
) -> None:
    configure(monkeypatch, "csv", csv_dir)
    client = TestClient(create_app())
    first = client.get("/api/v1/overview").json()
    client.get("/api/v1/overview")
    client.get("/api/v1/overview")
    assert len(count_builds) == 1

    sales = csv_dir / "sales.csv"
    with sales.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["quantity_sold"] = str(int(rows[0]["quantity_sold"]) + 5)
    with sales.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    stat = sales.stat()
    os.utime(sales, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    second = client.get("/api/v1/overview").json()
    assert len(count_builds) == 2
    assert sum(second["daily"]["units"]) == sum(first["daily"]["units"]) + 5
    client.get("/api/v1/overview")
    assert len(count_builds) == 2


def test_overview_cache_invalidates_after_a_databricks_refresh(dataset, count_builds) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(
        make_settings(), connect=warehouse.connect(), clock=clock, start=lambda fn: fn(), refresh_seconds=300
    )
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo

    before = client.get("/api/v1/overview").json()
    client.get("/api/v1/overview")
    assert len(count_builds) == 1 and warehouse.connects == 1

    row = list(warehouse.tables["sales"][0])
    row[4] += 7  # quantity_sold
    warehouse.tables["sales"][0] = tuple(row)
    clock.advance(301)  # snapshot is due; the next request refreshes it (synchronously here)
    client.get("/api/v1/overview")
    after = client.get("/api/v1/overview").json()

    assert warehouse.connects == 2 and len(count_builds) == 2
    assert sum(after["daily"]["units"]) == sum(before["daily"]["units"]) + 7


def test_initial_databricks_load_returns_503_with_retry_after(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        loading = client.get("/api/v1/overview")
        assert loading.status_code == 503
        assert "still loading" in loading.json()["detail"] and int(loading.headers["Retry-After"]) >= 1
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
    assert client.get("/api/v1/overview").json()["status"] == "ok"
    assert warehouse.connects == 1


def test_empty_dataset_returns_an_empty_status(monkeypatch, dataset, tmp_path) -> None:
    write_csv(dataclasses.replace(dataset, sales=[], inventory=[], purchase_orders=[]), tmp_path)
    configure(monkeypatch, "csv", tmp_path)
    response = TestClient(create_app()).get("/api/v1/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty" and body["source"] == "csv"
    assert "no inventory snapshots" in body["reason"] and body["freshness"]["source"] == "csv"


def test_stale_data_and_refresh_failure_are_reported(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(
        make_settings(),
        connect=warehouse.connect(),
        clock=clock,
        now=lambda: datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
        start=lambda fn: fn(),
        refresh_seconds=300,
    )
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    assert client.get("/api/v1/overview").json()["freshness"]["stale"] is False

    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    response = client.get("/api/v1/overview")
    body = response.json()

    assert response.status_code == 200 and body["status"] == "ok"  # stale snapshot is still served
    assert body["freshness"]["stale"] is True and body["freshness"]["age_seconds"] == 400
    assert body["freshness"]["last_error"] == "Databricks did not respond within the configured timeout."
    assert body["freshness"]["loaded_at"].startswith("2026-10-27T09:00:00")
    assert response.headers["X-Data-Stale"] == "true" and response.headers["X-Data-Refresh-Failed"] == "true"


def test_overview_schema_is_documented() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    operation = spec["paths"]["/api/v1/overview"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "status"
    components = spec["components"]["schemas"]
    assert {"OverviewOk", "OverviewEmpty", "OverviewMeta", "DailySeries"} <= set(components)
    assert "not today's date" in components["OverviewMeta"]["properties"]["as_of"]["description"]
