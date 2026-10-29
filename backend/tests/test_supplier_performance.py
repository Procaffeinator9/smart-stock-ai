"""GET /api/v1/suppliers/performance and /api/v1/suppliers/{id}/performance: reconciliation with the
Purchase Orders, Sales, Inventory and supplier APIs; on-time definitions and sample sizes; each
"Needs attention" rule at its boundary; route ordering and unknown IDs; caching per data snapshot;
and the loading/empty/stale states. The Databricks warehouse is a fake; nothing connects."""

import csv
import dataclasses
import os
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.analytics.suppliers as supplier_analytics
from app.analytics.suppliers import attention_flags
from app.data.repository import DatabricksRepository, get_repository
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from tests.test_data_api import all_rows, make_client
from tests.test_databricks_mode import configure, use_fake_warehouse, wait_until
from tests.test_databricks_repository import FakeClock, FakeWarehouse, make_settings

SMALL = GeneratorConfig(seed=25, num_suppliers=5, num_products=30, num_stores=3, num_days=60)  # has overdue orders
AS_OF = SMALL.end_date
SCORECARD = "/api/v1/suppliers/performance"
OPEN = ("PLACED", "IN_TRANSIT")


def detail_path(supplier_id: str) -> str:
    return f"/api/v1/suppliers/{supplier_id}/performance"


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def csv_dir(dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("suppliers")
    write_csv(dataset, directory)
    return directory


@pytest.fixture
def client(monkeypatch, csv_dir) -> TestClient:
    return make_client(monkeypatch, csv_dir)


# --- Reconciliation with the existing APIs -------------------------------------------------------


def test_scorecard_covers_every_supplier_and_reconciles_with_purchase_orders(client, dataset) -> None:
    body = client.get(SCORECARD).json()
    assert body["status"] == "ok" and body["source"] == "csv" and body["as_of"] == AS_OF.isoformat()
    rows = body["items"]
    assert sorted(r["supplier_id"] for r in rows) == sorted(s.supplier_id for s in dataset.suppliers)
    assert body["total"] == len(rows) == body["network"]["suppliers"] == SMALL.num_suppliers

    po = client.get("/api/v1/purchase-orders/summary").json()
    cancelled_value = next(s["value"] for s in po["by_status"] if s["status"] == "CANCELLED")
    assert sum(r["orders"] for r in rows) == body["network"]["orders"] == po["totals"]["orders"]
    assert sum(r["spend"] for r in rows) == pytest.approx(po["totals"]["value"] - cancelled_value)
    for field, expected in (("on_time", "on_time"), ("late", "late"), ("delivered", "delivered")):
        assert sum(r[field] for r in rows) == po["delivery"][expected]
    assert sum(r["overdue_orders"] for r in rows) == po["overdue"]["orders"] == body["network"]["overdue_orders"]
    assert sum(r["open_orders"] for r in rows) == po["open"]["orders"]
    assert body["network"]["on_time_rate"] == po["delivery"]["on_time_rate"]


def test_each_row_matches_the_purchase_order_summary_for_that_supplier(client) -> None:
    for row in client.get(SCORECARD).json()["items"]:
        po = client.get("/api/v1/purchase-orders/summary", params={"supplier_id": row["supplier_id"]}).json()
        delivery = po["delivery"]
        assert row["on_time_rate"] == delivery["on_time_rate"]
        assert row["sample_size"] == delivery["delivered"] + delivery["overdue_open"]
        assert row["delivered_only_on_time_rate"] == delivery["delivered_only_on_time_rate"]
        assert (row["open_orders"], row["overdue_orders"], row["cancelled"]) == (
            po["open"]["orders"], po["overdue"]["orders"], po["cancellation"]["cancelled"]
        )
        listed = client.get("/api/v1/purchase-orders", params={"supplier_id": row["supplier_id"], "page_size": 1}).json()
        assert listed["total"] == row["orders"]


def test_products_revenue_and_stockouts_match_the_sales_and_supplier_apis(client) -> None:
    body = client.get(SCORECARD).json()
    period = body["period"]
    suppliers = {s["supplier_id"]: s for s in all_rows(client, "/api/v1/suppliers")}
    for row in body["items"]:
        assert row["products"] == suppliers[row["supplier_id"]]["product_count"]
        sales = client.get(
            "/api/v1/sales/summary",
            params={"supplier_id": row["supplier_id"], "date_from": period["date_from"], "date_to": period["date_to"]},
        ).json()["kpis"]["current"]
        assert row["revenue"] == sales["revenue"]
        assert row["units_sold"] == sales["units"]
        assert row["stockout_days"] == sales["stockout_days"]
    assert sum(r["revenue"] for r in body["items"]) == pytest.approx(body["network"]["revenue"])


def test_at_risk_positions_match_the_inventory_worklist(client, dataset) -> None:
    body = client.get(SCORECARD).json()
    positions = all_rows(client, "/api/v1/inventory")
    for row in body["items"]:
        mine = [p for p in positions if p["supplier_id"] == row["supplier_id"]]
        assert row["positions"] == len(mine)
        assert row["at_risk_positions"] == sum(p["status"] in ("critical", "out_of_stock") for p in mine)
        assert row["low_positions"] == sum(p["status"] == "low" for p in mine)
    assert body["network"]["positions"] == len(positions)


# --- Definitions ---------------------------------------------------------------------------------


def test_observed_reliability_and_lead_time_are_measured_separately_from_stated_values(client, dataset) -> None:
    rows = {r["supplier_id"]: r for r in client.get(SCORECARD).json()["items"]}
    for supplier in dataset.suppliers:
        row = rows[supplier.supplier_id]
        orders = [po for po in dataset.purchase_orders if po.supplier_id == supplier.supplier_id]
        delivered = [po for po in orders if po.actual_delivery_date]
        on_time = [po for po in delivered if po.actual_delivery_date <= po.expected_delivery_date]  # on the date = on time
        overdue = [po for po in orders if po.order_status in OPEN and po.expected_delivery_date < AS_OF]
        assert row["stated_reliability"] == float(supplier.reliability_score)
        assert row["stated_lead_time_days"] == supplier.lead_time_days
        assert row["sample_size"] == len(delivered) + len(overdue)
        assert row["on_time_rate"] == round(len(on_time) / row["sample_size"], 4)
        assert row["reliability_gap"] == round(row["on_time_rate"] - row["stated_reliability"], 4)
        lead = sum((po.actual_delivery_date - po.order_date).days for po in delivered) / len(delivered)
        assert row["observed_lead_time_days"] == round(lead, 2)
        assert row["lead_time_gap_days"] == round(round(lead, 2) - supplier.lead_time_days, 2)
        spend = sum(po.unit_cost * po.quantity_ordered for po in orders if po.order_status != "CANCELLED")
        assert row["spend"] == float(spend.quantize(Decimal("0.01")))


def test_recent_trend_compares_the_last_30_days_of_promised_dates_with_the_30_before(client, dataset) -> None:
    rows = {r["supplier_id"]: r for r in client.get(SCORECARD).json()["items"]}

    def window(orders, start, end):
        known = [
            po for po in orders
            if start <= po.expected_delivery_date <= end
            and (po.actual_delivery_date is not None or (po.order_status in OPEN and po.expected_delivery_date < AS_OF))
        ]
        good = [po for po in known if po.actual_delivery_date and po.actual_delivery_date <= po.expected_delivery_date]
        return (round(len(good) / len(known), 4) if known else None), len(known)

    for supplier_id, row in rows.items():
        orders = [po for po in dataset.purchase_orders if po.supplier_id == supplier_id]
        assert (row["recent_on_time_rate"], row["recent_sample"]) == window(orders, AS_OF - timedelta(days=29), AS_OF)
        assert (row["previous_on_time_rate"], row["previous_sample"]) == window(
            orders, AS_OF - timedelta(days=59), AS_OF - timedelta(days=30)
        )


# --- Needs attention rules -------------------------------------------------------------------------


def healthy_row(**overrides) -> dict:
    row = {
        "on_time_rate": 0.9, "sample_size": 200, "overdue_orders": 0, "max_days_overdue": None,
        "lead_time_gap_days": 0.2, "observed_lead_time_days": 5.2, "stated_lead_time_days": 5,
        "positions": 40, "at_risk_positions": 2, "recent_on_time_rate": 0.9, "recent_sample": 60,
        "previous_on_time_rate": 0.9, "previous_sample": 60, "reliability_gap": 0.0, "stated_reliability": 0.9,
    }
    return {**row, **overrides}


def codes(row: dict) -> list[str]:
    return [f["code"] for f in attention_flags(row)]


def test_a_healthy_supplier_has_no_flags() -> None:
    assert attention_flags(healthy_row()) == []


@pytest.mark.parametrize(
    ("overrides", "flagged"),
    [
        ({"on_time_rate": 0.7499, "reliability_gap": 0.0}, True),
        ({"on_time_rate": 0.75, "reliability_gap": 0.0}, False),  # at the target is not below it
        ({"on_time_rate": 0.5, "sample_size": 19, "reliability_gap": 0.0}, False),  # too few orders to judge
    ],
)
def test_low_on_time_rule(overrides, flagged) -> None:
    assert ("low_on_time" in codes(healthy_row(**overrides))) is flagged


@pytest.mark.parametrize(("overdue", "flagged"), [(1, False), (2, True)])
def test_overdue_orders_rule(overdue, flagged) -> None:
    row = healthy_row(overdue_orders=overdue, max_days_overdue=3)
    assert ("overdue_orders" in codes(row)) is flagged


@pytest.mark.parametrize(
    ("gap", "stated", "flagged"),
    [(1.0, 10, True), (0.99, 10, False), (0.5, 2, True), (0.49, 2, False), (None, 5, False)],
)
def test_lead_time_slip_rule(gap, stated, flagged) -> None:
    row = healthy_row(lead_time_gap_days=gap, stated_lead_time_days=stated, observed_lead_time_days=None if gap is None else stated + gap)
    assert ("lead_time_slip" in codes(row)) is flagged


@pytest.mark.parametrize(("at_risk", "positions", "flagged"), [(3, 20, True), (2, 20, False), (0, 0, False)])
def test_at_risk_stock_rule(at_risk, positions, flagged) -> None:
    assert ("at_risk_stock" in codes(healthy_row(at_risk_positions=at_risk, positions=positions))) is flagged


@pytest.mark.parametrize(
    ("recent", "previous", "samples", "flagged"),
    [(0.75, 0.85, 20, True), (0.76, 0.85, 20, False), (0.5, 0.9, 19, False), (None, 0.9, 20, False)],
)
def test_declining_on_time_rule(recent, previous, samples, flagged) -> None:
    row = healthy_row(recent_on_time_rate=recent, previous_on_time_rate=previous, recent_sample=samples, previous_sample=samples)
    assert ("declining_on_time" in codes(row)) is flagged


@pytest.mark.parametrize(
    ("gap", "sample", "flagged"), [(-0.04, 100, True), (-0.039, 100, False), (-0.2, 99, False), (0.05, 200, False)]
)
def test_below_stated_reliability_rule(gap, sample, flagged) -> None:
    row = healthy_row(reliability_gap=gap, sample_size=sample, on_time_rate=0.9 + gap, stated_reliability=0.9)
    assert ("below_stated_reliability" in codes(row)) is flagged


def test_every_flag_explains_itself_with_the_numbers() -> None:
    row = healthy_row(
        on_time_rate=0.7, sample_size=150, overdue_orders=3, max_days_overdue=4, lead_time_gap_days=1.5,
        observed_lead_time_days=6.5, positions=20, at_risk_positions=5, recent_on_time_rate=0.6,
        previous_on_time_rate=0.8, reliability_gap=-0.1, stated_reliability=0.8,
    )
    flags = {f["code"]: f for f in attention_flags(row)}
    assert set(flags) == {"low_on_time", "overdue_orders", "lead_time_slip", "at_risk_stock", "declining_on_time", "below_stated_reliability"}
    assert "70.0% on time over 150 orders" in flags["low_on_time"]["reason"]
    assert "3 open orders" in flags["overdue_orders"]["reason"] and "4 days" in flags["overdue_orders"]["reason"]
    assert "6.5 days" in flags["lead_time_slip"]["reason"] and "stated 5 days" in flags["lead_time_slip"]["reason"]
    assert "5 of 20" in flags["at_risk_stock"]["reason"] and "does not by itself mean" in flags["at_risk_stock"]["reason"]
    assert "60.0%" in flags["declining_on_time"]["reason"] and "80.0%" in flags["declining_on_time"]["reason"]
    assert "10.0 points below" in flags["below_stated_reliability"]["reason"]
    assert all(f["label"] for f in flags.values())


def test_flags_on_generated_data_agree_with_each_row(client) -> None:
    body = client.get(SCORECARD).json()
    for row in body["items"]:
        assert [f["code"] for f in row["flags"]] == codes(row)
    assert body["network"]["flagged"] == sum(bool(r["flags"]) for r in body["items"])


# --- Filtering, sorting, routes ---------------------------------------------------------------------


def test_search_attention_filter_and_sorting(client, dataset) -> None:
    everyone = client.get(SCORECARD).json()
    flagged = client.get(SCORECARD, params={"attention": "true"}).json()
    unflagged = client.get(SCORECARD, params={"attention": "false"}).json()
    assert flagged["total"] + unflagged["total"] == everyone["total"]
    assert all(r["flags"] for r in flagged["items"]) and not any(r["flags"] for r in unflagged["items"])
    assert flagged["network"] == everyone["network"]  # network totals ignore filters

    by_flags = [len(r["flags"]) for r in everyone["items"]]
    assert by_flags == sorted(by_flags, reverse=True)
    rates = [r["on_time_rate"] for r in client.get(SCORECARD, params={"sort": "on_time_rate", "order": "asc"}).json()["items"]]
    assert rates == sorted(rates)
    names = [r["supplier_name"].lower() for r in client.get(SCORECARD, params={"sort": "supplier_name", "order": "asc"}).json()["items"]]
    assert names == sorted(names)

    target = dataset.suppliers[2]
    found = client.get(SCORECARD, params={"search": target.supplier_name.upper()}).json()
    assert target.supplier_id in [r["supplier_id"] for r in found["items"]]
    assert client.get(SCORECARD, params={"search": target.supplier_id.lower()}).json()["total"] == 1
    for params in ({"sort": "risk_score"}, {"order": "sideways"}, {"attention": "maybe"}):
        assert client.get(SCORECARD, params=params).status_code == 422


def test_routes_do_not_collide_and_unknown_suppliers_are_404(client, dataset) -> None:
    assert client.get(SCORECARD).json()["status"] == "ok"  # not read as supplier "performance"
    supplier = dataset.suppliers[0]
    assert client.get(f"/api/v1/suppliers/{supplier.supplier_id}").json()["supplier_name"] == supplier.supplier_name
    assert client.get("/api/v1/suppliers").json()["total"] == SMALL.num_suppliers

    missing = client.get(detail_path("SUP-9999"))
    assert missing.status_code == 404 and missing.json()["detail"] == "Supplier 'SUP-9999' not found"
    assert client.get(detail_path("X" * 33)).status_code == 422


def test_detail_adds_up_to_the_scorecard_row(client, dataset) -> None:
    rows = {r["supplier_id"]: r for r in client.get(SCORECARD).json()["items"]}
    for supplier in dataset.suppliers:
        body = client.get(detail_path(supplier.supplier_id)).json()
        row = body["scorecard"]
        assert row == rows[supplier.supplier_id]
        assert body["supplier"]["contact_email"] == supplier.contact_email
        assert body["supplier"]["stated_reliability"] == float(supplier.reliability_score)

        months = body["monthly"]
        assert sum(m["on_time"] for m in months) == row["on_time"]
        assert sum(m["late"] for m in months) == row["late"]
        assert sum(m["overdue"] for m in months) == row["overdue_orders"]
        assert all(m["month"].endswith("-01") for m in months)

        late = body["late_distribution"]
        assert [b["label"] for b in late] == ["On time", "1 day", "2 days", "3 days", "4 days", "5+ days"]
        assert sum(b["orders"] for b in late) == row["delivered"] and late[0]["orders"] == row["on_time"]

        products = body["products"]
        assert len(products) == row["products"]
        assert sum(p["revenue"] for p in products) == pytest.approx(row["revenue"])
        assert sum(p["stockout_days"] for p in products) == row["stockout_days"]
        assert sum(p["at_risk_stores"] for p in products) == row["at_risk_positions"]
        assert all(sum(p["status_counts"].values()) == p["stores"] for p in products)

        recent = body["recent_orders"]
        assert len(recent) == min(10, row["orders"]) and {o["supplier_id"] for o in recent} <= {supplier.supplier_id}
        assert [o["order_date"] for o in recent] == sorted((o["order_date"] for o in recent), reverse=True)
        overdue = body["overdue_orders"]
        assert len(overdue) == min(20, row["overdue_orders"]) and all(o["is_overdue"] for o in overdue)
        assert [o["days_overdue"] for o in overdue] == sorted((o["days_overdue"] for o in overdue), reverse=True)


def test_products_are_listed_most_at_risk_first(client, dataset) -> None:
    rank = {"out_of_stock": 0, "critical": 1, "low": 2, "healthy": 3}
    for supplier in dataset.suppliers:
        products = client.get(detail_path(supplier.supplier_id)).json()["products"]
        keys = [(rank[p["worst_status"]], -p["revenue"]) for p in products]
        assert keys == sorted(keys)


# --- Caching ----------------------------------------------------------------------------------------


@pytest.fixture
def count_scorecards(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = supplier_analytics._scorecard

    def counting(dataset):
        calls.append(1)
        return original(dataset)

    monkeypatch.setattr(supplier_analytics, "_scorecard", counting)
    return calls


def test_scorecard_is_computed_once_per_snapshot_and_recomputed_when_files_change(monkeypatch, dataset, tmp_path, count_scorecards) -> None:
    write_csv(dataset, tmp_path)
    client = make_client(monkeypatch, tmp_path)
    first = client.get(SCORECARD).json()
    client.get(SCORECARD, params={"sort": "spend"})
    client.get(SCORECARD, params={"attention": "true", "search": "a"})
    client.get(detail_path(dataset.suppliers[0].supplier_id))
    assert len(count_scorecards) == 1

    path = tmp_path / "purchase_orders.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    supplier_id = rows[0]["supplier_id"]
    rows[0]["quantity_ordered"] = str(int(rows[0]["quantity_ordered"]) + 10)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    second = client.get(SCORECARD).json()
    assert len(count_scorecards) == 2
    before = next(r for r in first["items"] if r["supplier_id"] == supplier_id)
    after = next(r for r in second["items"] if r["supplier_id"] == supplier_id)
    if rows[0]["order_status"] != "CANCELLED":
        assert after["spend"] > before["spend"]


def test_scorecard_cache_invalidates_after_a_databricks_refresh(dataset, count_scorecards) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), clock=clock, start=lambda fn: fn(), refresh_seconds=300)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo

    before = client.get(SCORECARD).json()
    client.get(SCORECARD)
    assert len(count_scorecards) == 1 and warehouse.connects == 1

    row = list(warehouse.tables["sales"][0])
    row[4] += 7  # quantity_sold
    warehouse.tables["sales"][0] = tuple(row)
    clock.advance(301)
    client.get(SCORECARD)
    after = client.get(SCORECARD).json()

    assert warehouse.connects == 2 and len(count_scorecards) == 2
    assert sum(r["units_sold"] for r in after["items"]) == sum(r["units_sold"] for r in before["items"]) + 7


