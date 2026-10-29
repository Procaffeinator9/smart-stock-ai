"""GET /api/v1/sales/summary and /api/v1/sales/products: agreement with independent calculations,
the existing /sales list endpoint and the Overview; windows, filters and validation; caching per data
snapshot; and the loading/empty/stale states. The Databricks warehouse is a fake; nothing connects."""

import csv
import dataclasses
import os
import threading
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.analytics.sales as sales_analytics
from app.analytics.cache import memoize
from app.data.repository import DatabricksRepository, get_repository
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from tests.test_data_api import all_rows, make_client
from tests.test_databricks_mode import configure, use_fake_warehouse, wait_until
from tests.test_databricks_repository import FakeClock, FakeWarehouse, make_settings

SMALL = GeneratorConfig(seed=11, num_suppliers=5, num_products=30, num_stores=3, num_days=60)
START, END = SMALL.start_date, SMALL.end_date
SUMMARY, PRODUCTS = "/api/v1/sales/summary", "/api/v1/sales/products"


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def csv_dir(dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("sales")
    write_csv(dataset, directory)
    return directory


@pytest.fixture
def client(monkeypatch, csv_dir) -> TestClient:
    return make_client(monkeypatch, csv_dir)


# --- Independent reference calculations (deliberately not using app.analytics) -----------------


def ref_sales(dataset, start, end, store=None, category=None, supplier=None, promotion=None):
    products = {p.product_id: p for p in dataset.products}
    return [
        s
        for s in dataset.sales
        if start <= s.sale_date <= end
        and (store is None or s.store_id == store)
        and (category is None or products[s.product_id].category == category)
        and (supplier is None or products[s.product_id].supplier_id == supplier)
        and (promotion is None or s.promotion_applied == promotion)
    ]


def revenue(rows) -> Decimal:
    return sum((s.unit_selling_price * s.quantity_sold for s in rows), Decimal(0))


def margin(dataset, rows) -> Decimal:
    cost = {p.product_id: p.unit_cost for p in dataset.products}
    return revenue(rows) - sum((cost[s.product_id] * s.quantity_sold for s in rows), Decimal(0))


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


# --- Windows and agreement with the existing APIs ----------------------------------------------


def test_default_window_is_the_last_30_days_with_the_previous_30_for_comparison(client) -> None:
    body = client.get(SUMMARY).json()

    assert body["status"] == "ok" and body["source"] == "csv" and body["as_of"] == END.isoformat()
    assert body["bounds"] == {"date_from": START.isoformat(), "date_to": END.isoformat(), "days": 60}
    assert body["period"] == {"date_from": (END - timedelta(days=29)).isoformat(), "date_to": END.isoformat(), "days": 30}
    assert body["previous_period"] == {"date_from": START.isoformat(), "date_to": (END - timedelta(days=30)).isoformat(), "days": 30}
    assert body["filters"] == {"store_id": None, "category": None, "supplier_id": None, "promotion": None}
    assert len(body["daily"]["dates"]) == 30 and body["daily"]["dates"][-1] == END.isoformat()
    assert body["facets"]["stores"] == ["STR-001", "STR-002", "STR-003"]
    assert len(body["facets"]["suppliers"]) == SMALL.num_suppliers


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"days": 7},
        {"date_from": "2026-01-10", "date_to": "2026-01-24"},
        {"store_id": "STR-002"},
        {"category": "Dairy"},
        {"promotion": "true"},
        {"promotion": "false", "store_id": "STR-003", "category": "Produce"},
    ],
)
def test_summary_totals_match_the_sales_list_endpoint(client, params) -> None:
    body = client.get(SUMMARY, params=params).json()
    period = body["period"]
    listed = client.get(
        "/api/v1/sales",
        params={**{k: v for k, v in params.items() if k != "days"}, "date_from": period["date_from"], "date_to": period["date_to"]},
    ).json()

    kpis = body["kpis"]["current"]
    assert kpis["revenue"] == listed["totals"]["revenue"]
    assert kpis["units"] == listed["totals"]["units"]
    assert kpis["sale_lines"] == listed["total"]
    assert sum(body["daily"]["revenue"]) == pytest.approx(kpis["revenue"])
    assert sum(body["daily"]["units"]) == kpis["units"]


