"""GET /api/v1/purchase-orders/summary and the extended /purchase-orders list: metric definitions and
boundaries (on hand-built orders), reconciliation with the list and the Overview, filters,
backward compatibility, caching per data snapshot, and loading/empty/stale states. The Databricks
warehouse is a fake; nothing connects."""

import csv
import dataclasses
import os
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.analytics.purchase_orders as po_analytics
from app.analytics.purchase_orders import OrderFilters, days_late, days_overdue, purchase_order_summary
from app.data.dataset import RetailDataset
from app.data.repository import DatabricksRepository, get_repository
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from app.synthetic.generator import PurchaseOrder
from tests.test_data_api import all_rows, make_client
from tests.test_databricks_mode import configure, use_fake_warehouse, wait_until
from tests.test_databricks_repository import FakeClock, FakeWarehouse, make_settings

SMALL = GeneratorConfig(seed=25, num_suppliers=5, num_products=30, num_stores=3, num_days=60)  # has overdue orders
AS_OF = SMALL.end_date
SUMMARY, LIST = "/api/v1/purchase-orders/summary", "/api/v1/purchase-orders"
OPEN = ("PLACED", "IN_TRANSIT")


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def csv_dir(dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("purchase_orders")
    write_csv(dataset, directory)
    return directory


@pytest.fixture
def client(monkeypatch, csv_dir) -> TestClient:
    return make_client(monkeypatch, csv_dir)


def value(po) -> Decimal:
    return po.unit_cost * po.quantity_ordered


def money(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("0.01")))


# --- Definitions and boundaries on hand-built orders ---------------------------------------------


@pytest.fixture(scope="module")
def crafted() -> RetailDataset:
    """Orders placed relative to the as-of date, one per boundary case (offsets in days)."""
    base = generate_dataset(GeneratorConfig(seed=3, num_suppliers=2, num_products=4, num_stores=1, num_days=10))
    as_of = base.config.end_date
    product = base.products[0]

    def order(n, status, expected, actual=None, ordered=-20):
        return PurchaseOrder(
            purchase_order_id=f"PO-T{n:03d}",
            supplier_id=product.supplier_id,
            product_id=product.product_id,
            store_id="STR-001",
            order_date=as_of + timedelta(days=ordered),
            expected_delivery_date=as_of + timedelta(days=expected),
            actual_delivery_date=as_of + timedelta(days=actual) if actual is not None else None,
            quantity_ordered=10,
            unit_cost=Decimal("2.50"),
            order_status=status,
        )

    orders = [
        order(1, "DELIVERED", -10, actual=-10),  # delivered exactly on the promised date: on time
        order(2, "DELIVERED", -10, actual=-9),  # 1 day late
        order(3, "DELIVERED", -10, actual=-12),  # early: on time
        order(4, "DELIVERED", -8, actual=-4),  # 4 days late
        order(5, "IN_TRANSIT", 0),  # due on the as-of date: not overdue, first inbound day
        order(6, "IN_TRANSIT", -1),  # overdue 1 day
        order(7, "IN_TRANSIT", -2),  # 2
        order(8, "IN_TRANSIT", -3),  # 3
        order(9, "PLACED", -5),  # 5
        order(10, "IN_TRANSIT", -6),  # 6
        order(11, "IN_TRANSIT", -14),  # 14
        order(12, "IN_TRANSIT", -15),  # 15
        order(13, "PLACED", 13),  # last inbound day
        order(14, "PLACED", 14),  # after the inbound window
        order(15, "CANCELLED", 5),  # cancelled: never open, never inbound
        order(16, "CANCELLED", -30, ordered=-40),  # cancelled, placed before a 30-day window
    ]
    return RetailDataset("csv", base.suppliers, base.products, [], base.inventory, orders)


