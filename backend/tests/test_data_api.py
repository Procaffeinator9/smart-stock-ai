"""Read-only data API over a small generated CSV dataset. Databricks is never contacted."""

import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analytics.overview import build_overview_snapshot
from app.core.config import get_settings
from app.data.repository import clear_repository_cache
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv

SMALL = GeneratorConfig(seed=5, num_suppliers=5, num_products=30, num_stores=3, num_days=30)
AS_OF = SMALL.end_date
STATUSES = ["out_of_stock", "critical", "low", "healthy"]


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def csv_dir(dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("synthetic")
    write_csv(dataset, directory)
    return directory


def make_client(monkeypatch: pytest.MonkeyPatch, data_dir: Path, source: str = "csv") -> TestClient:
    monkeypatch.setenv("SMARTSTOCK_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SMARTSTOCK_DATA_SOURCE", source)
    get_settings.cache_clear()
    clear_repository_cache()
    return TestClient(create_app())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, csv_dir: Path) -> TestClient:
    return make_client(monkeypatch, csv_dir)


def all_rows(client: TestClient, path: str, **params) -> list[dict]:
    """Walk every page of a list endpoint."""
    rows, page = [], 1
    while True:
        body = client.get(path, params={**params, "page": page, "page_size": 100}).json()
        rows += body["items"]
        if page >= body["total_pages"]:
            return rows
        page += 1


# --- Independent reference calculations (deliberately not using app.analytics) -----------------


def expected_status(snap) -> str:
    available = snap.quantity_on_hand - snap.quantity_reserved
    if available <= 0:
        return "out_of_stock"
    if available <= snap.safety_stock:
        return "critical"
    return "low" if available <= snap.reorder_point else "healthy"


def latest_snapshots(dataset, day=AS_OF):
    return {(s.store_id, s.product_id): s for s in dataset.inventory if s.snapshot_date == day}


# --- Inventory calculations ----------------------------------------------------------------------


def test_inventory_covers_every_position_with_correct_status(client, dataset) -> None:
    rows = all_rows(client, "/api/v1/inventory")
    snaps = latest_snapshots(dataset)

    assert len(rows) == SMALL.num_stores * SMALL.num_products
    for row in rows:
        snap = snaps[(row["store_id"], row["product_id"])]
        assert row["available"] == snap.quantity_on_hand - snap.quantity_reserved
        assert row["status"] == expected_status(snap)
        assert (row["reorder_point"], row["safety_stock"]) == (snap.reorder_point, snap.safety_stock)
        assert row["snapshot_date"] == AS_OF.isoformat()


def test_days_of_cover_uses_last_14_days_of_sales(client, dataset) -> None:
    window_start = AS_OF - timedelta(days=13)
    units = Counter()
    for sale in dataset.sales:
        if window_start <= sale.sale_date <= AS_OF:
            units[(sale.store_id, sale.product_id)] += sale.quantity_sold

    for row in all_rows(client, "/api/v1/inventory"):
        rate = units[(row["store_id"], row["product_id"])] / 14
        assert row["avg_daily_units"] == pytest.approx(rate, abs=0.005)
        if rate == 0:
            assert row["days_of_cover"] is None
        else:
            assert row["days_of_cover"] == pytest.approx(max(row["available"], 0) / rate, abs=0.051)


def test_open_purchase_orders_on_each_position(client, dataset) -> None:
    open_pos = [po for po in dataset.purchase_orders if po.order_status in ("PLACED", "IN_TRANSIT")]
    for row in all_rows(client, "/api/v1/inventory"):
        mine = [po for po in open_pos if (po.store_id, po.product_id) == (row["store_id"], row["product_id"])]
        assert row["open_po_count"] == len(mine)
        assert row["open_po_quantity"] == sum(po.quantity_ordered for po in mine)
        assert row["inventory_position"] == row["available"] + row["open_po_quantity"]
        assert {o["purchase_order_id"] for o in row["open_purchase_orders"]} == {po.purchase_order_id for po in mine}
        if mine:
            first = min(mine, key=lambda po: (po.expected_delivery_date, po.purchase_order_id))
            assert row["next_delivery"] == first.expected_delivery_date.isoformat()
            assert row["next_delivery_overdue"] == (first.expected_delivery_date < AS_OF)
        else:
            assert row["next_delivery"] is None and row["next_delivery_overdue"] is False