def test_daily_and_category_revenue_match_the_overview(client) -> None:
    overview = client.get("/api/v1/overview").json()
    body = client.get(SUMMARY, params={"days": 21}).json()
    index = {d: i for i, d in enumerate(overview["daily"]["dates"])}
    rows = [index[d] for d in body["daily"]["dates"]]

    assert body["daily"]["revenue"] == [overview["daily"]["revenue"][i] for i in rows]
    assert body["daily"]["units"] == [overview["daily"]["units"][i] for i in rows]
    for category in body["by_category"]:
        expected = sum(overview["daily"]["category_revenue"][category["category"]][i] for i in rows)
        assert category["revenue"] == pytest.approx(expected)


def test_margin_and_promotion_metrics_match_independent_calculations(client, dataset) -> None:
    body = client.get(SUMMARY, params={"days": 60}).json()
    rows = ref_sales(dataset, START, END)
    kpis, promo = body["kpis"]["current"], body["promotion"]
    products = {p.product_id: p for p in dataset.products}
    promo_rows = [s for s in rows if s.promotion_applied]

    assert kpis["revenue"] == money(revenue(rows))
    assert kpis["gross_margin"] == money(margin(dataset, rows))
    assert kpis["margin_rate"] == round(float(margin(dataset, rows) / revenue(rows)), 4)
    assert kpis["avg_unit_price"] == money(revenue(rows) / sum(s.quantity_sold for s in rows))
    assert kpis["products_sold"] == len({s.product_id for s in rows})
    assert kpis["promo_revenue"] == money(revenue(promo_rows)) == promo["promo_revenue"]
    assert promo["revenue_share"] == round(float(revenue(promo_rows) / revenue(rows)), 4)
    assert promo["promo_lines"] == len(promo_rows) > 0

    list_value = sum((products[s.product_id].selling_price * s.quantity_sold for s in promo_rows), Decimal(0))
    assert promo["avg_discount"] == round(float(1 - revenue(promo_rows) / list_value), 4)
    assert 0.10 <= promo["avg_discount"] <= 0.25  # the generator's discount range

    promoted = {s.product_id for s in promo_rows}
    regular = [s for s in rows if s.product_id in promoted and not s.promotion_applied]
    per_promo = sum(s.quantity_sold for s in promo_rows) / len(promo_rows)
    per_regular = sum(s.quantity_sold for s in regular) / len(regular)
    assert promo["promoted_products"] == len(promoted)
    assert promo["units_per_line_promo"] == round(per_promo, 2)
    assert promo["uplift"] == round(per_promo / per_regular - 1, 4)


def test_breakdowns_add_up_and_compare_with_the_previous_period(client, dataset) -> None:
    body = client.get(SUMMARY).json()
    total = body["kpis"]["current"]["revenue"]
    prev_start, prev_end = date.fromisoformat(body["previous_period"]["date_from"]), date.fromisoformat(body["previous_period"]["date_to"])

    assert sum(c["revenue"] for c in body["by_category"]) == pytest.approx(total)
    assert sum(s["revenue"] for s in body["by_store"]) == pytest.approx(total)
    assert sum(c["share"] for c in body["by_category"]) == pytest.approx(1, abs=1e-3)
    assert [c["revenue"] for c in body["by_category"]] == sorted((c["revenue"] for c in body["by_category"]), reverse=True)

    assert body["kpis"]["previous"]["revenue"] == money(revenue(ref_sales(dataset, prev_start, prev_end)))
    for store in body["by_store"]:
        before = revenue(ref_sales(dataset, prev_start, prev_end, store=store["store_id"]))
        assert store["previous_revenue"] == money(before)
        assert store["change"] == pytest.approx(float((Decimal(str(store["revenue"])) - before) / before), abs=1e-4)


def test_supplier_filter_covers_exactly_that_suppliers_products(client, dataset) -> None:
    supplier = Counter(p.supplier_id for p in dataset.products).most_common(1)[0][0]
    body = client.get(SUMMARY, params={"supplier_id": supplier, "days": 60}).json()
    expected = ref_sales(dataset, START, END, supplier=supplier)
    supplied = [p for p in dataset.products if p.supplier_id == supplier]

    assert body["kpis"]["current"]["revenue"] == money(revenue(expected))
    assert body["kpis"]["current"]["units"] == sum(s.quantity_sold for s in expected)
    assert {c["category"] for c in body["by_category"]} == {p.category for p in supplied}
    rows = all_rows(client, PRODUCTS, supplier_id=supplier, days=60)
    assert {r["product_id"] for r in rows} == {p.product_id for p in supplied}
    assert {r["supplier_id"] for r in rows} == {supplier}