def test_lateness_helpers_treat_the_promised_date_as_on_time(crafted) -> None:
    by_id = {po.purchase_order_id: po for po in crafted.purchase_orders}
    assert days_late(by_id["PO-T001"]) is None  # on the promised date
    assert days_late(by_id["PO-T003"]) is None  # early
    assert days_late(by_id["PO-T002"]) == 1 and days_late(by_id["PO-T004"]) == 4
    assert days_late(by_id["PO-T006"]) is None  # not delivered
    assert days_overdue(by_id["PO-T005"], crafted.as_of) is None  # due today is not overdue
    assert days_overdue(by_id["PO-T006"], crafted.as_of) == 1
    assert days_overdue(by_id["PO-T015"], crafted.as_of) is None  # cancelled orders are never overdue


def test_on_time_rate_counts_overdue_open_orders_as_late(crafted) -> None:
    delivery = purchase_order_summary(crafted, OrderFilters())["delivery"]
    assert (delivery["delivered"], delivery["on_time"], delivery["late"], delivery["overdue_open"]) == (4, 2, 2, 7)
    assert delivery["on_time_rate"] == round(2 / (4 + 7), 4)
    assert delivery["delivered_only_on_time_rate"] == 0.5
    assert delivery["avg_days_late"] == 2.5 and delivery["max_days_late"] == 4
    assert "overdue open orders" in delivery["on_time_rate_definition"]
    assert "on its promised date is on time" in delivery["on_time_rate_definition"]


def test_overdue_aging_buckets_and_most_overdue_first(crafted) -> None:
    overdue = purchase_order_summary(crafted, OrderFilters())["overdue"]
    assert overdue["orders"] == 7 and overdue["max_days_overdue"] == 15
    assert overdue["avg_days_overdue"] == round((1 + 2 + 3 + 5 + 6 + 14 + 15) / 7, 2)
    assert [(b["label"], b["orders"]) for b in overdue["aging"]] == [
        ("1–2 days", 2),
        ("3–5 days", 2),
        ("6–14 days", 2),
        ("15+ days", 1),
    ]
    assert [o["purchase_order_id"] for o in overdue["top"]] == [f"PO-T{n:03d}" for n in (12, 11, 10, 9, 8, 7, 6)]
    assert [o["days_overdue"] for o in overdue["top"]] == [15, 14, 6, 5, 3, 2, 1]


def test_inbound_schedule_boundaries_partition_open_orders(crafted) -> None:
    summary = purchase_order_summary(crafted, OrderFilters())
    inbound = summary["inbound"]
    assert inbound["date_from"] == crafted.as_of and inbound["date_to"] == crafted.as_of + timedelta(days=13)
    assert len(inbound["days"]) == 14
    assert inbound["days"][0]["orders"] == 1 and inbound["days"][13]["orders"] == 1  # PO-T005, PO-T013
    assert inbound["orders"] == 2 and inbound["later"]["orders"] == 1  # PO-T014
    assert summary["open"]["orders"] == summary["overdue"]["orders"] + inbound["orders"] + inbound["later"]["orders"] == 10


def test_cancellation_rate_is_by_order_date(crafted) -> None:
    everything = purchase_order_summary(crafted, OrderFilters())["cancellation"]
    assert (everything["orders"], everything["cancelled"], everything["rate"]) == (16, 2, 0.125)
    window = purchase_order_summary(crafted, OrderFilters(date_from=crafted.as_of - timedelta(days=30)))["cancellation"]
    assert (window["orders"], window["cancelled"]) == (15, 1)  # PO-T016 was placed before the window
    assert "by order date" in window["definition"]


def test_weekly_series_add_up(crafted) -> None:
    summary = purchase_order_summary(crafted, OrderFilters())
    weeks = summary["weekly_delivery"]
    assert sum(w["on_time"] for w in weeks) == 2 and sum(w["late"] for w in weeks) == 2 and sum(w["overdue"] for w in weeks) == 7
    assert all(w["week_start"].weekday() == 0 and w["date_from"] <= w["date_to"] for w in weeks)
    placed = summary["weekly_orders"]
    assert sum(w["orders"] for w in placed) == 16 and sum(w["cancelled"] for w in placed) == 2
    assert sum(w["days"] for w in placed) == (crafted.as_of - (crafted.as_of - timedelta(days=40))).days + 1