def test_default_order_matches_overview_alerts(client, dataset) -> None:
    alerts = build_overview_snapshot(dataset)["alerts"]
    rows = client.get("/api/v1/inventory", params={"page_size": len(alerts)}).json()["items"]
    assert [(r["store_id"], r["product_id"]) for r in rows] == [(a["store_id"], a["product_id"]) for a in alerts]


def test_historical_snapshot_evaluates_orders_as_of_that_day(client, dataset) -> None:
    day = AS_OF - timedelta(days=10)
    body = client.get("/api/v1/inventory", params={"snapshot_date": day.isoformat(), "page_size": 100}).json()
    assert body["as_of"] == day.isoformat()

    open_then = Counter(
        (po.store_id, po.product_id)
        for po in dataset.purchase_orders
        if po.order_status != "CANCELLED"
        and po.order_date <= day
        and (po.actual_delivery_date is None or po.actual_delivery_date > day)
    )
    for row in all_rows(client, "/api/v1/inventory", snapshot_date=day.isoformat()):
        assert row["open_po_count"] == open_then[(row["store_id"], row["product_id"])]
        assert all(o["status"] in ("PLACED", "IN_TRANSIT", "OPEN") for o in row["open_purchase_orders"])


# --- Inventory filtering, sorting, pagination ---------------------------------------------------


def test_store_category_and_status_filters(client, dataset) -> None:
    category_of = {p.product_id: p.category for p in dataset.products}
    snaps = latest_snapshots(dataset).values()
    # Pick a store/category pair that has at least one low or critical position.
    sample = next(s for s in snaps if expected_status(s) in ("low", "critical"))
    store, category = sample.store_id, category_of[sample.product_id]

    rows = all_rows(client, "/api/v1/inventory", store_id=store, category=category, status=["low", "critical"])
    expected = [
        s for s in snaps
        if s.store_id == store and category_of[s.product_id] == category and expected_status(s) in ("low", "critical")
    ]
    assert rows and len(rows) == len(expected)
    assert all(r["store_id"] == store and r["category"] == category and r["status"] in ("low", "critical") for r in rows)


def test_search_is_case_insensitive_over_name_sku_and_id(client) -> None:
    by_sku = all_rows(client, "/api/v1/inventory", search="sku-dry")
    assert by_sku and all(r["sku"].startswith("SKU-DRY") for r in by_sku)
    product = by_sku[0]
    by_id = all_rows(client, "/api/v1/inventory", search=product["product_id"].lower())
    assert {r["product_id"] for r in by_id} == {product["product_id"]}
    assert len(by_id) == SMALL.num_stores
    assert client.get("/api/v1/inventory", params={"search": "no such product"}).json()["total"] == 0


def test_summary_ignores_status_filter_but_respects_others(client) -> None:
    unfiltered = client.get("/api/v1/inventory", params={"store_id": "STR-001"}).json()
    filtered = client.get("/api/v1/inventory", params={"store_id": "STR-001", "status": "healthy"}).json()
    assert filtered["summary"] == unfiltered["summary"]
    assert sum(unfiltered["summary"].values()) == unfiltered["total"] == SMALL.num_products
    assert filtered["total"] == unfiltered["summary"]["healthy"]
    assert list(unfiltered["summary"]) == STATUSES


def test_has_open_po_filter(client) -> None:
    with_po = all_rows(client, "/api/v1/inventory", has_open_po="true")
    without = all_rows(client, "/api/v1/inventory", has_open_po="false")
    assert all(r["open_po_count"] > 0 for r in with_po)
    assert all(r["open_po_count"] == 0 for r in without)
    assert len(with_po) + len(without) == SMALL.num_stores * SMALL.num_products


