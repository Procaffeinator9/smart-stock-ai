"""Replenishment recommendations for every store-product position on the dataset's as-of date
(the latest inventory snapshot). Read-only: nothing here creates or changes a purchase order.

Definitions (also shown on the Replenishment page):

- estimated daily demand (d): units sold ÷ in-stock days over the last 14 days. An in-stock day is
  one that did not start with zero available units (the previous day's closing available > 0).
  Days that start out of stock are excluded, sales included. The data only has end-of-day stock,
  so a day that sells out part-way still counts: the estimate is a lower bound, not measured demand.
  Fewer than 7 in-stock days: widen to 28, then 90 days. Still fewer: use the rate implied by the
  reorder settings, (reorder point − safety stock) ÷ stated lead time (low confidence).
  d is rounded to 0.01 before it is used, so explanations reproduce exactly.
- inventory position (IP) = available + units on open orders (placed or in transit, including
  overdue ones), as on the Inventory page.
- order needed: IP ≤ reorder point.
- target = reorder point + ⌈d × 14⌉ (14-day review period); need = target − IP.
- recommended quantity = max(need, supplier minimum order quantity), per store and product
  (no pack-size rounding: the data has none). No quantity when d = 0 (no recent demand).
- estimated cost = quantity × the product's unit cost.
- expected arrival if ordered on the as-of date = as-of date + the supplier's stated lead time.
- days of cover = available ÷ d; projected run-out = as-of date + ⌊days of cover⌋.
- projected days without stock (estimate) = days from the projected run-out to the next expected
  delivery (or to a new order's arrival). No lost units or revenue are estimated.
- shelf-life warning: (IP + quantity) ÷ d is longer than the product's shelf life. Not capped.

Actions: "order" (order needed), "expedite" (out of stock or below safety stock with an open order
that was due on or before the as-of date and not received by that end-of-day snapshot, or that is
expected after the projected run-out; no duplicate order is recommended),
"watch" (above the reorder point but projected to reach it within 3 days). Other positions are
not listed.

Priority (each with its reason): critical = out of stock now, or below safety stock with nothing
arriving before the projected run-out; high = below safety stock with stock arriving in time, or
an order is needed and stock runs out before a new order could arrive; medium = order needed;
low = watch.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.analytics.cache import memoize
from app.analytics.inventory import InventoryPosition, inventory_positions
from app.analytics.suppliers import supplier_scorecard
from app.data.dataset import RetailDataset

CENT = Decimal("0.01")
DEMAND_WINDOWS = (14, 28, 90)
MIN_IN_STOCK_DAYS = 7
REVIEW_DAYS = 14
WATCH_DAYS = 3
ACTIONS = ("order", "expedite", "watch")
PRIORITIES = ("critical", "high", "medium", "low")
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}

SETTINGS = {
    "demand_window_days": DEMAND_WINDOWS[0],
    "fallback_window_days": list(DEMAND_WINDOWS[1:]),
    "min_in_stock_days": MIN_IN_STOCK_DAYS,
    "review_days": REVIEW_DAYS,
    "watch_days": WATCH_DAYS,
    "lead_time_basis": "stated",
}


@dataclass(frozen=True)
class DemandEstimate:
    rate: float  # units per day, rounded to 0.01
    basis: str  # "last 14 days" | "last 28 days" | "last 90 days" | "reorder settings"
    confidence: str  # "high" | "medium" | "low"
    window_days: int | None
    in_stock_days: int | None
    units: int | None
    excluded_days: int | None  # days that started out of stock


def _short(day: date) -> str:
    return f"{day:%b} {day.day}"


def _usd(value: Decimal | float) -> str:
    return f"${float(value):,.2f}"


def _units(n: float) -> str:
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


# --- Demand ------------------------------------------------------------------------------------


def _history(dataset: RetailDataset) -> tuple[dict[tuple[str, str], dict[date, int]], dict[tuple[str, str], set[date]]]:
    """Units sold per position and day, and the days each position ended with no available units."""

    def build():
        sold: dict[tuple[str, str], dict[date, int]] = defaultdict(lambda: defaultdict(int))
        for sale in dataset.sales:
            sold[(sale.store_id, sale.product_id)][sale.sale_date] += sale.quantity_sold
        out: dict[tuple[str, str], set[date]] = defaultdict(set)
        for snap in dataset.inventory:
            if snap.quantity_on_hand - snap.quantity_reserved <= 0:
                out[(snap.store_id, snap.product_id)].add(snap.snapshot_date)
        return sold, out

    return memoize(dataset, "replenishment_index", "history", build)


def estimate_demand(
    sold: dict[date, int],
    ended_out: set[date],
    as_of: date,
    first_day: date,
    reorder_point: int,
    safety_stock: int,
    lead_time_days: int,
) -> DemandEstimate:
    """See the module docstring. ``first_day`` is the first snapshot date in the data: a day with no
    previous snapshot is treated as in stock."""
    for window, confidence in zip(DEMAND_WINDOWS, ("high", "medium", "medium")):
        start = max(as_of - timedelta(days=window - 1), first_day)
        days = [start + timedelta(days=i) for i in range((as_of - start).days + 1)]
        in_stock = [d for d in days if d == first_day or (d - timedelta(days=1)) not in ended_out]
        if len(in_stock) >= MIN_IN_STOCK_DAYS:
            units = sum(sold.get(d, 0) for d in in_stock)
            return DemandEstimate(
                rate=round(units / len(in_stock), 2),
                basis=f"last {window} days",
                confidence=confidence,
                window_days=len(days),
                in_stock_days=len(in_stock),
                units=units,
                excluded_days=len(days) - len(in_stock),
            )
    implied = max(reorder_point - safety_stock, 0) / lead_time_days if lead_time_days > 0 else 0.0
    return DemandEstimate(round(implied, 2), "reorder settings", "low", None, None, None, None)


# --- Recommendations -----------------------------------------------------------------------------


def _recommend(
    dataset: RetailDataset,
    p: InventoryPosition,
    demand: DemandEstimate,
    supplier_context: dict[str, Any],
) -> dict[str, Any] | None:
    as_of = dataset.as_of
    assert as_of is not None
    product = dataset.product_by_id[p.product_id]
    supplier = dataset.supplier_by_id[product.supplier_id]
    d = demand.rate
    ip = p.inventory_position
    on_order = p.open_po_quantity
    lead = supplier.lead_time_days
    expected_arrival = as_of + timedelta(days=lead)

    order_needed = ip <= p.reorder_point
    target = p.reorder_point + math.ceil(d * REVIEW_DAYS)
    need = max(target - ip, 0)
    quantity = max(need, supplier.minimum_order_quantity) if order_needed and d > 0 else 0
    raised = quantity > need
    cost = product.unit_cost * quantity

    cover = round(max(p.available, 0) / d, 1) if d > 0 else None
    run_out = as_of + timedelta(days=math.floor(max(p.available, 0) / d)) if d > 0 else None
    has_open = p.open_po_count > 0
    # The as-of snapshot is end of day: an open order promised on or before it and not received is
    # late for planning (its arrival date is unknown), even when it is not yet "overdue".
    not_received = has_open and p.next_delivery is not None and p.next_delivery <= as_of
    late_open = not_received or (has_open and run_out is not None and p.next_delivery is not None and p.next_delivery > run_out)
    below_safety = p.status in ("critical", "out_of_stock")

    if order_needed:
        action = "order"
    elif has_open and below_safety and late_open:
        action = "expedite"
    elif d > 0 and ip - d * WATCH_DAYS <= p.reorder_point:
        action = "watch"
    else:
        return None

    # Stock expected to arrive next: an open order promised after the as-of date, else a new order
    # placed today. None when the next open order is already due and has not arrived.
    if has_open and not not_received:
        relief: date | None = p.next_delivery
    elif action == "order" and quantity > 0 and not has_open:
        relief = expected_arrival
    else:
        relief = None
    nothing_in_time = relief is None or (run_out is not None and relief > run_out)
    shortfall = max((relief - run_out).days, 0) if relief is not None and run_out is not None else None

    if not_received and p.next_delivery is not None:
        incoming = f"the next delivery was due {_short(p.next_delivery)} and has not arrived"
    elif relief is not None and has_open:
        incoming = f"the next delivery is expected {_short(relief)}"
    elif relief is not None:
        incoming = f"a new order would arrive {_short(relief)}"
    else:
        incoming = "no delivery is expected"
    run_out_text = f"projected run-out {_short(run_out)}" if run_out else "no projected run-out (no recent demand)"

    if p.available <= 0:
        priority, priority_reason = "critical", f"Out of stock now ({_units(p.available)} available); {incoming}."
    elif p.status == "critical" and nothing_in_time:
        priority, priority_reason = (
            "critical",
            f"Below safety stock ({_units(p.available)} of {p.safety_stock}) and nothing arrives in time: {run_out_text}, {incoming}.",
        )
    elif p.status == "critical":
        priority, priority_reason = (
            "high",
            f"Below safety stock ({_units(p.available)} of {p.safety_stock}), but {incoming}, before the {run_out_text}.",
        )
    elif action == "order" and run_out is not None and run_out < expected_arrival:
        priority, priority_reason = (
            "high",
            f"Order needed, and stock is projected to run out on {_short(run_out)}, before a new order could arrive on {_short(expected_arrival)}.",
        )
    elif action == "order":
        priority, priority_reason = "medium", f"Stock plus open orders ({_units(ip)}) is at or below the reorder point ({p.reorder_point})."
    else:
        priority, priority_reason = "low", f"Projected to reach the reorder point ({p.reorder_point}) within {WATCH_DAYS} days at {d:.2f} units/day."

    shelf_life = product.shelf_life_days
    stock_days = round((ip + quantity) / d, 1) if d > 0 else None
    exceeds_shelf_life = bool(quantity and shelf_life is not None and stock_days is not None and stock_days > shelf_life)

    warnings = []
    if exceeds_shelf_life:
        warnings.append(
            f"Shelf-life conflict: after this order the stock would last about {stock_days:.1f} days, but the product's shelf life is "
            f"{shelf_life} days. The quantity is not capped; review it before ordering."
        )
    if action == "order" and d == 0:
        warnings.append("No recent demand: no quantity is recommended. Review manually.")
    if raised:
        warnings.append(f"Raised from {_units(need)} to the supplier's minimum order of {supplier.minimum_order_quantity} (+{quantity - need} units).")
    if not_received and p.next_delivery is not None:
        warnings.append(
            f"The next open order was due {_short(p.next_delivery)} and had not arrived by the {_short(as_of)} end-of-day snapshot."
        )
    if demand.confidence == "low":
        warnings.append("Too little in-stock sales history: demand comes from the reorder settings (low confidence).")

    action_reason = {
        "order": "Order now: stock plus open orders is at or below the reorder point.",
        "expedite": "Expedite: an open order exists but it is overdue or expected after the projected run-out. No duplicate order is recommended.",
        "watch": f"Watch: projected to reach the reorder point within {WATCH_DAYS} days.",
    }[action]

    ctx = supplier_context.get(supplier.supplier_id, {})
    observed = ctx.get("observed_lead_time_days")
    on_time = ctx.get("on_time_rate")
    explanation = [
        _demand_step(demand, d),
        f"Inventory position {_units(ip)} = available {_units(p.available)} + on order {_units(on_order)}.",
        (
            f"{_units(ip)} ≤ reorder point {p.reorder_point}: an order is needed."
            if order_needed
            else f"{_units(ip)} > reorder point {p.reorder_point}: no order needed yet."
        ),
    ]
    if order_needed and d > 0:
        explanation += [
            f"Target {_units(target)} = reorder point {p.reorder_point} + ⌈{d:.2f} × {REVIEW_DAYS}⌉ ({math.ceil(d * REVIEW_DAYS)}).",
            f"Need {_units(need)} = target {_units(target)} − inventory position {_units(ip)}.",
            (
                f"Quantity {quantity} = minimum order {supplier.minimum_order_quantity} (need {_units(need)} is below it)."
                if raised
                else f"Quantity {quantity} = need (at least the minimum order of {supplier.minimum_order_quantity})."
            ),
            f"Estimated cost {_usd(cost)} = {quantity} × {_usd(product.unit_cost)}.",
            f"Expected arrival {_short(expected_arrival)} if ordered on {_short(as_of)} (stated lead time {lead} days"
            + (f"; observed {observed:.1f} days, {on_time * 100:.1f}% on time" if observed is not None and on_time is not None else "")
            + ").",
        ]
    if cover is not None and run_out is not None:
        explanation.append(f"Days of cover {cover:.1f} = available {_units(max(p.available, 0))} ÷ {d:.2f}; projected run-out {_short(run_out)}.")
    if shortfall and run_out is not None and relief is not None:
        explanation.append(f"Projected days without stock (estimate): {shortfall}, from {_short(run_out)} until {_short(relief)}.")
    if exceeds_shelf_life:
        explanation.append(f"Shelf life {shelf_life} days < about {stock_days:.1f} days of stock after the order.")

    return {
        "position_id": f"{p.store_id}|{p.product_id}",
        "store_id": p.store_id,
        "product_id": p.product_id,
        "product_name": p.product_name,
        "sku": p.sku,
        "category": p.category,
        "supplier_id": supplier.supplier_id,
        "supplier_name": supplier.supplier_name,
        "action": action,
        "priority": priority,
        "priority_reason": priority_reason,
        "action_reason": action_reason,
        "warnings": warnings,
        "stock_status": p.status,
        "on_hand": p.on_hand,
        "reserved": p.reserved,
        "available": p.available,
        "safety_stock": p.safety_stock,
        "reorder_point": p.reorder_point,
        "on_order": on_order,
        "inventory_position": ip,
        "open_po_count": p.open_po_count,
        "next_delivery": p.next_delivery,
        "next_delivery_overdue": p.next_delivery_overdue,
        "demand_per_day": d,
        "demand_basis": demand.basis,
        "demand_confidence": demand.confidence,
        "demand_window_days": demand.window_days,
        "in_stock_days": demand.in_stock_days,
        "units_in_window": demand.units,
        "excluded_days": demand.excluded_days,
        "days_of_cover": cover,
        "run_out_date": run_out,
        "days_without_stock": shortfall,
        "stated_lead_time_days": lead,
        "observed_lead_time_days": observed,
        "supplier_on_time_rate": on_time,
        "minimum_order_quantity": supplier.minimum_order_quantity,
        "target_level": target,
        "need": need if order_needed else 0,
        "quantity": quantity,
        "raised_to_moq": raised,
        "unit_cost": product.unit_cost,
        "order_cost": cost,
        "expected_arrival": expected_arrival if action == "order" and quantity else None,
        "shelf_life_days": shelf_life,
        "stock_days_after_order": stock_days if quantity else None,
        "exceeds_shelf_life": exceeds_shelf_life,
        "explanation": explanation,
    }


def _demand_step(demand: DemandEstimate, d: float) -> str:
    if demand.basis == "reorder settings":
        return f"Estimated demand {d:.2f}/day from the reorder settings: (reorder point − safety stock) ÷ stated lead time (low confidence)."
    excluded = f"; {demand.excluded_days} days excluded for starting out of stock" if demand.excluded_days else ""
    return (
        f"Estimated demand {d:.2f}/day = {_units(demand.units or 0)} units ÷ {demand.in_stock_days} in-stock days "
        f"({demand.basis}{excluded}). An estimate, not measured demand."
    )


def recommendations(dataset: RetailDataset) -> list[dict[str, Any]]:
    """Every listed position (order, expedite, watch), cached per data snapshot. Requires ``dataset.as_of``."""
    return memoize(dataset, "replenishment", "all", lambda: _recommendations(dataset))


def _recommendations(dataset: RetailDataset) -> list[dict[str, Any]]:
    as_of = dataset.as_of
    assert as_of is not None
    sold, ended_out = _history(dataset)
    first_day = dataset.snapshot_dates[0]
    context = {r["supplier_id"]: r for r in supplier_scorecard(dataset)["suppliers"]}
    rows = []
    for p in inventory_positions(dataset, as_of):
        lead = dataset.supplier_by_id[p.supplier_id].lead_time_days
        key = (p.store_id, p.product_id)
        demand = estimate_demand(sold.get(key, {}), ended_out.get(key, set()), as_of, first_day, p.reorder_point, p.safety_stock, lead)
        row = _recommend(dataset, p, demand, context)
        if row is not None:
            rows.append(row)
    rows.sort(key=priority_key)
    return rows


def priority_key(row: dict[str, Any]) -> tuple:
    """Most urgent first: priority, then earliest projected run-out, then store and product."""
    return (PRIORITY_RANK[row["priority"]], row["run_out_date"] or date.max, row["store_id"], row["product_id"])


def plan_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Simulated reorder plan: every "order" line with a quantity, grouped by supplier. Nothing is ordered."""
    lines = [r for r in rows if r["action"] == "order" and r["quantity"] > 0]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        groups[line["supplier_id"]].append(line)
    suppliers = []
    for supplier_id, items in sorted(groups.items(), key=lambda kv: (kv[1][0]["supplier_name"].lower(), kv[0])):
        items.sort(key=priority_key)
        suppliers.append(
            {
                "supplier_id": supplier_id,
                "supplier_name": items[0]["supplier_name"],
                "stated_lead_time_days": items[0]["stated_lead_time_days"],
                "expected_arrival": items[0]["expected_arrival"],
                "lines": len(items),
                "units": sum(i["quantity"] for i in items),
                "cost": sum((i["order_cost"] for i in items), Decimal(0)),
                "raised_to_moq": sum(i["raised_to_moq"] for i in items),
                "shelf_life_warnings": sum(i["exceeds_shelf_life"] for i in items),
                "items": items,
            }
        )
    return {
        "lines": len(lines),
        "units": sum(line["quantity"] for line in lines),
        "cost": sum((line["order_cost"] for line in lines), Decimal(0)),
        "raised_to_moq": sum(line["raised_to_moq"] for line in lines),
        "shelf_life_warnings": sum(line["exceeds_shelf_life"] for line in lines),
        "manual_review": sum(1 for r in rows if r["action"] == "order" and r["quantity"] == 0),
        "suppliers": suppliers,
    }
