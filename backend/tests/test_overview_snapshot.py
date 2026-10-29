import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.analytics.overview import STATUS_RANK, build_overview_snapshot, position_status
from app.synthetic import GeneratorConfig, generate_dataset

SMALL = GeneratorConfig(seed=3, num_suppliers=5, num_products=24, num_stores=3, num_days=35)
FRONTEND_SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "overview-snapshot.json"


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.fixture(scope="module")
def snapshot(dataset):
    return build_overview_snapshot(dataset)


def test_snapshot_is_json_serialisable_and_labelled_synthetic(snapshot) -> None:
    assert json.loads(json.dumps(snapshot)) == snapshot
    assert snapshot["meta"]["source"] == "synthetic"
    assert snapshot["meta"]["as_of"] == SMALL.end_date.isoformat()


def test_daily_series_reconcile_with_sales(dataset, snapshot) -> None:
    daily = snapshot["daily"]
    total_revenue = sum(s.unit_selling_price * s.quantity_sold for s in dataset.sales)

    assert len(daily["dates"]) == SMALL.num_days
    assert sum(daily["units"]) == sum(s.quantity_sold for s in dataset.sales)
    assert sum(daily["revenue"]) == pytest.approx(float(total_revenue), abs=0.05)
    for i in range(SMALL.num_days):
        by_category = sum(series[i] for series in snapshot["daily"]["category_revenue"].values())
        assert by_category == pytest.approx(daily["revenue"][i], abs=0.05)


def test_inventory_kpis_match_latest_snapshot(dataset, snapshot) -> None:
    latest = [s for s in dataset.inventory if s.snapshot_date == SMALL.end_date]
    cost = {p.product_id: p.unit_cost for p in dataset.products}
    current = snapshot["kpis"]["current"]

    assert current["inventory_units"] == sum(s.quantity_on_hand for s in latest)
    assert current["inventory_value"] == pytest.approx(float(sum(cost[s.product_id] * s.quantity_on_hand for s in latest)))
    assert sum(current["positions"].values()) == SMALL.num_stores * SMALL.num_products
    at_risk = {s.product_id for s in latest if position_status(s) in ("critical", "out_of_stock")}
    assert current["stockout_risk_products"] == len(at_risk)
    assert current["low_stock_products"] + current["stockout_risk_products"] <= SMALL.num_products

    daily = snapshot["daily"]
    for key in ("inventory_value", "low_stock_products", "stockout_risk_products"):
        assert len(daily[key]) == SMALL.num_days
        assert daily[key][-1] == current[key]
    assert daily["inventory_value"][-8] == snapshot["kpis"]["week_before"]["inventory_value"]


def test_alerts_are_unhealthy_and_ordered_by_severity(snapshot) -> None:
    ranks = [STATUS_RANK[a["status"]] for a in snapshot["alerts"]]
    assert snapshot["alerts"], "expected some alerts in the sample dataset"
    assert all(a["status"] != "healthy" for a in snapshot["alerts"])
    assert ranks == sorted(ranks)


def test_store_health_counts_cover_every_position(snapshot) -> None:
    for store in snapshot["store_health"]:
        assert sum(store[status] for status in STATUS_RANK) == store["positions"] == SMALL.num_products


def test_purchase_orders_recent_and_overdue(dataset, snapshot) -> None:
    pos = snapshot["purchase_orders"]
    order_dates = [po["order_date"] for po in pos["recent"]]
    assert order_dates == sorted(order_dates, reverse=True)
    assert pos["summary"]["overdue"] == len(pos["overdue"])
    assert all(po["is_late"] and po["status"] in ("PLACED", "IN_TRANSIT") for po in pos["overdue"])
    assert pos["summary"]["open"] == sum(po.order_status in ("PLACED", "IN_TRANSIT") for po in dataset.purchase_orders)


def test_forecast_baseline_uses_same_weekday_history(snapshot) -> None:
    forecast = snapshot["forecast"]
    units_by_date = dict(zip(snapshot["daily"]["dates"], snapshot["daily"]["units"]))
    assert len(forecast["projection"]) == 14
    for point in forecast["projection"]:
        day = date.fromisoformat(point["date"])
        same_weekday = [v for d, v in units_by_date.items() if date.fromisoformat(d).weekday() == day.weekday()][-4:]
        assert point["units"] == pytest.approx(sum(same_weekday) / 4, abs=0.051)  # rounded to 1 dp
        assert point["low"] == min(same_weekday) and point["high"] == max(same_weekday)


def test_product_index_covers_catalogue(dataset, snapshot) -> None:
    index = {p["product_id"]: p for p in snapshot["products"]}
    assert set(index) == {p.product_id for p in dataset.products}
    statuses = Counter(p["status"] for p in index.values())
    assert sum(statuses.values()) == SMALL.num_products
    assert all(p["selling_price"] == float(Decimal(str(p["selling_price"]))) for p in index.values())


def test_frontend_snapshot_is_up_to_date() -> None:
    """The committed frontend JSON must equal what export_dashboard_snapshot.py produces."""
    if not FRONTEND_SNAPSHOT.exists():
        pytest.skip("frontend snapshot not generated")
    committed = json.loads(FRONTEND_SNAPSHOT.read_text(encoding="utf-8"))
    expected = build_overview_snapshot(generate_dataset(GeneratorConfig(seed=committed["meta"]["seed"])))
    assert committed == json.loads(json.dumps(expected)), "re-run scripts/export_dashboard_snapshot.py"