@pytest.mark.parametrize("sort", ["available", "reorder_point", "safety_stock", "inventory_position", "store_id", "category"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sorting(client, sort: str, order: str) -> None:
    values = [r[sort] for r in all_rows(client, "/api/v1/inventory", sort=sort, order=order)]
    assert values == sorted(values, reverse=order == "desc")


@pytest.mark.parametrize("sort", ["days_of_cover", "next_delivery"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sorting_puts_missing_values_last(client, sort: str, order: str) -> None:
    values = [r[sort] for r in all_rows(client, "/api/v1/inventory", sort=sort, order=order)]
    present = [v for v in values if v is not None]
    assert values == present + [None] * (len(values) - len(present))
    assert present == sorted(present, reverse=order == "desc")


def test_sort_by_product_name_ignores_case(client) -> None:
    names = [r["product_name"].lower() for r in all_rows(client, "/api/v1/inventory", sort="product_name")]
    assert names == sorted(names)


def test_pages_cover_every_row_exactly_once(client) -> None:
    seen, page = [], 1
    while True:
        body = client.get("/api/v1/inventory", params={"page": page, "page_size": 7}).json()
        assert body["page"] == page and body["page_size"] == 7
        seen += [(r["store_id"], r["product_id"]) for r in body["items"]]
        if page == body["total_pages"]:
            break
        assert len(body["items"]) == 7
        page += 1
    total = SMALL.num_stores * SMALL.num_products
    assert len(seen) == len(set(seen)) == total
    assert body["total_pages"] == -(-total // 7)


def test_page_past_the_end_is_empty_not_an_error(client) -> None:
    body = client.get("/api/v1/inventory", params={"page": 999}).json()
    assert body["items"] == [] and body["total"] == SMALL.num_stores * SMALL.num_products


# --- Validation and errors ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "params", "field"),
    [
        ("/api/v1/inventory", {"page": 0}, "page"),
        ("/api/v1/inventory", {"page_size": 0}, "page_size"),
        ("/api/v1/inventory", {"page_size": 101}, "page_size"),
        ("/api/v1/inventory", {"sort": "price"}, "sort"),
        ("/api/v1/inventory", {"order": "up"}, "order"),
        ("/api/v1/inventory", {"status": "unknown"}, "status"),
        ("/api/v1/inventory", {"store_id": "STR-999"}, "store_id"),
        ("/api/v1/inventory", {"category": "Toys"}, "category"),
        ("/api/v1/inventory", {"snapshot_date": "2020-01-01"}, "snapshot_date"),
        ("/api/v1/inventory", {"snapshot_date": "not-a-date"}, "snapshot_date"),
        ("/api/v1/inventory", {"search": "x" * 101}, "search"),
        ("/api/v1/sales", {"date_from": "2026-01-10", "date_to": "2026-01-01"}, "date_from"),
        ("/api/v1/sales", {"product_id": "PRD-99999"}, "product_id"),
        ("/api/v1/purchase-orders", {"status": "LOST"}, "status"),
        ("/api/v1/products", {"supplier_id": "SUP-9999"}, "supplier_id"),
    ],
)
def test_invalid_queries_return_422_naming_the_field(client, path: str, params: dict, field: str) -> None:
    response = client.get(path, params=params)
    assert response.status_code == 422
    # List parameters report their index last, e.g. ["query", "status", 0].
    assert any(field in error["loc"] for error in response.json()["detail"])


@pytest.mark.parametrize("path", ["/api/v1/products/PRD-99999", "/api/v1/suppliers/SUP-9999"])
def test_unknown_ids_return_404(client, path: str) -> None:
    assert client.get(path).status_code == 404


def test_every_data_route_is_read_only() -> None:
    app = create_app()
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/v1"):
            assert route.methods <= {"GET", "HEAD"}, route.path


# --- Other endpoints ----------------------------------------------------------------------------


def test_products_search_sort_and_detail(client, dataset) -> None:
    rows = all_rows(client, "/api/v1/products", category="Dairy", sort="selling_price", order="desc")
    prices = [r["selling_price"] for r in rows]
    assert prices == sorted(prices, reverse=True) and all(isinstance(p, float) for p in prices)
    assert len(rows) == sum(p.category == "Dairy" for p in dataset.products)

    detail = client.get(f"/api/v1/products/{rows[0]['product_id']}").json()
    assert detail["as_of"] == AS_OF.isoformat()
    assert sorted(s["store_id"] for s in detail["stock"]) == [f"STR-00{i}" for i in range(1, SMALL.num_stores + 1)]


def test_suppliers_counts(client, dataset) -> None:
    rows = all_rows(client, "/api/v1/suppliers", sort="supplier_name")
    assert len(rows) == SMALL.num_suppliers
    assert sum(r["product_count"] for r in rows) == SMALL.num_products
    assert sum(r["open_purchase_orders"] for r in rows) == sum(
        po.order_status in ("PLACED", "IN_TRANSIT") for po in dataset.purchase_orders
    )


def test_sales_date_range_is_inclusive_and_totals_cover_all_matches(client, dataset) -> None:
    start, end = date(2026, 1, 10), date(2026, 1, 12)
    params = {"date_from": start.isoformat(), "date_to": end.isoformat(), "store_id": "STR-001", "page_size": 5}
    body = client.get("/api/v1/sales", params=params).json()
    expected = [s for s in dataset.sales if start <= s.sale_date <= end and s.store_id == "STR-001"]

    assert body["total"] == len(expected) and len(body["items"]) == 5
    assert body["totals"]["units"] == sum(s.quantity_sold for s in expected)
    assert body["totals"]["revenue"] == pytest.approx(float(sum(s.unit_selling_price * s.quantity_sold for s in expected)))
    assert {r["sale_date"] for r in all_rows(client, "/api/v1/sales", **params)} == {
        (start + timedelta(days=i)).isoformat() for i in range(3)
    }


def test_sales_promotion_filter_and_revenue_sort(client) -> None:
    rows = all_rows(client, "/api/v1/sales", promotion="true", sort="revenue", order="desc", store_id="STR-003")
    assert rows and all(r["promotion_applied"] for r in rows)
    revenue = [r["revenue"] for r in rows]
    assert revenue == sorted(revenue, reverse=True)
    assert all(r["revenue"] == pytest.approx(r["quantity_sold"] * r["unit_selling_price"]) for r in rows)


def test_purchase_order_filters(client, dataset) -> None:
    overdue = all_rows(client, "/api/v1/purchase-orders", overdue="true")
    expected = [
        po for po in dataset.purchase_orders
        if po.order_status in ("PLACED", "IN_TRANSIT") and po.expected_delivery_date < AS_OF
    ]
    assert len(overdue) == len(expected) and all(r["is_late"] for r in overdue)

    open_rows = all_rows(client, "/api/v1/purchase-orders", status=["PLACED", "IN_TRANSIT"])
    assert {r["order_status"] for r in open_rows} <= {"PLACED", "IN_TRANSIT"}
    assert all(r["value"] == pytest.approx(r["quantity_ordered"] * r["unit_cost"]) for r in open_rows)

    dated = all_rows(client, "/api/v1/purchase-orders", date_from="2026-01-05", date_to="2026-01-05")
    assert dated and {r["order_date"] for r in dated} == {"2026-01-05"}


# --- Data source behaviour ----------------------------------------------------------------------


def test_missing_csvs_return_503_but_health_still_works(monkeypatch, tmp_path: Path) -> None:
    client = make_client(monkeypatch, tmp_path / "empty")
    response = client.get("/api/v1/inventory")
    assert response.status_code == 503
    assert "missing" in response.json()["detail"]
    assert str(tmp_path) not in response.json()["detail"]  # no server paths in client errors
    assert client.get("/api/v1/health").status_code == 200


def test_invalid_csv_returns_503(monkeypatch, csv_dir: Path, tmp_path: Path) -> None:
    for path in csv_dir.glob("*.csv"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    sales = tmp_path / "sales.csv"
    lines = sales.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace(",STR-001,", ",STR-001,", 1).rsplit(",", 3)[0] + ",-5,1.00,false"
    sales.write_text("\n".join(lines) + "\n", encoding="utf-8")

    response = make_client(monkeypatch, tmp_path).get("/api/v1/products")
    assert response.status_code == 503
    assert "failed validation" in response.json()["detail"]


def test_csv_changes_are_picked_up(monkeypatch, csv_dir: Path, tmp_path: Path) -> None:
    for path in csv_dir.glob("*.csv"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    client = make_client(monkeypatch, tmp_path)
    assert client.get("/api/v1/suppliers/SUP-0001").json()["supplier_name"] != "Renamed Supplier"

    suppliers = tmp_path / "suppliers.csv"
    lines = suppliers.read_text(encoding="utf-8").splitlines()
    fields = lines[1].split(",")
    fields[1] = "Renamed Supplier"
    lines[1] = ",".join(fields)
    suppliers.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stat = suppliers.stat()
    os.utime(suppliers, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    assert client.get("/api/v1/suppliers/SUP-0001").json()["supplier_name"] == "Renamed Supplier"


def test_databricks_source_without_credentials_is_503_and_health_reports_it(monkeypatch, csv_dir: Path) -> None:
    client = make_client(monkeypatch, csv_dir, source="databricks")
    response = client.get("/api/v1/inventory")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert client.get("/api/v1/health").json()["data_source"] == "databricks"
