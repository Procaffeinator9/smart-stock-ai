"""Supplier performance: a scorecard for every supplier and a detail view for one, calculated from
the loaded dataset. Reuses the Purchase Orders definitions (``app.analytics.purchase_orders``), the
Sales calculations (``app.analytics.sales``) and the Inventory positions (``app.analytics.inventory``).
"As of" is the latest inventory snapshot date. Definitions (also shown on the Suppliers pages):

- stated reliability : the supplier table's reliability_score. A stated figure, not a measurement.
- observed on-time   : the Purchase Orders on-time rate: delivered on or before the promised date ÷
                       (delivered + overdue open orders). Sample size = that denominator.
- stated lead time   : the supplier table's lead_time_days (every promised date is the order date
                       plus this).
- observed lead time : average days from order to delivery, over delivered orders. Gap = observed − stated.
- spend              : quantity × unit cost of the supplier's orders that were not cancelled.
- revenue            : sales revenue of the products the supplier supplies (each product has exactly
                       one supplier), over every sale date in the data.
- stockout days      : store-days that ended with no available units for those products, over the
                       same dates. A correlation only: stockouts also depend on demand and reorder
                       settings, so this does not show that the supplier caused them.
- at-risk positions  : store positions of those products below safety stock or out of stock on the
                       as-of date (the Inventory page's statuses).
- recent trend       : on-time rate for orders promised in the last 30 days up to the as-of date,
                       compared with the 30 days before.

"Needs attention" flags are simple rules with the thresholds below; each flag carries its reason.
They are not a risk score or a prediction.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.analytics.cache import memoize
from app.analytics.inventory import InventoryPosition, inventory_positions
from app.analytics.purchase_orders import (
    OrderFilters,
    days_late,
    delivery_outcome,
    order_row,
    order_value,
    orders_by_id,
    purchase_order_summary,
)
from app.analytics.sales import Period, SalesFilters, sales_bounds, window_sales
from app.analytics.stock import STATUS_RANK
from app.data.dataset import RetailDataset
from app.synthetic.generator import PurchaseOrder, Supplier

CENT = Decimal("0.01")
TREND_DAYS = 30
RECENT_ORDERS = 10
MAX_OVERDUE_LISTED = 20
AT_RISK = ("out_of_stock", "critical")

# "Needs attention" thresholds
ON_TIME_TARGET = 0.75
ON_TIME_MIN_SAMPLE = 20
OVERDUE_ORDERS_MIN = 2
LEAD_SLIP_DAYS = 1.0
LEAD_SLIP_SHARE = 0.25
AT_RISK_SHARE = 0.15
TREND_DROP = 0.10
TREND_MIN_SAMPLE = 20
BELOW_STATED = 0.04
BELOW_STATED_MIN_SAMPLE = 100

LATE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("On time", 0, 0),
    ("1 day", 1, 1),
    ("2 days", 2, 2),
    ("3 days", 3, 3),
    ("4 days", 4, 4),
    ("5+ days", 5, None),
)


class _NoSales:
    """Stands in for a product's sales totals when the data has no sales."""

    revenue = Decimal(0)
    units = 0


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT))


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def data_period(dataset: RetailDataset) -> Period | None:
    """Every sale date in the data (or the inventory snapshot dates when there are no sales)."""
    bounds = sales_bounds(dataset)
    if bounds is None and dataset.snapshot_dates:
        bounds = Period(dataset.snapshot_dates[0], dataset.snapshot_dates[-1])
    return bounds


def _orders_by_supplier(dataset: RetailDataset) -> dict[str, list[PurchaseOrder]]:
    def build() -> dict[str, list[PurchaseOrder]]:
        grouped: dict[str, list[PurchaseOrder]] = defaultdict(list)
        for po in orders_by_id(dataset):
            grouped[po.supplier_id].append(po)
        return dict(grouped)

    return memoize(dataset, "supplier_index", "orders", build)


def _positions_by_supplier(dataset: RetailDataset, as_of: date) -> dict[str, list[InventoryPosition]]:
    def build() -> dict[str, list[InventoryPosition]]:
        grouped: dict[str, list[InventoryPosition]] = defaultdict(list)
        for position in inventory_positions(dataset, as_of):
            grouped[position.supplier_id].append(position)
        return dict(grouped)

    return memoize(dataset, "supplier_index", ("positions", as_of), build)


