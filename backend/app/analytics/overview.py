"""Overview dashboard metrics, calculated from a generated synthetic dataset.

Every number here is derived from the dataset; nothing is invented. The result is a
JSON-serialisable dict consumed by the frontend overview page (see
``scripts/export_dashboard_snapshot.py``). Definitions:

- available        = quantity_on_hand - quantity_reserved
- out_of_stock     : available <= 0
- critical         : available <= safety_stock            (stockout risk)
- low              : available <= reorder_point           (low stock)
- healthy          : otherwise
- days_of_cover    = available / average daily units sold over the last 14 days
- Stockout-risk product: at least one store position is critical or out of stock.
- Low-stock product: not a stockout risk, and its network-wide available units are at or
  below the sum of its store reorder points.
- In the product search index, a product's status is its worst status across stores.
- Forecast "baseline": for each future day, the mean units sold on the same weekday over
  the previous four weeks; the band is the min/max of those four values. It is a simple
  seasonal average, not a trained model.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean
from typing import TYPE_CHECKING, Any

from app.analytics.stock import (
    DEMAND_WINDOW_DAYS,
    STATUS_RANK,
    days_of_cover,
    is_late,
    is_open,
    position_status,
)
from app.synthetic.generator import GeneratedDataset, InventorySnapshot

if TYPE_CHECKING:
    from app.data.dataset import RetailDataset

__all__ = ["STATUS_RANK", "build_overview", "build_overview_for", "build_overview_snapshot", "position_status"]

SCHEMA_VERSION = 1
FORECAST_HISTORY_DAYS = 28
FORECAST_HORIZON_DAYS = 14
TOP_ALERTS = 8
RECENT_PURCHASE_ORDERS = 30


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _worst(statuses: list[str]) -> str:
    return min(statuses, key=STATUS_RANK.__getitem__)


def _inventory_summary(snapshots: list[InventorySnapshot], unit_cost: dict[str, Decimal]) -> dict[str, Any]:
    """Point-in-time inventory KPIs for one snapshot date."""
    available: Counter[str] = Counter()
    reorder_point: Counter[str] = Counter()
    at_risk: set[str] = set()
    value = Decimal(0)
    units = 0
    for snap in snapshots:
        available[snap.product_id] += snap.quantity_on_hand - snap.quantity_reserved
        reorder_point[snap.product_id] += snap.reorder_point
        if position_status(snap) in ("critical", "out_of_stock"):
            at_risk.add(snap.product_id)
        value += unit_cost[snap.product_id] * snap.quantity_on_hand
        units += snap.quantity_on_hand
    low = [pid for pid in reorder_point if pid not in at_risk and available[pid] <= reorder_point[pid]]
    positions = Counter(position_status(s) for s in snapshots)
    return {
        "inventory_value": _money(value),
        "inventory_units": units,
        "low_stock_products": len(low),
        "stockout_risk_products": len(at_risk),
        "positions": {status: positions[status] for status in STATUS_RANK},
    }


def build_overview_snapshot(dataset: GeneratedDataset) -> dict[str, Any]:
    """Offline export for frontend/src/data/overview-snapshot.json (output unchanged)."""
    config = dataset.config
    return build_overview(
        dataset,
        start_date=config.start_date,
        end_date=config.end_date,
        as_of=config.end_date,
        source="synthetic",
        generator="app.synthetic.generator",
        seed=config.seed,
    )


def build_overview_for(dataset: "RetailDataset") -> dict[str, Any] | None:
    """Overview of a loaded dataset (CSV or Databricks) for the API.

    The date range comes from the data itself: start = earliest sale or snapshot date, end = latest,
    and as_of = the latest inventory snapshot. Returns None when there is nothing to summarise
    (no inventory snapshot, no sales, or no products).
    """
    if dataset.as_of is None or not dataset.sales or not dataset.products:
        return None
    dates = [s.sale_date for s in dataset.sales] + dataset.snapshot_dates
    return build_overview(
        dataset,
        start_date=min(dates),
        end_date=max(dates),
        as_of=dataset.as_of,
        source=dataset.source,
        generator=None,
        seed=None,
    )


def build_overview(
    dataset: Any,
    *,
    start_date: date,
    end_date: date,
    as_of: date,
    source: str,
    generator: str | None,
    seed: int | None,
) -> dict[str, Any]:
    """Overview metrics from any object with suppliers, products, sales, inventory, purchase_orders, stores."""
    week_before = as_of - timedelta(days=7)

    products = {p.product_id: p for p in dataset.products}
    suppliers = {s.supplier_id: s for s in dataset.suppliers}
    unit_cost = {p.product_id: p.unit_cost for p in dataset.products}
    categories = sorted({p.category for p in dataset.products})

    snapshots_by_date: dict[date, list[InventorySnapshot]] = defaultdict(list)
    for snap in dataset.inventory:
        snapshots_by_date[snap.snapshot_date].append(snap)
    latest = snapshots_by_date[as_of]

    # --- KPIs ---------------------------------------------------------------------------
    current = _inventory_summary(latest, unit_cost)
    previous = _inventory_summary(snapshots_by_date.get(week_before, []), unit_cost) if week_before >= start_date else None
    kpis = {
        "total_products": len(dataset.products),
        "categories": len(categories),
        "suppliers": len(dataset.suppliers),
        "stores": len(dataset.stores),
        "current": current,
        "week_before": previous,
    }

    # --- Daily sales (aligned arrays) -------------------------------------------------
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    index = {d: i for i, d in enumerate(dates)}
    revenue = [Decimal(0)] * len(dates)
    units = [0] * len(dates)
    category_revenue = {c: [Decimal(0)] * len(dates) for c in categories}
    demand_since = as_of - timedelta(days=DEMAND_WINDOW_DAYS - 1)
    recent_units: Counter[tuple[str, str]] = Counter()
    for sale in dataset.sales:
        i = index[sale.sale_date]
        amount = sale.unit_selling_price * sale.quantity_sold
        revenue[i] += amount
        units[i] += sale.quantity_sold
        category_revenue[products[sale.product_id].category][i] += amount
        if sale.sale_date >= demand_since:
            recent_units[(sale.store_id, sale.product_id)] += sale.quantity_sold

    inventory_by_day = [_inventory_summary(snapshots_by_date[d], unit_cost) for d in dates]
    daily = {
        "dates": [d.isoformat() for d in dates],
        "revenue": [_money(v) for v in revenue],
        "units": units,
        "category_revenue": {c: [_money(v) for v in values] for c, values in category_revenue.items()},
        # End-of-day inventory KPIs, one value per date (used for KPI sparklines).
        "inventory_value": [s["inventory_value"] for s in inventory_by_day],
        "low_stock_products": [s["low_stock_products"] for s in inventory_by_day],
        "stockout_risk_products": [s["stockout_risk_products"] for s in inventory_by_day],
    }

    # --- Open purchase orders and alerts ---------------------------------------------
    next_delivery: dict[tuple[str, str], date] = {}
    for po in dataset.purchase_orders:
        if is_open(po):
            key = (po.store_id, po.product_id)
            if key not in next_delivery or po.expected_delivery_date < next_delivery[key]:
                next_delivery[key] = po.expected_delivery_date

    positions = []
    for snap in latest:
        product = products[snap.product_id]
        key = (snap.store_id, snap.product_id)
        available = snap.quantity_on_hand - snap.quantity_reserved
        daily_rate = recent_units[key] / DEMAND_WINDOW_DAYS
        delivery = next_delivery.get(key)
        positions.append(
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "sku": product.sku,
                "category": product.category,
                "supplier_name": suppliers[product.supplier_id].supplier_name,
                "store_id": snap.store_id,
                "status": position_status(snap),
                "available": available,
                "on_hand": snap.quantity_on_hand,
                "reserved": snap.quantity_reserved,
                "reorder_point": snap.reorder_point,
                "safety_stock": snap.safety_stock,
                "avg_daily_units": round(daily_rate, 2),
                "days_of_cover": days_of_cover(available, daily_rate),
                "next_delivery": delivery.isoformat() if delivery else None,
            }
        )
    alerts = sorted(
        (p for p in positions if p["status"] != "healthy"),
        key=lambda p: (
            STATUS_RANK[p["status"]],
            p["days_of_cover"] if p["days_of_cover"] is not None else float("inf"),
            p["store_id"],
            p["product_id"],
        ),
    )[:TOP_ALERTS]

    # --- Purchase orders --------------------------------------------------------------
    def po_row(po) -> dict[str, Any]:
        return {
            "purchase_order_id": po.purchase_order_id,
            "supplier_name": suppliers[po.supplier_id].supplier_name,
            "product_name": products[po.product_id].product_name,
            "store_id": po.store_id,
            "quantity": po.quantity_ordered,
            "value": _money(po.unit_cost * po.quantity_ordered),
            "order_date": po.order_date.isoformat(),
            "expected_delivery_date": po.expected_delivery_date.isoformat(),
            "actual_delivery_date": po.actual_delivery_date.isoformat() if po.actual_delivery_date else None,
            "status": po.order_status,
            "is_late": is_late(po, as_of),
        }

    newest_first = sorted(dataset.purchase_orders, key=lambda po: (po.order_date, po.purchase_order_id), reverse=True)
    overdue = [po for po in newest_first if is_open(po) and is_late(po, as_of)]
    delivered_30d = [
        po
        for po in dataset.purchase_orders
        if po.actual_delivery_date is not None and po.actual_delivery_date > as_of - timedelta(days=30)
    ]
    purchase_orders = {
        "summary": {
            "open": sum(is_open(po) for po in dataset.purchase_orders),
            "overdue": len(overdue),
            "delivered_last_30_days": len(delivered_30d),
            "on_time_rate_last_30_days": (
                round(sum(not is_late(po, as_of) for po in delivered_30d) / len(delivered_30d), 3) if delivered_30d else None
            ),
        },
        "recent": [po_row(po) for po in newest_first[:RECENT_PURCHASE_ORDERS]],
        "overdue": [po_row(po) for po in overdue],
    }

    # --- Store health -----------------------------------------------------------------
    store_health = []
    for store in dataset.stores:
        store_snaps = [s for s in latest if s.store_id == store]
        counts = Counter(position_status(s) for s in store_snaps)
        store_health.append(
            {
                "store_id": store,
                "positions": len(store_snaps),
                **{status: counts[status] for status in STATUS_RANK},
                "inventory_value": _money(sum((unit_cost[s.product_id] * s.quantity_on_hand for s in store_snaps), Decimal(0))),
            }
        )

    # --- Baseline demand projection ---------------------------------------------------
    history_dates = dates[-FORECAST_HISTORY_DAYS:]
    units_by_date = dict(zip(dates, units))
    projection = []
    for step in range(1, FORECAST_HORIZON_DAYS + 1):
        day = as_of + timedelta(days=step)
        same_weekday = [d for d in dates if d.weekday() == day.weekday()][-4:]
        samples = [units_by_date[d] for d in same_weekday]
        if not samples:  # fewer than one week of history
            continue
        projection.append(
            {"date": day.isoformat(), "units": round(mean(samples), 1), "low": min(samples), "high": max(samples)}
        )
    forecast = {
        "method": "Same-weekday average of the last 4 weeks (baseline, not a trained model)",
        "history": [{"date": d.isoformat(), "units": units_by_date[d]} for d in history_dates],
        "projection": projection,
    }

    # --- Product index for search -----------------------------------------------------
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in positions:
        by_product[position["product_id"]].append(position)
    product_index = [
        {
            "product_id": p.product_id,
            "product_name": p.product_name,
            "sku": p.sku,
            "category": p.category,
            "supplier_name": suppliers[p.supplier_id].supplier_name,
            "selling_price": _money(p.selling_price),
            "on_hand": sum(x["on_hand"] for x in by_product[p.product_id]),
            "available": sum(x["available"] for x in by_product[p.product_id]),
            "status": _worst([x["status"] for x in by_product[p.product_id]]),
            "stores_at_risk": sum(x["status"] in ("critical", "out_of_stock") for x in by_product[p.product_id]),
        }
        for p in dataset.products
    ]

    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "source": source,
            "generator": generator,
            "seed": seed,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "as_of": as_of.isoformat(),
            "stores": list(dataset.stores),
            "categories": categories,
            "currency": "USD",
        },
        "kpis": kpis,
        "daily": daily,
        "alerts": alerts,
        "purchase_orders": purchase_orders,
        "store_health": store_health,
        "forecast": forecast,
        "products": product_index,
    }
