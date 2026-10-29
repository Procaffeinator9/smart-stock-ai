"""Replenishment engine and its read-only endpoints: demand estimation and fallbacks, the order
trigger, target, quantity, MOQ, shelf life, overdue and late open orders, priorities (on hand-built
positions); reconciliation with the Inventory, Products and Suppliers APIs; filters, pagination,
caching per data snapshot, CSV/Databricks parity, and loading/empty/stale states. The Databricks
warehouse is a fake; nothing connects and nothing is written."""

import csv
import dataclasses
import os
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.analytics.replenishment as replenishment
from app.analytics.replenishment import estimate_demand, plan_for, recommendations
from app.data.dataset import RetailDataset
from app.data.repository import DatabricksRepository, get_repository
from app.main import create_app
from app.synthetic import GeneratorConfig, generate_dataset, write_csv
from app.synthetic.generator import InventorySnapshot, Product, PurchaseOrder, Sale, Supplier
from tests.test_data_api import all_rows, make_client
from tests.test_databricks_mode import configure, use_fake_warehouse, wait_until
from tests.test_databricks_repository import FakeClock, FakeWarehouse, make_settings

LIST, PLAN = "/api/v1/replenishment", "/api/v1/replenishment/plan"
AS_OF = date(2026, 3, 31)
FIRST = date(2026, 1, 1)


# --- Demand estimation ---------------------------------------------------------------------------


def days_back(*offsets: int) -> set[date]:
    return {AS_OF - timedelta(days=o) for o in offsets}


def sold_daily(units: int, days: int = 90) -> dict[date, int]:
    return {AS_OF - timedelta(days=i): units for i in range(days)}


def test_demand_uses_the_last_14_in_stock_days() -> None:
    estimate = estimate_demand(sold_daily(4), set(), AS_OF, FIRST, 20, 8, 5)
    assert (estimate.rate, estimate.basis, estimate.confidence) == (4.0, "last 14 days", "high")
    assert (estimate.window_days, estimate.in_stock_days, estimate.units, estimate.excluded_days) == (14, 14, 56, 0)


def test_days_that_start_out_of_stock_are_excluded_with_their_sales() -> None:
    sold = sold_daily(4)
    sold[AS_OF - timedelta(days=2)] = 50  # a restock day that started out of stock: excluded
    ended_out = days_back(3, 5)  # so the days after them (offsets 2 and 4) started out of stock
    estimate = estimate_demand(sold, ended_out, AS_OF, FIRST, 20, 8, 5)
    assert (estimate.in_stock_days, estimate.excluded_days, estimate.units) == (12, 2, 48)
    assert estimate.rate == 4.0


def test_rate_is_rounded_to_cents_before_use() -> None:
    sold = {AS_OF - timedelta(days=i): (1 if i % 3 == 0 else 0) for i in range(14)}  # 5 units / 14 days
    assert estimate_demand(sold, set(), AS_OF, FIRST, 20, 8, 5).rate == 0.36


def test_fewer_than_7_in_stock_days_widens_to_28_then_90_days() -> None:
    sold = sold_daily(2)
    out_recent = days_back(*range(1, 9))  # 8 of the last 14 days start out of stock
    medium = estimate_demand(sold, out_recent, AS_OF, FIRST, 20, 8, 5)
    assert (medium.basis, medium.confidence, medium.window_days, medium.in_stock_days) == ("last 28 days", "medium", 28, 20)

    out_28 = days_back(*range(1, 23))  # 22 of the last 28 start out of stock: only 6 in stock
    wide = estimate_demand(sold, out_28, AS_OF, FIRST, 20, 8, 5)
    assert (wide.basis, wide.confidence, wide.window_days, wide.in_stock_days) == ("last 90 days", "medium", 90, 68)


def test_without_enough_history_demand_comes_from_reorder_settings() -> None:
    nearly_always_out = days_back(*range(1, 90))
    estimate = estimate_demand({}, nearly_always_out, AS_OF, AS_OF - timedelta(days=89), reorder_point=26, safety_stock=8, lead_time_days=6)
    assert (estimate.basis, estimate.confidence, estimate.rate) == ("reorder settings", "low", 3.0)  # (26 − 8) ÷ 6
    assert estimate.in_stock_days is None and estimate.window_days is None