# --- Data sources and states ------------------------------------------------------------------------


def test_databricks_and_csv_modes_produce_identical_results(monkeypatch, dataset, csv_dir) -> None:
    supplier_id = dataset.suppliers[1].supplier_id

    def fetch(client: TestClient) -> tuple[dict, dict]:
        scorecard = client.get(SCORECARD, params={"sort": "revenue"}).json()
        detail = client.get(detail_path(supplier_id)).json()
        strip = lambda body: {k: v for k, v in body.items() if k not in ("freshness", "source")}  # noqa: E731
        return strip(scorecard), strip(detail)

    configure(monkeypatch, "csv", csv_dir)
    csv_scorecard, csv_detail = fetch(TestClient(create_app()))

    warehouse = FakeWarehouse(dataset, as_strings=True)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    client = TestClient(create_app())
    response = client.get(SCORECARD)
    assert response.headers["X-Data-Source"] == "databricks" and response.json()["source"] == "databricks"
    db_scorecard, db_detail = fetch(client)

    assert db_scorecard == csv_scorecard
    assert db_detail == csv_detail
    assert warehouse.connects == 1


def test_initial_databricks_load_returns_503_with_retry_after(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        for path in (SCORECARD, detail_path(dataset.suppliers[0].supplier_id)):
            loading = client.get(path)
            assert loading.status_code == 503
            assert "still loading" in loading.json()["detail"] and int(loading.headers["Retry-After"]) >= 1
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
    assert client.get(SCORECARD).json()["status"] == "ok"
    assert warehouse.connects == 1


def test_data_without_inventory_returns_an_empty_status(monkeypatch, dataset, tmp_path) -> None:
    write_csv(dataclasses.replace(dataset, inventory=[]), tmp_path)
    client = make_client(monkeypatch, tmp_path)
    for path in (SCORECARD, detail_path(dataset.suppliers[0].supplier_id)):
        body = client.get(path).json()
        assert body["status"] == "empty" and "no inventory snapshots" in body["reason"]
        assert body["freshness"]["source"] == "csv"
    assert client.get(detail_path("SUP-9999")).status_code == 404


def test_stale_data_and_refresh_failure_are_reported(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(
        make_settings(), connect=warehouse.connect(), clock=clock,
        now=lambda: datetime(2026, 10, 27, 9, 0, tzinfo=UTC), start=lambda fn: fn(), refresh_seconds=300,
    )
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    assert client.get(SCORECARD).json()["freshness"]["stale"] is False

    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    response = client.get(SCORECARD)
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["freshness"]["stale"] is True and body["freshness"]["last_error"]
    assert response.headers["X-Data-Refresh-Failed"] == "true"
    detail = client.get(detail_path(dataset.suppliers[0].supplier_id))
    assert detail.json()["freshness"]["stale"] is True and detail.headers["X-Data-Stale"] == "true"


def test_supplier_performance_schema_is_documented() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    for path in ("/api/v1/suppliers/performance", "/api/v1/suppliers/{supplier_id}/performance"):
        schema = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["discriminator"]["propertyName"] == "status"
    components = spec["components"]["schemas"]
    assert {"SupplierScorecardOk", "SupplierDetailOk", "SupplierScore", "AttentionFlag", "SupplierPerformanceEmpty"} <= set(components)
    score = components["SupplierScore"]["properties"]
    assert "stated, not measured" in score["stated_reliability"]["description"]
    assert "not proof of supplier causation" in score["stockout_days"]["description"]