def test_stockout_days_count_out_of_stock_store_days(client, dataset) -> None:
    body = client.get(SUMMARY, params={"store_id": "STR-001", "days": 60}).json()
    out = [
        i
        for i in dataset.inventory
        if i.store_id == "STR-001" and i.quantity_on_hand - i.quantity_reserved <= 0
    ]
    assert out, "the generated data should contain stockouts"
    assert body["kpis"]["current"]["stockout_days"] == len(out)

    rows = all_rows(client, PRODUCTS, store_id="STR-001", days=60)
    per_product = Counter(i.product_id for i in out)
    assert {r["product_id"]: r["stockout_days"] for r in rows if r["stockout_days"]} == dict(per_product)
    # The promotion filter does not change stockout days.
    promo = client.get(SUMMARY, params={"store_id": "STR-001", "days": 60, "promotion": "true"}).json()
    assert promo["kpis"]["current"]["stockout_days"] == len(out)


def test_a_window_without_a_full_previous_period_has_no_comparison(client) -> None:
    body = client.get(SUMMARY, params={"days": 31}).json()
    assert body["previous_period"] is None and body["kpis"]["previous"] is None
    assert all(c["change"] is None and c["previous_revenue"] is None for c in body["by_category"])

    page = client.get(PRODUCTS, params={"days": 31, "sort": "revenue_change"}).json()
    assert page["previous_period"] is None
    assert all(r["revenue_change"] is None for r in page["items"])


def test_windows_are_clamped_to_the_data_and_invalid_queries_are_rejected(client) -> None:
    clamped = client.get(SUMMARY, params={"date_from": "2025-12-01", "date_to": "2026-12-31"}).json()
    assert clamped["period"] == {"date_from": START.isoformat(), "date_to": END.isoformat(), "days": 60}
    assert client.get(SUMMARY, params={"date_to": "2026-01-20", "days": 7}).json()["period"]["date_from"] == "2026-01-14"

    bad = [
        ({"days": 7, "date_from": "2026-01-05"}, "days"),
        ({"date_from": "2026-02-10", "date_to": "2026-02-01"}, "date_from"),
        ({"date_from": "2027-01-01"}, "date_from"),
        ({"store_id": "STR-999"}, "store_id"),
        ({"category": "Toys"}, "category"),
        ({"supplier_id": "SUP-9999"}, "supplier_id"),
        ({"days": 0}, "days"),
        ({"days": 367}, "days"),
    ]
    for params, field in bad:
        for path in (SUMMARY, PRODUCTS):
            response = client.get(path, params=params)
            assert response.status_code == 422, (path, params)
            assert response.json()["detail"][0]["loc"][-1] == field
    assert "outside the sales data" in client.get(SUMMARY, params={"date_from": "2027-01-01"}).json()["detail"][0]["msg"]


def test_product_rows_cover_every_product_in_scope_and_add_up(client, dataset) -> None:
    summary = client.get(SUMMARY, params={"promotion": "true"}).json()
    rows = all_rows(client, PRODUCTS, promotion="true")

    assert len(rows) == SMALL.num_products  # including products with no promotional sales
    assert any(r["revenue"] == 0 and r["margin_rate"] is None and r["avg_unit_price"] is None for r in rows)
    assert sum(r["revenue"] for r in rows) == pytest.approx(summary["kpis"]["current"]["revenue"])
    assert sum(r["units"] for r in rows) == summary["kpis"]["current"]["units"]
    assert sum(r["revenue_share"] or 0 for r in rows) == pytest.approx(1, abs=1e-3)
    assert sum(1 for r in rows if r["units"]) == summary["kpis"]["current"]["products_sold"]