def test_a_short_history_clips_the_window_and_counts_the_first_day_as_in_stock() -> None:
    first = AS_OF - timedelta(days=9)  # only 10 days of data
    estimate = estimate_demand(sold_daily(3, 10), days_back(*range(0, 10)), AS_OF, first, 20, 8, 5)
    # every day ended out of stock, so only the first day (no earlier snapshot) counts as in stock
    assert estimate.basis == "reorder settings"
    ok = estimate_demand(sold_daily(3, 10), set(), AS_OF, first, 20, 8, 5)
    assert (ok.window_days, ok.in_stock_days, ok.rate) == (10, 10, 3.0)


# --- Recommendations on hand-built positions -------------------------------------------------------


def _supplier(sid: str, lead: int, moq: int) -> Supplier:
    return Supplier(sid, f"Supplier {sid}", f"orders@{sid.lower()}.example.com", lead, moq, Decimal("0.900"))


def _product(pid: str, sid: str, shelf: int | None = None, cost: str = "2.00") -> Product:
    return Product(pid, f"SKU-{pid}", f"Product {pid}", "Pantry", Decimal(cost), Decimal("3.00"), sid, shelf, datetime(2025, 1, 1))


@dataclasses.dataclass
class Case:
    pid: str
    on_hand: int
    rop: int = 20
    ss: int = 8
    daily: int = 4
    lead: int = 5
    moq: int = 12
    shelf: int | None = None
    open_orders: tuple[tuple[int, int], ...] = ()  # (expected offset from as-of, quantity)


CASES = [
    Case("P-ROP", on_hand=20),  # IP exactly at the reorder point: order
    Case("P-ABOVE", on_hand=21),  # one above: no order (watch)
    Case("P-MOQ", on_hand=10, rop=12, ss=4, daily=1, moq=48),  # need 16 < MOQ 48
    Case("P-NODEMAND", on_hand=5, rop=10, ss=2, daily=0),  # order needed, no recent demand
    Case("P-OVERDUE", on_hand=2, open_orders=((-2, 50),)),  # below safety, delivery overdue
    Case("P-DUETODAY", on_hand=2, open_orders=((0, 50),)),  # due on the as-of date, not received
    Case("P-INTIME", on_hand=6, daily=1, open_orders=((3, 50),)),  # below safety, delivery before run-out
    Case("P-LATE", on_hand=6, daily=1, open_orders=((9, 50),)),  # below safety, delivery after run-out
    Case("P-OUT", on_hand=0),  # out of stock, nothing on order
    Case("P-HIGH", on_hand=9, ss=4),  # order needed; runs out (2 days) before a new order (5 days)
    Case("P-SHELF", on_hand=20, shelf=3),  # order would last far longer than the shelf life
    Case("P-WATCH-EDGE", on_hand=32),  # 32 − 3 × 4 = 20 = ROP: watch
    Case("P-NOT-LISTED", on_hand=33),  # 33 − 12 = 21 > ROP: not listed
]


@pytest.fixture(scope="module")
def crafted() -> RetailDataset:
    start = AS_OF - timedelta(days=13)
    suppliers, products, sales, inventory, orders = {}, [], [], [], []
    for n, case in enumerate(CASES):
        sid = f"S-{n:02d}"
        suppliers[sid] = _supplier(sid, case.lead, case.moq)
        products.append(_product(case.pid, sid, case.shelf))
        for i in range(14):
            day = start + timedelta(days=i)
            if case.daily:
                sales.append(Sale(f"SAL-{case.pid}-{i}", day, "STR-001", case.pid, case.daily, Decimal("3.00"), False))
            on_hand = case.on_hand if day == AS_OF else 500
            inventory.append(InventorySnapshot(f"INV-{case.pid}-{i}", day, "STR-001", case.pid, on_hand, 0, case.rop, case.ss))
        for k, (offset, qty) in enumerate(case.open_orders):
            orders.append(
                PurchaseOrder(f"PO-{case.pid}-{k}", sid, case.pid, "STR-001", AS_OF - timedelta(days=10),
                              AS_OF + timedelta(days=offset), None, qty, Decimal("2.00"), "IN_TRANSIT")
            )
    return RetailDataset("csv", list(suppliers.values()), products, sales, inventory, orders)


@pytest.fixture(scope="module")
def by_product(crafted) -> dict[str, dict]:
    return {r["product_id"]: r for r in recommendations(crafted)}


