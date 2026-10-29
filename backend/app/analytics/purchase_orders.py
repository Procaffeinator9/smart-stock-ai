"""Purchase-order analytics for the Purchase Orders page, calculated from the loaded dataset.

"As of" is the dataset's latest inventory snapshot date (the same date the Inventory page and the
Overview use). Definitions (also shown on the page):

- order value       = quantity_ordered × unit_cost
- open              : PLACED or IN_TRANSIT
- overdue           : open, and the promised (expected) delivery date is before the as-of date
- days overdue      = as-of date − promised date (always at least 1)
- delivered late    : delivered after the promised date; days late = delivered − promised.
                      An order delivered on its promised date is on time.
- on-time rate      = delivered on or before the promised date ÷ (delivered + overdue open).
                      Overdue open orders are already late, so they count against the rate. The
                      Overview's 30-day figure counts delivered orders only and is unchanged.
- cancellation rate = cancelled ÷ all orders placed in the order-date window. The data has no
                      cancellation date or reason, so cancellations are counted by order date.
- inbound schedule  : open orders by promised date, from the as-of date through the next 13 days
                      (14 days). Earlier promised dates are overdue; later ones are "later".
- weekly orders     : orders placed per week (weeks start on Monday), by order date
- weekly delivery   : orders with a known outcome per week of their promised date: on time, late
                      (delivered after the promised date), or overdue (still open)

Every order has a single line, receipts always match the quantity ordered, and prices always
match the product's cost, so fill rate and price variance would be constant and are not reported.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.analytics.cache import memoize
from app.analytics.stock import is_late, is_open
from app.data.dataset import RetailDataset
from app.synthetic.generator import PurchaseOrder

CENT = Decimal("0.01")
ZERO = Decimal(0)
STATUSES = ("PLACED", "IN_TRANSIT", "DELIVERED", "CANCELLED")
INBOUND_DAYS = 14
TOP_OVERDUE = 10
# (label, min days overdue, max days overdue or None for no upper limit)
AGING_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("1–2 days", 1, 2),
    ("3–5 days", 3, 5),
    ("6–14 days", 6, 14),
    ("15+ days", 15, None),
)

ON_TIME_DEFINITION = (
    "Delivered on or before the promised date ÷ (delivered + overdue open orders). "
    "An order delivered on its promised date is on time."
)
DELIVERED_ONLY_DEFINITION = "Delivered on or before the promised date ÷ delivered orders (the Overview's definition)."
CANCELLATION_DEFINITION = "Cancelled ÷ all orders, by order date (the data has no cancellation date or reason)."


@dataclass(frozen=True)
class OrderFilters:
    store_id: str | None = None
    supplier_id: str | None = None
    category: str | None = None
    product_id: str | None = None
    date_from: date | None = None  # order date, inclusive
    date_to: date | None = None


# --- Per-order facts ---------------------------------------------------------------------------


def order_value(po: PurchaseOrder) -> Decimal:
    return po.unit_cost * po.quantity_ordered


def is_overdue(po: PurchaseOrder, as_of: date) -> bool:
    return is_open(po) and po.expected_delivery_date < as_of


def days_overdue(po: PurchaseOrder, as_of: date) -> int | None:
    return (as_of - po.expected_delivery_date).days if is_overdue(po, as_of) else None


def days_late(po: PurchaseOrder) -> int | None:
    """Days a delivered order arrived after its promised date; None if on time or not delivered."""
    if po.actual_delivery_date is None or po.actual_delivery_date <= po.expected_delivery_date:
        return None
    return (po.actual_delivery_date - po.expected_delivery_date).days


def delivery_outcome(po: PurchaseOrder, as_of: date) -> str | None:
    """"on_time", "late" (delivered after the promised date), or "overdue" (open and past it); None
    while the outcome is not known yet (open and not yet due) or for cancelled orders. These are
    the orders the on-time rate counts."""
    if po.actual_delivery_date is not None:
        return "late" if days_late(po) is not None else "on_time"
    return "overdue" if is_overdue(po, as_of) else None


def order_row(dataset: RetailDataset, po: PurchaseOrder) -> dict[str, Any]:
    """One order for the API: the stored fields plus names, value, and lateness as of the dataset date."""
    as_of = dataset.as_of
    product = dataset.product_by_id[po.product_id]
    return {
        "purchase_order_id": po.purchase_order_id,
        "supplier_id": po.supplier_id,
        "product_id": po.product_id,
        "store_id": po.store_id,
        "order_date": po.order_date,
        "expected_delivery_date": po.expected_delivery_date,
        "actual_delivery_date": po.actual_delivery_date,
        "quantity_ordered": po.quantity_ordered,
        "unit_cost": po.unit_cost,
        "order_status": po.order_status,
        "supplier_name": dataset.supplier_by_id[po.supplier_id].supplier_name,
        "product_name": product.product_name,
        "category": product.category,
        "value": order_value(po),
        "is_late": is_late(po, as_of) if as_of else False,
        "is_overdue": is_overdue(po, as_of) if as_of else False,
        "days_overdue": days_overdue(po, as_of) if as_of else None,
        "days_late": days_late(po),
    }


# --- Scope -------------------------------------------------------------------------------------


def orders_by_id(dataset: RetailDataset) -> list[PurchaseOrder]:
    """All orders in purchase-order ID order (a stable base order whatever the source returned)."""
    return memoize(
        dataset, "po_index", "by_id", lambda: sorted(dataset.purchase_orders, key=lambda po: po.purchase_order_id)
    )


def orders_in_scope(dataset: RetailDataset, f: OrderFilters) -> list[PurchaseOrder]:
    products = dataset.product_by_id
    return [
        po
        for po in orders_by_id(dataset)
        if (f.store_id is None or po.store_id == f.store_id)
        and (f.supplier_id is None or po.supplier_id == f.supplier_id)
        and (f.product_id is None or po.product_id == f.product_id)
        and (f.category is None or products[po.product_id].category == f.category)
        and (f.date_from is None or po.order_date >= f.date_from)
        and (f.date_to is None or po.order_date <= f.date_to)
    ]


def order_date_bounds(dataset: RetailDataset) -> tuple[date, date] | None:
    orders = dataset.purchase_orders
    return (min(po.order_date for po in orders), max(po.order_date for po in orders)) if orders else None


# --- Summary -----------------------------------------------------------------------------------


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT))


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _mean(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weeks(start: date, end: date) -> list[tuple[date, date, date]]:
    """(week start Monday, first day, last day) for each week overlapping [start, end], clamped."""
    weeks = []
    monday = _monday(start)
    while monday <= end:
        weeks.append((monday, max(monday, start), min(monday + timedelta(days=6), end)))
        monday += timedelta(days=7)
    return weeks


def _amounts(orders: list[PurchaseOrder]) -> dict[str, Any]:
    return {
        "orders": len(orders),
        "value": _money(sum((order_value(po) for po in orders), ZERO)),
        "units": sum(po.quantity_ordered for po in orders),
    }


def purchase_order_summary(dataset: RetailDataset, f: OrderFilters) -> dict[str, Any]:
    """Figures for the orders matching ``f``; cached per data snapshot and filter set.
    Requires ``dataset.as_of``."""
    return memoize(dataset, "po_summary", f, lambda: _summary(dataset, f))


def _summary(dataset: RetailDataset, f: OrderFilters) -> dict[str, Any]:
    as_of = dataset.as_of
    assert as_of is not None
    scope = orders_in_scope(dataset, f)

    by_status: dict[str, list[PurchaseOrder]] = {s: [] for s in STATUSES}
    for po in scope:
        by_status.setdefault(po.order_status, []).append(po)
    open_orders = [po for po in scope if is_open(po)]
    overdue = sorted(
        (po for po in open_orders if is_overdue(po, as_of)),
        key=lambda po: (-(as_of - po.expected_delivery_date).days, po.purchase_order_id),
    )
    overdue_days = [(as_of - po.expected_delivery_date).days for po in overdue]
    delivered = by_status["DELIVERED"]
    late_days = [d for po in delivered if (d := days_late(po)) is not None]
    on_time = len(delivered) - len(late_days)
    actual_lead = [(po.actual_delivery_date - po.order_date).days for po in delivered if po.actual_delivery_date]

    # Inbound schedule: overdue | as-of date .. +13 days | later
    inbound_end = as_of + timedelta(days=INBOUND_DAYS - 1)
    due_by_day: dict[date, list[PurchaseOrder]] = defaultdict(list)
    later = []
    for po in open_orders:
        if as_of <= po.expected_delivery_date <= inbound_end:
            due_by_day[po.expected_delivery_date].append(po)
        elif po.expected_delivery_date > inbound_end:
            later.append(po)
    inbound_days = [as_of + timedelta(days=i) for i in range(INBOUND_DAYS)]

    # Weekly orders placed (by order date), zero-filled across the window
    bounds = order_date_bounds(dataset)
    weekly_orders = []
    if bounds:
        start = f.date_from or bounds[0]
        end = f.date_to or max(bounds[1], as_of)
        placed: dict[date, list[PurchaseOrder]] = defaultdict(list)
        for po in scope:
            placed[_monday(po.order_date)].append(po)
        for monday, first, last in _weeks(start, end) if start <= end else []:
            week = placed.get(monday, [])
            weekly_orders.append(
                {
                    "week_start": monday,
                    "date_from": first,
                    "date_to": last,
                    "days": (last - first).days + 1,
                    **_amounts(week),
                    "cancelled": sum(po.order_status == "CANCELLED" for po in week),
                }
            )

    # Weekly delivery performance (by promised date), for orders with a known outcome
    outcomes: dict[date, dict[str, int]] = defaultdict(lambda: {"on_time": 0, "late": 0, "overdue": 0})
    known = [*delivered, *overdue]
    for po in known:
        if (outcome := delivery_outcome(po, as_of)) is not None:
            outcomes[_monday(po.expected_delivery_date)][outcome] += 1
    weekly_delivery = []
    if known:
        due = [po.expected_delivery_date for po in known]
        for monday, first, last in _weeks(min(due), max(due)):
            counts = outcomes.get(monday, {"on_time": 0, "late": 0, "overdue": 0})
            weekly_delivery.append(
                {
                    "week_start": monday,
                    "date_from": first,
                    "date_to": last,
                    "days": (last - first).days + 1,
                    **counts,
                    "on_time_rate": _ratio(counts["on_time"], counts["on_time"] + counts["late"] + counts["overdue"]),
                }
            )

    return {
        "totals": _amounts(scope),
        "by_status": [{"status": s, **_amounts(by_status[s])} for s in STATUSES],
        "open": _amounts(open_orders),
        "overdue": {
            **_amounts(overdue),
            "avg_days_overdue": _mean(overdue_days),
            "max_days_overdue": max(overdue_days, default=None),
            "aging": [
                {
                    "label": label,
                    "min_days": low,
                    "max_days": high,
                    **_amounts([po for po, d in zip(overdue, overdue_days) if d >= low and (high is None or d <= high)]),
                }
                for label, low, high in AGING_BUCKETS
            ],
            "top": [order_row(dataset, po) for po in overdue[:TOP_OVERDUE]],
        },
        "delivery": {
            "delivered": len(delivered),
            "on_time": on_time,
            "late": len(late_days),
            "overdue_open": len(overdue),
            "on_time_rate": _ratio(on_time, len(delivered) + len(overdue)),
            "on_time_rate_definition": ON_TIME_DEFINITION,
            "delivered_only_on_time_rate": _ratio(on_time, len(delivered)),
            "delivered_only_definition": DELIVERED_ONLY_DEFINITION,
            "avg_days_late": _mean(late_days),
            "max_days_late": max(late_days, default=None),
            "avg_promised_lead_days": _mean([(po.expected_delivery_date - po.order_date).days for po in delivered]),
            "avg_actual_lead_days": _mean(actual_lead),
        },
        "cancellation": {
            "orders": len(scope),
            "cancelled": len(by_status["CANCELLED"]),
            "rate": _ratio(len(by_status["CANCELLED"]), len(scope)),
            "definition": CANCELLATION_DEFINITION,
        },
        "inbound": {
            "date_from": as_of,
            "date_to": inbound_end,
            **_amounts([po for day in inbound_days for po in due_by_day.get(day, [])]),
            "days": [{"date": day, **_amounts(due_by_day.get(day, []))} for day in inbound_days],
            "later": _amounts(later),
        },
        "weekly_orders": weekly_orders,
        "weekly_delivery": weekly_delivery,
    }