def _on_time(orders: list[PurchaseOrder], as_of: date, start: date, end: date) -> tuple[float | None, int]:
    """On-time rate and sample size for orders promised between start and end (inclusive)."""
    outcomes = Counter(
        outcome
        for po in orders
        if start <= po.expected_delivery_date <= end and (outcome := delivery_outcome(po, as_of)) is not None
    )
    sample = sum(outcomes.values())
    return _ratio(outcomes["on_time"], sample), sample


# --- Flags -------------------------------------------------------------------------------------


def attention_flags(row: dict[str, Any]) -> list[dict[str, str]]:
    """Each rule that applies, with the numbers behind it."""
    flags = []
    rate, sample = row["on_time_rate"], row["sample_size"]
    if rate is not None and sample >= ON_TIME_MIN_SAMPLE and rate < ON_TIME_TARGET:
        flags.append(
            {
                "code": "low_on_time",
                "label": "Low on-time rate",
                "reason": f"{_pct(rate)} on time over {sample} orders, below the {_pct(ON_TIME_TARGET)} target.",
            }
        )
    if row["overdue_orders"] >= OVERDUE_ORDERS_MIN:
        flags.append(
            {
                "code": "overdue_orders",
                "label": "Overdue orders",
                "reason": f"{row['overdue_orders']} open orders are past their promised date "
                f"(up to {row['max_days_overdue']} days).",
            }
        )
    gap, stated = row["lead_time_gap_days"], row["stated_lead_time_days"]
    if gap is not None and (gap >= LEAD_SLIP_DAYS or (stated > 0 and gap / stated >= LEAD_SLIP_SHARE)):
        flags.append(
            {
                "code": "lead_time_slip",
                "label": "Lead time slipping",
                "reason": f"Deliveries take {row['observed_lead_time_days']:.1f} days on average against a stated "
                f"{stated} days (+{gap:.1f} days).",
            }
        )
    positions, at_risk = row["positions"], row["at_risk_positions"]
    if positions and at_risk / positions >= AT_RISK_SHARE:
        flags.append(
            {
                "code": "at_risk_stock",
                "label": "Stock at risk",
                "reason": f"{at_risk} of {positions} store positions ({_pct(at_risk / positions)}) are below safety "
                f"stock or out of stock. This does not by itself mean the supplier caused it.",
            }
        )
    recent, previous = row["recent_on_time_rate"], row["previous_on_time_rate"]
    if (
        recent is not None
        and previous is not None
        and row["recent_sample"] >= TREND_MIN_SAMPLE
        and row["previous_sample"] >= TREND_MIN_SAMPLE
        and round(previous - recent, 4) >= TREND_DROP  # rounded so 0.85 − 0.75 counts as 10 points
    ):
        flags.append(
            {
                "code": "declining_on_time",
                "label": "On-time rate falling",
                "reason": f"{_pct(recent)} on time in the last {TREND_DAYS} days against {_pct(previous)} "
                f"in the {TREND_DAYS} days before.",
            }
        )
    gap_stated = row["reliability_gap"]
    if gap_stated is not None and sample >= BELOW_STATED_MIN_SAMPLE and round(-gap_stated, 4) >= BELOW_STATED:
        flags.append(
            {
                "code": "below_stated_reliability",
                "label": "Below stated reliability",
                "reason": f"Observed on-time {_pct(rate)} is {(-gap_stated) * 100:.1f} points below the stated "
                f"reliability of {_pct(row['stated_reliability'])}.",
            }
        )
    return flags


# --- Scorecard ---------------------------------------------------------------------------------