def test_an_order_is_triggered_exactly_at_the_reorder_point(by_product) -> None:
    row = by_product["P-ROP"]
    assert (row["action"], row["priority"]) == ("order", "medium")
    assert row["inventory_position"] == row["reorder_point"] == 20
    assert (row["demand_per_day"], row["target_level"], row["need"], row["quantity"]) == (4.0, 76, 56, 56)  # 20 + ⌈4 × 14⌉
    assert row["order_cost"] == Decimal("112.00") and not row["raised_to_moq"]
    assert row["expected_arrival"] == AS_OF + timedelta(days=5) and row["run_out_date"] == AS_OF + timedelta(days=5)
    assert row["days_of_cover"] == 5.0 and row["days_without_stock"] == 0
    assert by_product["P-ABOVE"]["action"] == "watch" and by_product["P-ABOVE"]["quantity"] == 0


def test_the_minimum_order_quantity_raises_a_small_need(by_product) -> None:
    row = by_product["P-MOQ"]
    assert (row["need"], row["quantity"], row["raised_to_moq"]) == (16, 48, True)  # 12 + 14 − 10
    assert any("minimum order of 48 (+32 units)" in w for w in row["warnings"])
    assert any("Quantity 48 = minimum order 48" in step for step in row["explanation"])


def test_no_recent_demand_recommends_no_quantity(by_product, crafted) -> None:
    row = by_product["P-NODEMAND"]
    assert (row["action"], row["demand_per_day"], row["quantity"], row["run_out_date"]) == ("order", 0.0, 0, None)
    assert any("Review manually" in w for w in row["warnings"])
    plan = plan_for(recommendations(crafted))
    assert plan["manual_review"] == 1
    assert "P-NODEMAND" not in [i["product_id"] for s in plan["suppliers"] for i in s["items"]]


def test_overdue_and_due_today_orders_are_expedited_not_reordered(by_product) -> None:
    for pid, due in (("P-OVERDUE", AS_OF - timedelta(days=2)), ("P-DUETODAY", AS_OF)):
        row = by_product[pid]
        assert (row["action"], row["priority"], row["quantity"]) == ("expedite", "critical", 0), pid
        assert row["inventory_position"] == 52  # the open order still counts: no duplicate order
        assert row["next_delivery"] == due and row["days_without_stock"] is None
        assert any("had not arrived" in w for w in row["warnings"])
        assert "has not arrived" in row["priority_reason"]
    assert by_product["P-OVERDUE"]["next_delivery_overdue"] is True
    assert by_product["P-DUETODAY"]["next_delivery_overdue"] is False  # the Purchase Orders definition is unchanged


def test_an_open_order_arriving_in_time_is_not_listed_but_a_late_one_is_expedited(by_product) -> None:
    assert "P-INTIME" not in by_product  # below safety stock, but stock arrives before the run-out
    late = by_product["P-LATE"]
    assert (late["action"], late["priority"]) == ("expedite", "critical")
    assert late["run_out_date"] == AS_OF + timedelta(days=6) and late["next_delivery"] == AS_OF + timedelta(days=9)
    assert late["days_without_stock"] == 3
    assert any("Projected days without stock (estimate): 3" in step for step in late["explanation"])


def test_priority_rules_and_reasons(by_product) -> None:
    out = by_product["P-OUT"]
    assert (out["action"], out["priority"]) == ("order", "critical") and out["priority_reason"].startswith("Out of stock now")
    high = by_product["P-HIGH"]
    assert (high["action"], high["priority"]) == ("order", "high")  # runs out Apr 2, a new order arrives Apr 5
    assert "before a new order could arrive" in high["priority_reason"]
    assert by_product["P-ROP"]["priority_reason"].startswith("Stock plus open orders (20) is at or below the reorder point")
    assert by_product["P-WATCH-EDGE"]["priority"] == "low" and "within 3 days" in by_product["P-WATCH-EDGE"]["priority_reason"]
    assert all(r["priority_reason"] and r["action_reason"] for r in by_product.values())


def test_the_watch_horizon_boundary(by_product) -> None:
    assert by_product["P-WATCH-EDGE"]["action"] == "watch"
    assert "P-NOT-LISTED" not in by_product


def test_shelf_life_conflicts_are_flagged_not_capped(by_product, crafted) -> None:
    row = by_product["P-SHELF"]
    assert row["quantity"] == by_product["P-ROP"]["quantity"] == 56  # same inputs, not capped
    assert row["exceeds_shelf_life"] is True and row["stock_days_after_order"] == 19.0  # (20 + 56) ÷ 4
    assert any(w.startswith("Shelf-life conflict") and "not capped" in w for w in row["warnings"])
    assert by_product["P-ROP"]["exceeds_shelf_life"] is False  # no shelf life
    assert plan_for(recommendations(crafted))["shelf_life_warnings"] == 1