def test_product_rows_sort_paginate_and_search(client, dataset) -> None:
    rows = all_rows(client, PRODUCTS)
    revenue_desc = [r["revenue"] for r in rows]
    assert revenue_desc == sorted(revenue_desc, reverse=True)

    page = client.get(PRODUCTS, params={"page": 2, "page_size": 10, "sort": "units", "order": "asc"}).json()
    assert page["total"] == SMALL.num_products and page["total_pages"] == 3 and len(page["items"]) == 10
    assert page["period"]["days"] == 30 and page["source"] == "csv"
    units = [r["units"] for r in all_rows(client, PRODUCTS, sort="units", order="asc")]
    assert [r["units"] for r in page["items"]] == units[10:20]

    by_name = all_rows(client, PRODUCTS, sort="product_name", order="asc")
    assert [r["product_name"].lower() for r in by_name] == sorted(r["product_name"].lower() for r in by_name)

    product = dataset.products[3]
    found = client.get(PRODUCTS, params={"search": product.sku.lower()}).json()
    assert [r["product_id"] for r in found["items"]] == [product.product_id]

    expected = revenue(ref_sales(dataset, END - timedelta(days=29), END))
    row = next(r for r in rows if r["product_id"] == product.product_id)
    own = revenue([s for s in ref_sales(dataset, END - timedelta(days=29), END) if s.product_id == product.product_id])
    before = revenue([s for s in ref_sales(dataset, START, END - timedelta(days=30)) if s.product_id == product.product_id])
    assert row["revenue"] == money(own) and row["previous_revenue"] == money(before)
    assert row["revenue_share"] == round(float(own / expected), 4)


def test_sorting_by_change_puts_products_without_a_comparison_last(client) -> None:
    rows = all_rows(client, PRODUCTS, promotion="true", sort="revenue_change", order="desc")
    changes = [r["revenue_change"] for r in rows]
    present = [c for c in changes if c is not None]
    assert present == sorted(present, reverse=True)
    assert changes == present + [None] * (len(changes) - len(present))


# --- Caching -----------------------------------------------------------------------------------


@pytest.fixture
def count_windows(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []
    original = sales_analytics._window_sales

    def counting(dataset, period, filters):
        calls.append((period, filters))
        return original(dataset, period, filters)

    monkeypatch.setattr(sales_analytics, "_window_sales", counting)
    return calls


def test_results_are_cached_per_filter_set_and_recomputed_when_the_data_changes(
    monkeypatch, dataset, tmp_path, count_windows
) -> None:
    write_csv(dataset, tmp_path)
    client = make_client(monkeypatch, tmp_path)

    first = client.get(SUMMARY).json()
    assert len(count_windows) == 2  # the period and the previous period
    client.get(SUMMARY)
    client.get(PRODUCTS, params={"page": 2, "sort": "units"})
    assert len(count_windows) == 2  # same filters: served from the cache
    client.get(SUMMARY, params={"store_id": "STR-002"})
    assert len(count_windows) == 4

    sales = tmp_path / "sales.csv"
    with sales.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    last = max(range(len(rows)), key=lambda i: rows[i]["sale_date"])
    rows[last]["quantity_sold"] = str(int(rows[last]["quantity_sold"]) + 5)
    with sales.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    stat = sales.stat()
    os.utime(sales, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    second = client.get(SUMMARY).json()
    assert len(count_windows) == 6
    assert second["kpis"]["current"]["units"] == first["kpis"]["current"]["units"] + 5


def test_cache_entries_are_bounded() -> None:
    holder = dataclasses.make_dataclass("Holder", [("_cache", dict)])({})
    for key in range(10):
        memoize(holder, "ns", key, lambda key=key: key * 2, max_entries=4)
    assert list(holder._cache["ns"]) == [6, 7, 8, 9]
    calls = []
    assert memoize(holder, "ns", 9, lambda: calls.append(1)) == 18 and not calls


def test_cache_invalidates_after_a_databricks_refresh(dataset, count_windows) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), clock=clock, start=lambda fn: fn(), refresh_seconds=300)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo

    before = client.get(SUMMARY, params={"days": 60}).json()
    client.get(SUMMARY, params={"days": 60})
    assert len(count_windows) == 1 and warehouse.connects == 1

    row = list(warehouse.tables["sales"][0])
    row[4] += 7  # quantity_sold
    warehouse.tables["sales"][0] = tuple(row)
    clock.advance(301)
    client.get(SUMMARY, params={"days": 60})
    after = client.get(SUMMARY, params={"days": 60}).json()

    assert warehouse.connects == 2 and len(count_windows) == 2
    assert after["kpis"]["current"]["units"] == before["kpis"]["current"]["units"] + 7


# --- Data sources and states -------------------------------------------------------------------