# --- Reconciliation on generated data -----------------------------------------------------------


def test_status_counts_and_values_reconcile_with_the_list(client, dataset) -> None:
    body = client.get(SUMMARY).json()
    assert body["status"] == "ok" and body["as_of"] == AS_OF.isoformat() and body["source"] == "csv"
    totals = body["totals"]
    assert totals["orders"] == len(dataset.purchase_orders)
    assert totals["value"] == money(sum((value(po) for po in dataset.purchase_orders), Decimal(0)))
    assert sum(s["orders"] for s in body["by_status"]) == totals["orders"]
    assert sum(s["units"] for s in body["by_status"]) == totals["units"]
    assert sum(s["value"] for s in body["by_status"]) == pytest.approx(totals["value"])
    for row in body["by_status"]:
        listed = client.get(LIST, params={"status": row["status"], "page_size": 1}).json()
        assert listed["total"] == row["orders"], row["status"]
    rows = all_rows(client, LIST)
    assert len(rows) == totals["orders"] and sum(r["value"] for r in rows) == pytest.approx(totals["value"])
    open_orders = [po for po in dataset.purchase_orders if po.order_status in OPEN]
    assert body["open"] == {"orders": len(open_orders), "value": money(sum((value(po) for po in open_orders), Decimal(0))),
                            "units": sum(po.quantity_ordered for po in open_orders)}


def test_open_and_overdue_match_the_list_and_the_overview(client, dataset) -> None:
    body = client.get(SUMMARY).json()
    overview = client.get("/api/v1/overview").json()["purchase_orders"]["summary"]
    overdue = all_rows(client, LIST, overdue="true")
    assert body["open"]["orders"] == overview["open"]
    assert body["overdue"]["orders"] == overview["overdue"] == len(overdue) > 0
    assert all(r["is_overdue"] and r["is_late"] and r["days_overdue"] >= 1 for r in overdue)
    assert sum(b["orders"] for b in body["overdue"]["aging"]) == body["overdue"]["orders"]
    top = [o["days_overdue"] for o in body["overdue"]["top"]]
    assert top == sorted(top, reverse=True) and len(top) == min(10, len(overdue))
    assert body["overdue"]["orders"] + body["inbound"]["orders"] + body["inbound"]["later"]["orders"] == body["open"]["orders"]


def test_on_time_rates_match_independent_calculations_and_the_overview_is_unchanged(client, dataset) -> None:
    delivery = client.get(SUMMARY).json()["delivery"]
    delivered = [po for po in dataset.purchase_orders if po.actual_delivery_date]
    on_time = [po for po in delivered if po.actual_delivery_date <= po.expected_delivery_date]
    overdue = [po for po in dataset.purchase_orders if po.order_status in OPEN and po.expected_delivery_date < AS_OF]
    assert delivery["on_time_rate"] == round(len(on_time) / (len(delivered) + len(overdue)), 4)
    assert delivery["delivered_only_on_time_rate"] == round(len(on_time) / len(delivered), 4)
    assert delivery["late"] == len(all_rows(client, LIST, delivered_late="true"))

    # The Overview keeps its own definition: delivered in the last 30 days, delivered orders only.
    recent = [po for po in delivered if po.actual_delivery_date > AS_OF - timedelta(days=30)]
    expected = round(sum(po.actual_delivery_date <= po.expected_delivery_date for po in recent) / len(recent), 3)
    assert client.get("/api/v1/overview").json()["purchase_orders"]["summary"]["on_time_rate_last_30_days"] == expected