def _supplier_row(
    dataset: RetailDataset,
    supplier: Supplier,
    orders: list[PurchaseOrder],
    positions: list[InventoryPosition],
    sales_by_product: dict[str, Any],
    stockouts: Counter,
    total_revenue: Decimal,
) -> dict[str, Any]:
    as_of = dataset.as_of
    assert as_of is not None
    summary = purchase_order_summary(dataset, OrderFilters(supplier_id=supplier.supplier_id))
    delivery, overdue = summary["delivery"], summary["overdue"]
    stated_reliability = float(supplier.reliability_score)
    observed_lead = delivery["avg_actual_lead_days"]
    recent_start = as_of - timedelta(days=TREND_DAYS - 1)
    recent, recent_n = _on_time(orders, as_of, recent_start, as_of)
    previous, previous_n = _on_time(orders, as_of, recent_start - timedelta(days=TREND_DAYS), recent_start - timedelta(days=1))
    products = [p for p in dataset.products if p.supplier_id == supplier.supplier_id]
    revenue = sum((sales_by_product[p.product_id].revenue for p in products), Decimal(0))
    sample = delivery["delivered"] + delivery["overdue_open"]

    row = {
        "supplier_id": supplier.supplier_id,
        "supplier_name": supplier.supplier_name,
        "stated_reliability": stated_reliability,
        "stated_lead_time_days": supplier.lead_time_days,
        "minimum_order_quantity": supplier.minimum_order_quantity,
        "orders": len(orders),
        "spend": _money(sum((order_value(po) for po in orders if po.order_status != "CANCELLED"), Decimal(0))),
        "cancelled": summary["cancellation"]["cancelled"],
        "cancellation_rate": summary["cancellation"]["rate"],
        "delivered": delivery["delivered"],
        "on_time": delivery["on_time"],
        "late": delivery["late"],
        "on_time_rate": delivery["on_time_rate"],
        "sample_size": sample,
        "delivered_only_on_time_rate": delivery["delivered_only_on_time_rate"],
        "reliability_gap": round(delivery["on_time_rate"] - stated_reliability, 4) if delivery["on_time_rate"] is not None else None,
        "observed_lead_time_days": observed_lead,
        "lead_time_gap_days": round(observed_lead - supplier.lead_time_days, 2) if observed_lead is not None else None,
        "avg_days_late": delivery["avg_days_late"],
        "open_orders": summary["open"]["orders"],
        "open_value": summary["open"]["value"],
        "overdue_orders": overdue["orders"],
        "max_days_overdue": overdue["max_days_overdue"],
        "recent_on_time_rate": recent,
        "recent_sample": recent_n,
        "previous_on_time_rate": previous,
        "previous_sample": previous_n,
        "products": len(products),
        "revenue": _money(revenue),
        "revenue_share": _ratio(float(revenue), float(total_revenue)),
        "units_sold": sum(sales_by_product[p.product_id].units for p in products),
        "stockout_days": sum(stockouts[p.product_id] for p in products),
        "positions": len(positions),
        "at_risk_positions": sum(p.status in AT_RISK for p in positions),
        "low_positions": sum(p.status == "low" for p in positions),
    }
    row["flags"] = attention_flags(row)
    return row


def supplier_scorecard(dataset: RetailDataset) -> dict[str, Any]:
    """Every supplier's row plus network totals; cached per data snapshot. Requires ``dataset.as_of``."""
    return memoize(dataset, "supplier_performance", "scorecard", lambda: _scorecard(dataset))


def _scorecard(dataset: RetailDataset) -> dict[str, Any]:
    as_of = dataset.as_of
    assert as_of is not None
    period = data_period(dataset)
    window = window_sales(dataset, period, SalesFilters()) if period else None
    sales_by_product = window.by_product if window else defaultdict(lambda: _NoSales)
    stockouts = window.stockout_days if window else Counter()
    total_revenue = window.total.revenue if window else Decimal(0)
    orders = _orders_by_supplier(dataset)
    positions = _positions_by_supplier(dataset, as_of)

    rows = [
        _supplier_row(dataset, s, orders.get(s.supplier_id, []), positions.get(s.supplier_id, []), sales_by_product, stockouts, total_revenue)
        for s in sorted(dataset.suppliers, key=lambda s: s.supplier_id)
    ]
    on_time = sum(r["on_time"] for r in rows)
    sample = sum(r["sample_size"] for r in rows)
    return {
        "period": period.as_dict() if period else None,
        "network": {
            "suppliers": len(rows),
            "flagged": sum(bool(r["flags"]) for r in rows),
            "orders": sum(r["orders"] for r in rows),
            "spend": round(sum(r["spend"] for r in rows), 2),
            "on_time": on_time,
            "sample_size": sample,
            "on_time_rate": _ratio(on_time, sample),
            "overdue_orders": sum(r["overdue_orders"] for r in rows),
            "revenue": _money(total_revenue),
            "positions": sum(r["positions"] for r in rows),
            "at_risk_positions": sum(r["at_risk_positions"] for r in rows),
        },
        "suppliers": rows,
    }