def test_databricks_and_csv_modes_produce_identical_sales_analytics(monkeypatch, dataset, csv_dir) -> None:
    def fetch(client: TestClient) -> tuple[dict, list[dict]]:
        summary = client.get(SUMMARY, params={"category": "Bakery"}).json()
        products = all_rows(client, PRODUCTS, category="Bakery", sort="gross_margin")
        return {k: v for k, v in summary.items() if k not in ("freshness", "source")}, products

    configure(monkeypatch, "csv", csv_dir)
    csv_summary, csv_products = fetch(TestClient(create_app()))

    warehouse = FakeWarehouse(dataset, as_strings=True)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    client = TestClient(create_app())
    response = client.get(SUMMARY)
    assert response.headers["X-Data-Source"] == "databricks" and response.json()["source"] == "databricks"
    db_summary, db_products = fetch(client)

    assert db_summary == csv_summary
    assert db_products == csv_products
    assert warehouse.connects == 1


def test_initial_databricks_load_returns_503_with_retry_after(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        for path in (SUMMARY, PRODUCTS):
            loading = client.get(path)
            assert loading.status_code == 503
            assert "still loading" in loading.json()["detail"] and int(loading.headers["Retry-After"]) >= 1
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
    assert client.get(SUMMARY).json()["status"] == "ok"
    assert warehouse.connects == 1


def test_data_without_sales_returns_an_empty_status(monkeypatch, dataset, tmp_path) -> None:
    write_csv(dataclasses.replace(dataset, sales=[]), tmp_path)
    client = make_client(monkeypatch, tmp_path)

    summary = client.get(SUMMARY).json()
    assert summary["status"] == "empty" and summary["source"] == "csv"
    assert "no sales" in summary["reason"] and summary["freshness"]["source"] == "csv"
    page = client.get(PRODUCTS).json()
    assert page["items"] == [] and page["total"] == 0 and page["period"] is None


def test_filters_that_match_nothing_return_zeros_not_errors(monkeypatch, dataset, tmp_path) -> None:
    unsold = dataclasses.replace(dataset.products[0], product_id="PRD-99999", sku="SKU-NEW-99999", category="Garden")
    write_csv(dataclasses.replace(dataset, products=[*dataset.products, unsold]), tmp_path)
    body = make_client(monkeypatch, tmp_path).get(SUMMARY, params={"category": "Garden"}).json()

    assert body["status"] == "ok"
    kpis = body["kpis"]["current"]
    assert kpis["revenue"] == 0 and kpis["units"] == 0 and kpis["margin_rate"] is None and kpis["promo_revenue_share"] is None
    assert body["promotion"]["uplift"] is None and body["promotion"]["avg_discount"] is None
    assert body["by_category"] == [
        {"category": "Garden", "revenue": 0.0, "units": 0, "gross_margin": 0.0, "margin_rate": None, "share": 0.0,
         "previous_revenue": 0.0, "change": None}
    ]


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
    assert client.get(SUMMARY).json()["freshness"]["stale"] is False

    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    response = client.get(SUMMARY)
    body = response.json()

    assert response.status_code == 200 and body["status"] == "ok"
    assert body["freshness"]["stale"] is True and body["freshness"]["last_error"]
    assert response.headers["X-Data-Stale"] == "true" and response.headers["X-Data-Refresh-Failed"] == "true"
    assert client.get(PRODUCTS).headers["X-Data-Stale"] == "true"


def test_sales_analytics_schema_is_documented() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    summary = spec["paths"]["/api/v1/sales/summary"]["get"]
    schema = summary["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "status"
    assert {p["name"] for p in summary["parameters"]} >= {"date_from", "date_to", "days", "store_id", "category", "supplier_id", "promotion"}
    products = spec["paths"]["/api/v1/sales/products"]["get"]
    assert {p["name"] for p in products["parameters"]} >= {"search", "sort", "order", "page", "page_size", "supplier_id"}
    components = spec["components"]["schemas"]
    assert {"SalesSummaryOk", "SalesSummaryEmpty", "SalesKpiTotals", "ProductPerformancePage"} <= set(components)
    assert "standard unit cost" in components["SalesKpiTotals"]["properties"]["gross_margin"]["description"]
    assert "not today's date" in components["SalesSummaryOk"]["properties"]["as_of"]["description"]