def test_explanations_reproduce_the_numbers(by_product) -> None:
    steps = by_product["P-ROP"]["explanation"]
    assert steps[0].startswith("Estimated demand 4.00/day = 56 units ÷ 14 in-stock days (last 14 days)")
    assert "Inventory position 20 = available 20 + on order 0." in steps
    assert "20 ≤ reorder point 20: an order is needed." in steps
    assert "Target 76 = reorder point 20 + ⌈4.00 × 14⌉ (56)." in steps
    assert "Need 56 = target 76 − inventory position 20." in steps
    assert "Estimated cost $112.00 = 56 × $2.00." in steps


def test_the_plan_groups_order_lines_by_supplier_and_adds_up(crafted) -> None:
    rows = recommendations(crafted)
    plan = plan_for(rows)
    lines = [r for r in rows if r["action"] == "order" and r["quantity"] > 0]
    assert plan["lines"] == len(lines) == sum(s["lines"] for s in plan["suppliers"])
    assert plan["units"] == sum(r["quantity"] for r in lines) == sum(s["units"] for s in plan["suppliers"])
    assert plan["cost"] == sum((r["order_cost"] for r in lines), Decimal(0)) == sum((s["cost"] for s in plan["suppliers"]), Decimal(0))
    assert plan["raised_to_moq"] == 1
    for group in plan["suppliers"]:
        assert all(i["supplier_id"] == group["supplier_id"] and i["action"] == "order" for i in group["items"])


# --- API on generated data ------------------------------------------------------------------------