def test_weekly_series_and_inbound_add_up_on_generated_data(client, dataset) -> None:
    body = client.get(SUMMARY).json()
    assert sum(w["orders"] for w in body["weekly_orders"]) == body["totals"]["orders"]
    assert sum(w["cancelled"] for w in body["weekly_orders"]) == body["cancellation"]["cancelled"]
    first_order = min(po.order_date for po in dataset.purchase_orders)
    assert sum(w["days"] for w in body["weekly_orders"]) == (AS_OF - first_order).days + 1
    assert body["weekly_orders"][0]["date_from"] == first_order.isoformat()
    delivery = body["delivery"]
    assert sum(w["on_time"] + w["late"] for w in body["weekly_delivery"]) == delivery["delivered"]
    assert sum(w["overdue"] for w in body["weekly_delivery"]) == delivery["overdue_open"]
    assert sum(d["orders"] for d in body["inbound"]["days"]) == body["inbound"]["orders"]


def test_order_date_window_and_cancellation_rate(client, dataset) -> None:
    body = client.get(SUMMARY, params={"days": 30}).json()
    start = AS_OF - timedelta(days=29)
    assert body["period"] == {"date_from": start.isoformat(), "date_to": AS_OF.isoformat()}
    in_window = [po for po in dataset.purchase_orders if start <= po.order_date <= AS_OF]
    cancelled = sum(po.order_status == "CANCELLED" for po in in_window)
    assert body["cancellation"] == {
        "orders": len(in_window),
        "cancelled": cancelled,
        "rate": round(cancelled / len(in_window), 4),
        "definition": body["cancellation"]["definition"],
    }
    assert client.get(LIST, params={"days": 30, "page_size": 1}).json()["total"] == len(in_window)
    explicit = client.get(SUMMARY, params={"date_from": start.isoformat(), "date_to": AS_OF.isoformat()}).json()
    assert explicit["totals"] == body["totals"]


def test_scope_filters_apply_to_summary_and_list(client, dataset) -> None:
    supplier = Counter(po.supplier_id for po in dataset.purchase_orders).most_common(1)[0][0]
    category = dataset.products[2].category
    params = {"store_id": "STR-002", "supplier_id": supplier, "category": category}
    products = {p.product_id: p for p in dataset.products}
    expected = [
        po for po in dataset.purchase_orders
        if po.store_id == "STR-002" and po.supplier_id == supplier and products[po.product_id].category == category
    ]
    body = client.get(SUMMARY, params=params).json()
    assert body["filters"] == {**params, "product_id": None}
    assert body["totals"]["orders"] == len(expected) == client.get(LIST, params=params).json()["total"]
    product = expected[0].product_id if expected else dataset.products[0].product_id
    one = client.get(SUMMARY, params={"product_id": product}).json()
    assert one["totals"]["orders"] == sum(po.product_id == product for po in dataset.purchase_orders)


# --- The list: new filters, fields, sorting, compatibility ----------------------------------------


def test_list_rows_keep_existing_fields_and_add_lateness_details(client, dataset) -> None:
    page = client.get(LIST, params={"page_size": 100}).json()
    assert page["source"] == "csv" and page["as_of"] == AS_OF.isoformat()
    existing = {"purchase_order_id", "supplier_id", "supplier_name", "product_id", "product_name", "store_id", "order_date",
                "expected_delivery_date", "actual_delivery_date", "quantity_ordered", "unit_cost", "value", "order_status", "is_late"}
    added = {"category", "is_overdue", "days_overdue", "days_late"}
    assert set(page["items"][0]) == existing | added
    by_id = {po.purchase_order_id: po for po in dataset.purchase_orders}
    for row in all_rows(client, LIST):
        po = by_id[row["purchase_order_id"]]
        late = po.actual_delivery_date is not None and po.actual_delivery_date > po.expected_delivery_date
        assert row["days_late"] == ((po.actual_delivery_date - po.expected_delivery_date).days if late else None)
        overdue = po.order_status in OPEN and po.expected_delivery_date < AS_OF
        assert row["is_overdue"] == overdue
        assert row["days_overdue"] == ((AS_OF - po.expected_delivery_date).days if overdue else None)
        assert row["is_late"] == (late or overdue)