# --- Detail ------------------------------------------------------------------------------------


def supplier_detail(dataset: RetailDataset, supplier_id: str) -> dict[str, Any]:
    """Scorecard row plus monthly trend, late-delivery distribution, products, and orders; cached."""
    return memoize(dataset, "supplier_performance", ("detail", supplier_id), lambda: _detail(dataset, supplier_id))


def _detail(dataset: RetailDataset, supplier_id: str) -> dict[str, Any]:
    as_of = dataset.as_of
    assert as_of is not None
    supplier = dataset.supplier_by_id[supplier_id]
    row = next(r for r in supplier_scorecard(dataset)["suppliers"] if r["supplier_id"] == supplier_id)
    orders = _orders_by_supplier(dataset).get(supplier_id, [])

    # Monthly on-time trend by month of the promised date (orders with a known outcome)
    monthly: dict[date, Counter] = defaultdict(Counter)
    for po in orders:
        if (outcome := delivery_outcome(po, as_of)) is not None:
            monthly[po.expected_delivery_date.replace(day=1)][outcome] += 1
    months = []
    if monthly:
        month, last = min(monthly), max(monthly)
        while month <= last:
            counts = monthly.get(month, Counter())
            known = counts["on_time"] + counts["late"] + counts["overdue"]
            months.append(
                {
                    "month": month,
                    "on_time": counts["on_time"],
                    "late": counts["late"],
                    "overdue": counts["overdue"],
                    "on_time_rate": _ratio(counts["on_time"], known),
                }
            )
            month = (month + timedelta(days=32)).replace(day=1)

    # Days late for delivered orders
    lateness = [days_late(po) or 0 for po in orders if po.actual_delivery_date is not None]
    distribution = [
        {"label": label, "min_days": low, "max_days": high, "orders": sum(1 for d in lateness if d >= low and (high is None or d <= high))}
        for label, low, high in LATE_BUCKETS
    ]

    # Products and their stock on the as-of date
    period = data_period(dataset)
    # Per-product figures don't depend on the supplier filter, so the scorecard's cached window is reused.
    window = window_sales(dataset, period, SalesFilters()) if period else None
    positions: dict[str, list[InventoryPosition]] = defaultdict(list)
    for position in _positions_by_supplier(dataset, as_of).get(supplier_id, []):
        positions[position.product_id].append(position)
    products = []
    for product in (p for p in dataset.products if p.supplier_id == supplier_id):
        stock = positions.get(product.product_id, [])
        statuses = Counter(p.status for p in stock)
        totals = window.by_product[product.product_id] if window else _NoSales
        products.append(
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "sku": product.sku,
                "category": product.category,
                "revenue": _money(totals.revenue),
                "units_sold": totals.units,
                "stockout_days": window.stockout_days[product.product_id] if window else 0,
                "stores": len(stock),
                "status_counts": {status: statuses[status] for status in STATUS_RANK},
                "worst_status": min(statuses, key=STATUS_RANK.__getitem__) if statuses else None,
                "at_risk_stores": sum(statuses[s] for s in AT_RISK),
                "available": sum(p.available for p in stock),
                "open_po_quantity": sum(p.open_po_quantity for p in stock),
            }
        )
    products.sort(key=lambda p: (STATUS_RANK.get(p["worst_status"], len(STATUS_RANK)), -p["revenue"], p["product_id"]))

    overdue = sorted(
        (po for po in orders if delivery_outcome(po, as_of) == "overdue"),
        key=lambda po: (po.expected_delivery_date, po.purchase_order_id),
    )
    recent = sorted(orders, key=lambda po: (po.order_date, po.purchase_order_id), reverse=True)[:RECENT_ORDERS]
    return {
        "supplier": {
            "supplier_id": supplier.supplier_id,
            "supplier_name": supplier.supplier_name,
            "contact_email": supplier.contact_email,
            "stated_lead_time_days": supplier.lead_time_days,
            "minimum_order_quantity": supplier.minimum_order_quantity,
            "stated_reliability": float(supplier.reliability_score),
        },
        "scorecard": row,
        "monthly": months,
        "late_distribution": distribution,
        "products": products,
        "overdue_orders": [order_row(dataset, po) for po in overdue[:MAX_OVERDUE_LISTED]],
        "recent_orders": [order_row(dataset, po) for po in recent],
    }