SMALL = GeneratorConfig(seed=25, num_suppliers=5, num_products=30, num_stores=3, num_days=60)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def csv_dir(dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("replenishment")
    write_csv(dataset, directory)
    return directory


@pytest.fixture
def client(monkeypatch, csv_dir) -> TestClient:
    return make_client(monkeypatch, csv_dir)


def test_rows_reconcile_with_inventory_products_and_suppliers(client) -> None:
    rows = all_rows(client, LIST)
    inventory = {f"{p['store_id']}|{p['product_id']}": p for p in all_rows(client, "/api/v1/inventory")}
    products = {p["product_id"]: p for p in all_rows(client, "/api/v1/products")}
    suppliers = {s["supplier_id"]: s for s in client.get("/api/v1/suppliers/performance").json()["items"]}
    assert rows
    for row in rows:
        stock = inventory[row["position_id"]]
        for field in ("available", "reorder_point", "safety_stock", "inventory_position", "open_po_count", "next_delivery"):
            assert row[field] == stock[field], (row["position_id"], field)
        assert row["on_order"] == stock["open_po_quantity"] and row["stock_status"] == stock["status"]
        assert row["unit_cost"] == products[row["product_id"]]["unit_cost"]
        assert row["order_cost"] == pytest.approx(row["quantity"] * row["unit_cost"])
        ctx = suppliers[row["supplier_id"]]
        assert row["observed_lead_time_days"] == ctx["observed_lead_time_days"]
        assert row["supplier_on_time_rate"] == ctx["on_time_rate"]
        assert row["stated_lead_time_days"] == ctx["stated_lead_time_days"]
        assert row["minimum_order_quantity"] == ctx["minimum_order_quantity"]
        if row["quantity"]:
            assert row["quantity"] >= row["minimum_order_quantity"]
    needs_order = {k for k, p in inventory.items() if p["inventory_position"] <= p["reorder_point"]}
    assert {r["position_id"] for r in rows if r["action"] == "order"} == needs_order


def test_plan_totals_match_the_listed_order_lines(client) -> None:
    body = client.get(PLAN).json()
    assert body["status"] == "ok" and body["simulation"] is True and "no purchase orders are created" in body["notice"]
    orders = all_rows(client, LIST, action="order")
    lines = [r for r in orders if r["quantity"] > 0]
    plan = body["plan"]
    assert plan["lines"] == len(lines)
    assert plan["units"] == sum(r["quantity"] for r in lines)
    assert plan["cost"] == pytest.approx(sum(r["order_cost"] for r in lines))
    assert sum(s["lines"] for s in plan["suppliers"]) == plan["lines"]
    assert body["counts"]["by_action"]["order"] == len(orders)
    assert body["settings"] == {"demand_window_days": 14, "fallback_window_days": [28, 90], "min_in_stock_days": 7,
                                "review_days": 14, "watch_days": 3, "lead_time_basis": "stated"}


def test_filters_counts_sorting_and_pagination(client, dataset) -> None:
    everything = all_rows(client, LIST)
    page = client.get(LIST, params={"action": ["order", "expedite"], "page_size": 5}).json()
    assert page["counts"]["by_action"]["watch"] == sum(r["action"] == "watch" for r in everything)  # ignores its own filter
    assert page["counts"]["by_priority"]["low"] == 0  # respects the action filter (watch rows are low)
    critical = client.get(LIST, params={"priority": "critical", "page_size": 1}).json()["counts"]
    assert critical["by_action"]["watch"] == sum(r["action"] == "watch" and r["priority"] == "critical" for r in everything)
    assert critical["by_priority"] == {p: sum(r["priority"] == p for r in everything) for p in ("critical", "high", "medium", "low")}
    assert all(r["action"] in ("order", "expedite") for r in all_rows(client, LIST, action=["order", "expedite"]))
    assert page["as_of"] == SMALL.end_date.isoformat() and page["source"] == "csv"

    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    keys = [(ranks[r["priority"]], r["run_out_date"] or "9999") for r in everything]
    assert keys == sorted(keys)  # most urgent first, then earliest run-out

    store = all_rows(client, LIST, store_id="STR-002")
    assert store and {r["store_id"] for r in store} == {"STR-002"}
    plan = client.get(PLAN, params={"store_id": "STR-002"}).json()
    assert plan["counts"]["by_action"] == {a: sum(r["action"] == a for r in store) for a in ("order", "expedite", "watch")}

    costs = [r["order_cost"] for r in all_rows(client, LIST, sort="order_cost", order="desc")]
    assert costs == sorted(costs, reverse=True)
    covers = [r["days_of_cover"] for r in all_rows(client, LIST, sort="days_of_cover")]
    present = [c for c in covers if c is not None]
    assert covers == sorted(present) + [None] * (len(covers) - len(present))

    product = everything[0]
    found = client.get(LIST, params={"search": product["sku"].lower()}).json()
    assert {r["product_id"] for r in found["items"]} == {product["product_id"]}
    second = client.get(LIST, params={"page": 2, "page_size": 5}).json()
    assert [r["position_id"] for r in second["items"]] == [r["position_id"] for r in everything[5:10]]


def test_invalid_queries_are_rejected(client) -> None:
    for params, field in (({"store_id": "STR-999"}, "store_id"), ({"category": "Toys"}, "category"), ({"supplier_id": "SUP-9999"}, "supplier_id")):
        for path in (LIST, PLAN):
            response = client.get(path, params=params)
            assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == field
    for params in ({"action": "buy"}, {"priority": "urgent"}, {"sort": "risk"}, {"page_size": 101}):
        assert client.get(LIST, params=params).status_code == 422, params


def test_endpoints_are_read_only(client, dataset) -> None:
    before = client.get("/api/v1/purchase-orders/summary").json()["totals"]
    for _ in range(2):
        client.get(PLAN)
        client.get(LIST, params={"action": "order"})
    assert client.get("/api/v1/purchase-orders/summary").json()["totals"] == before
    spec = TestClient(create_app()).get("/openapi.json").json()
    for path in (LIST, PLAN):
        assert set(spec["paths"][path]) == {"get"}


# --- Caching, sources and states --------------------------------------------------------------------


@pytest.fixture
def count_builds(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = replenishment._recommendations

    def counting(dataset):
        calls.append(1)
        return original(dataset)

    monkeypatch.setattr(replenishment, "_recommendations", counting)
    return calls


def test_computed_once_per_snapshot_and_recomputed_when_files_change(monkeypatch, dataset, tmp_path, count_builds) -> None:
    write_csv(dataset, tmp_path)
    client = make_client(monkeypatch, tmp_path)
    before = client.get(PLAN).json()
    client.get(LIST, params={"store_id": "STR-001", "page": 2})
    client.get(PLAN, params={"supplier_id": dataset.suppliers[0].supplier_id})
    assert len(count_builds) == 1

    path = tmp_path / "inventory.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    last = max(r["snapshot_date"] for r in rows)
    target = next(r for r in rows if r["snapshot_date"] == last)
    target["quantity_on_hand"], target["quantity_reserved"] = "0", "0"  # out of stock on the as-of date
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    after = client.get(PLAN).json()
    assert len(count_builds) == 2
    assert after["counts"]["by_priority"]["critical"] >= before["counts"]["by_priority"]["critical"]
    position = f"{target['store_id']}|{target['product_id']}"
    row = next(r for r in all_rows(client, LIST) if r["position_id"] == position)
    assert row["available"] == 0 and row["priority"] == "critical"


def test_cache_invalidates_after_a_databricks_refresh(dataset, count_builds) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(make_settings(), connect=warehouse.connect(), clock=clock, start=lambda fn: fn(), refresh_seconds=300)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    client.get(PLAN)
    client.get(LIST)
    assert len(count_builds) == 1 and warehouse.connects == 1
    clock.advance(301)
    client.get(PLAN)
    client.get(PLAN)
    assert warehouse.connects == 2 and len(count_builds) == 2


def test_databricks_and_csv_modes_produce_identical_results(monkeypatch, dataset, csv_dir) -> None:
    def fetch(client: TestClient) -> tuple[dict, list[dict]]:
        plan = client.get(PLAN).json()
        return {k: v for k, v in plan.items() if k not in ("freshness", "source")}, all_rows(client, LIST, sort="order_cost")

    configure(monkeypatch, "csv", csv_dir)
    csv_plan, csv_rows = fetch(TestClient(create_app()))
    warehouse = FakeWarehouse(dataset, as_strings=True)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir)
    client = TestClient(create_app())
    assert client.get(PLAN).json()["source"] == "databricks"
    db_plan, db_rows = fetch(client)
    assert db_plan == csv_plan and db_rows == csv_rows
    assert warehouse.connects == 1


def test_initial_databricks_load_returns_503_with_retry_after(monkeypatch, dataset, csv_dir) -> None:
    gate = threading.Event()
    warehouse = FakeWarehouse(dataset, gate=gate)
    use_fake_warehouse(monkeypatch, warehouse)
    configure(monkeypatch, "databricks", csv_dir, SMARTSTOCK_DATA_WAIT_SECONDS="0.3")
    client = TestClient(create_app())
    try:
        for path in (LIST, PLAN):
            loading = client.get(path)
            assert loading.status_code == 503 and int(loading.headers["Retry-After"]) >= 1
            assert "still loading" in loading.json()["detail"]
    finally:
        gate.set()
    assert wait_until(lambda: client.get("/api/v1/data-source").json()["loaded_at"] is not None)
    assert client.get(PLAN).json()["status"] == "ok"


def test_without_inventory_the_plan_is_empty_and_the_list_unavailable(monkeypatch, dataset, tmp_path) -> None:
    write_csv(dataclasses.replace(dataset, inventory=[]), tmp_path)
    client = make_client(monkeypatch, tmp_path)
    plan = client.get(PLAN).json()
    assert plan["status"] == "empty" and "no inventory snapshots" in plan["reason"] and plan["freshness"]["source"] == "csv"
    listing = client.get(LIST)
    assert listing.status_code == 503 and "no inventory snapshots" in listing.json()["detail"]


def test_stale_data_and_refresh_failure_are_reported(dataset) -> None:
    clock = FakeClock()
    warehouse = FakeWarehouse(dataset)
    repo = DatabricksRepository(
        make_settings(), connect=warehouse.connect(), clock=clock,
        now=lambda: datetime(2026, 10, 27, 9, 0, tzinfo=UTC), start=lambda fn: fn(), refresh_seconds=300,
    )
    client = TestClient(create_app())
    client.app.dependency_overrides[get_repository] = lambda: repo
    assert client.get(PLAN).json()["freshness"]["stale"] is False
    clock.advance(400)
    warehouse.error = TimeoutError("timed out")
    response = client.get(PLAN)
    assert response.status_code == 200 and response.json()["status"] == "ok"
    assert response.json()["freshness"]["stale"] is True and response.headers["X-Data-Refresh-Failed"] == "true"
    assert client.get(LIST).headers["X-Data-Stale"] == "true"


def test_replenishment_schema_is_documented() -> None:
    spec = TestClient(create_app()).get("/openapi.json").json()
    plan = spec["paths"][PLAN]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert plan["discriminator"]["propertyName"] == "status"
    params = {p["name"] for p in spec["paths"][LIST]["get"]["parameters"]}
    assert {"store_id", "category", "supplier_id", "search", "action", "priority", "sort", "order", "page", "page_size"} <= params
    components = spec["components"]["schemas"]
    assert {"Recommendation", "RecommendationPage", "ReplenishmentPlanOk", "SimulatedPlan"} <= set(components)
    assert "Estimated, not measured" in components["Recommendation"]["properties"]["demand_per_day"]["description"]