def test_list_sorts_by_lateness_with_missing_values_last_and_paginates(client) -> None:
    rows = all_rows(client, LIST, sort="days_late", order="desc")
    values = [r["days_late"] for r in rows]
    present = [v for v in values if v is not None]
    assert present and present == sorted(present, reverse=True)
    assert values == present + [None] * (len(values) - len(present))

    first = client.get(LIST, params={"sort": "days_overdue", "order": "desc", "page_size": 5}).json()
    assert first["items"][0]["days_overdue"] == max(r["days_overdue"] or 0 for r in rows)
    second = client.get(LIST, params={"page": 2, "page_size": 5}).json()
    assert second["page"] == 2 and len(second["items"]) == 5
    assert second["total_pages"] == -(-second["total"] // 5)
    ids = [r["purchase_order_id"] for r in all_rows(client, LIST, sort="order_date", order="desc")]
    assert len(ids) == len(set(ids))

    late = all_rows(client, LIST, delivered_late="true")
    assert late and all(r["order_status"] == "DELIVERED" and r["days_late"] >= 1 for r in late)
    not_late = client.get(LIST, params={"delivered_late": "false", "page_size": 1}).json()["total"]
    assert not_late + len(late) == len(rows)
    dairy = all_rows(client, LIST, category="Dairy")
    assert dairy and {r["category"] for r in dairy} == {"Dairy"}


def test_existing_list_parameters_behave_as_before(client, dataset) -> None:
    product = dataset.products[1]
    found = all_rows(client, LIST, search=product.product_name.lower())
    assert found and all(r["product_name"] == product.product_name for r in found)
    assert {r["purchase_order_id"] for r in all_rows(client, LIST, search=found[0]["purchase_order_id"].lower())} == {found[0]["purchase_order_id"]}
    both = all_rows(client, LIST, status=["DELIVERED", "CANCELLED"])
    assert {r["order_status"] for r in both} <= {"DELIVERED", "CANCELLED"}
    newest = client.get(LIST).json()["items"]
    assert [r["order_date"] for r in newest] == sorted((r["order_date"] for r in newest), reverse=True)


def test_invalid_queries_are_rejected(client) -> None:
    bad = [
        ({"days": 7, "date_from": "2026-01-05"}, "days"),
        ({"date_from": "2026-02-10", "date_to": "2026-02-01"}, "date_from"),
        ({"store_id": "STR-999"}, "store_id"),
        ({"category": "Toys"}, "category"),
        ({"supplier_id": "SUP-9999"}, "supplier_id"),
        ({"product_id": "PRD-99999"}, "product_id"),
        ({"days": 0}, "days"),
    ]
    for params, field in bad:
        for path in (SUMMARY, LIST):
            response = client.get(path, params=params)
            assert response.status_code == 422, (path, params)
            assert response.json()["detail"][0]["loc"][-1] == field
    for params in ({"status": "LOST"}, {"sort": "supplier"}, {"delivered_late": "maybe"}, {"page_size": 101}):
        assert client.get(LIST, params=params).status_code == 422, params


# --- Caching --------------------------------------------------------------------------------------


@pytest.fixture
def count_summaries(monkeypatch) -> list[OrderFilters]:
    calls: list[OrderFilters] = []
    original = po_analytics._summary

    def counting(dataset, filters):
        calls.append(filters)
        return original(dataset, filters)

    monkeypatch.setattr(po_analytics, "_summary", counting)
    return calls


def test_summary_is_cached_per_filter_set_and_recomputed_when_files_change(monkeypatch, dataset, tmp_path, count_summaries) -> None:
    write_csv(dataset, tmp_path)
    client = make_client(monkeypatch, tmp_path)

    first = client.get(SUMMARY).json()
    client.get(SUMMARY)
    client.get(LIST, params={"status": "DELIVERED", "page": 2})
    assert len(count_summaries) == 1
    client.get(SUMMARY, params={"store_id": "STR-001"})
    assert len(count_summaries) == 2

    path = tmp_path / "purchase_orders.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["quantity_ordered"] = str(int(rows[0]["quantity_ordered"]) + 9)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    second = client.get(SUMMARY).json()
    assert len(count_summaries) == 3
    assert second["totals"]["units"] == first["totals"]["units"] + 9


def test_summary_cache_invalidates_after_a_databricks_refresh(dataset, count_summaries) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), clock=clock, start=lambda fn: fn(), refresh_seconds=300)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo

    before = client.get(SUMMARY).json()
    client.get(SUMMARY)
    assert len(count_summaries) == 1 and warehouse.connects == 1

    row = list(warehouse.tables["purchase_orders"][0])
    row[7] += 11  # quantity_ordered
    warehouse.tables["purchase_orders"][0] = tuple(row)
    clock.advance(301)
    client.get(SUMMARY)
    after = client.get(SUMMARY).json()

    assert warehouse.connects == 2 and len(count_summaries) == 2
    assert after["totals"]["units"] == before["totals"]["units"] + 11


# --- Data sources and states ------------------------------------------------------------------------


def test_databricks_and_csv_modes_produce_identical_results(monkeypatch, dataset, csv_dir) -> None:
    def fetch(client: TestClient) -> tuple[dict, list[dict]]:
        summary = client.get(SUMMARY, params={"category": "Produce"}).json()
        rows = all_rows(client, LIST, category="Produce", sort="expected_delivery_date")
        return {k: v for k, v in summary.items() if k not in ("freshness", "source")}, rows

    configure(monkeypatch, "csv", csv_dir)
    csv_summary, csv_rows = fetch(TestClient(create_app()))

    warehouse = FakeWarehouse(dataset, as_strings=True)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    client = TestClient(create_app())
    response = client.get(SUMMARY)
    assert response.headers["X-Data-Source"] == "databricks" and response.json()["source"] == "databricks"
    db_summary, db_rows = fetch(client)

    assert db_summary == csv_summary
    assert db_rows == csv_rows
    assert warehouse.connects == 1


def test_initial_databricks_load_returns_503_with_retry_after(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        for path in (SUMMARY, LIST):
            loading = client.get(path)
            assert loading.status_code == 503
            assert "still loading" in loading.json()["detail"] and int(loading.headers["Retry-After"]) >= 1
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
    assert client.get(SUMMARY).json()["status"] == "ok"
    assert warehouse.connects == 1


def test_data_without_orders_returns_an_empty_status(monkeypatch, dataset, tmp_path) -> None:
    write_csv(dataclasses.replace(dataset, purchase_orders=[]), tmp_path)
    client = make_client(monkeypatch, tmp_path)
    body = client.get(SUMMARY).json()
    assert body["status"] == "empty" and "no purchase orders" in body["reason"] and body["freshness"]["source"] == "csv"
    page = client.get(LIST).json()
    assert page["items"] == [] and page["total"] == 0


def test_stale_data_and_refresh_failure_are_reported(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(
        make_settings(), connect=warehouse.connect(), clock=clock,
        now=lambda: datetime(2026, 10, 27, 9, 0, tzinfo=UTC), start=lambda fn: fn(), refresh_seconds=300,
    )
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    assert client.get(SUMMARY).json()["freshness"]["stale"] is False

    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    response = client.get(SUMMARY)
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["freshness"]["stale"] is True and body["freshness"]["last_error"]
    assert response.headers["X-Data-Refresh-Failed"] == "true"
    assert client.get(LIST).headers["X-Data-Stale"] == "true"


def test_purchase_order_schema_is_documented() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    summary = spec["paths"]["/api/v1/purchase-orders/summary"]["get"]
    schema = summary["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "status"
    listing = {p["name"] for p in spec["paths"]["/api/v1/purchase-orders"]["get"]["parameters"]}
    old = {"page", "page_size", "search", "status", "store_id", "supplier_id", "product_id", "overdue", "date_from", "date_to", "sort", "order"}
    assert old | {"category", "delivered_late", "days"} <= listing
    components = spec["components"]["schemas"]
    assert {"PurchaseOrderSummaryOk", "PurchaseOrderSummaryEmpty", "DeliverySummary", "InboundSchedule", "PurchaseOrderPage"} <= set(components)
    assert "not today's date" in components["PurchaseOrderSummaryOk"]["properties"]["as_of"]["description"]
