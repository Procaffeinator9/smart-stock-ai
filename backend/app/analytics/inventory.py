"""Inventory worklist: one position per store and product on a snapshot date.

Uses the shared rules in ``app.analytics.stock`` so the API and the overview dashboard agree.
Open purchase orders are evaluated as of the snapshot date (placed on or before it and not yet
received by then).
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.analytics.stock import (
    DEMAND_WINDOW_DAYS,
    STATUS_RANK,
    PositionStatus,
    available_units,
    days_of_cover,
    is_open_on,
    is_overdue_on,
    position_status,
)
from app.data.dataset import RetailDataset


@dataclass(frozen=True)
class OpenPurchaseOrder:
    purchase_order_id: str
    supplier_id: str
    quantity: int
    order_date: date
    expected_delivery_date: date
    status: str  # PLACED | IN_TRANSIT | OPEN (see _build_positions)
    is_overdue: bool


@dataclass(frozen=True)
class InventoryPosition:
    snapshot_date: date
    store_id: str
    product_id: str
    product_name: str
    sku: str
    category: str
    supplier_id: str
    supplier_name: str
    status: PositionStatus
    on_hand: int
    reserved: int
    available: int
    reorder_point: int
    safety_stock: int
    avg_daily_units: float
    days_of_cover: float | None
    open_po_count: int
    open_po_quantity: int
    # available + quantity on open purchase orders
    inventory_position: int
    next_delivery: date | None
    next_delivery_overdue: bool
    open_purchase_orders: tuple[OpenPurchaseOrder, ...]

    @property
    def severity_key(self) -> tuple:
        """Most urgent first: status, then fewest days of cover. Matches the overview alerts."""
        return (
            STATUS_RANK[self.status],
            self.days_of_cover if self.days_of_cover is not None else float("inf"),
            self.store_id,
            self.product_id,
        )


def inventory_positions(dataset: RetailDataset, snapshot_date: date) -> list[InventoryPosition]:
    """All positions on ``snapshot_date`` (memoised per dataset and date)."""
    cache_key = ("positions", snapshot_date)
    if cache_key not in dataset._cache:
        dataset._cache[cache_key] = _build_positions(dataset, snapshot_date)
    return dataset._cache[cache_key]


def _build_positions(dataset: RetailDataset, day: date) -> list[InventoryPosition]:
    window_start = day - timedelta(days=DEMAND_WINDOW_DAYS - 1)
    recent_units: Counter[tuple[str, str]] = Counter()
    for sale in dataset.sales:
        if window_start <= sale.sale_date <= day:
            recent_units[(sale.store_id, sale.product_id)] += sale.quantity_sold

    open_orders: dict[tuple[str, str], list[OpenPurchaseOrder]] = defaultdict(list)
    for po in dataset.purchase_orders:
        if is_open_on(po, day):
            open_orders[(po.store_id, po.product_id)].append(
                OpenPurchaseOrder(
                    purchase_order_id=po.purchase_order_id,
                    supplier_id=po.supplier_id,
                    quantity=po.quantity_ordered,
                    order_date=po.order_date,
                    expected_delivery_date=po.expected_delivery_date,
                    # For past snapshot dates an order delivered later was open, but whether it was
                    # PLACED or IN_TRANSIT on that day is unknown, so it is reported as OPEN.
                    status=po.order_status if po.actual_delivery_date is None else "OPEN",
                    is_overdue=is_overdue_on(po, day),
                )
            )

    positions = []
    for snap in dataset.inventory:
        if snap.snapshot_date != day:
            continue
        product = dataset.product_by_id[snap.product_id]
        key = (snap.store_id, snap.product_id)
        orders = tuple(sorted(open_orders.get(key, []), key=lambda o: (o.expected_delivery_date, o.purchase_order_id)))
        available = available_units(snap)
        rate = recent_units[key] / DEMAND_WINDOW_DAYS
        on_order = sum(o.quantity for o in orders)
        positions.append(
            InventoryPosition(
                snapshot_date=day,
                store_id=snap.store_id,
                product_id=product.product_id,
                product_name=product.product_name,
                sku=product.sku,
                category=product.category,
                supplier_id=product.supplier_id,
                supplier_name=dataset.supplier_by_id[product.supplier_id].supplier_name,
                status=position_status(snap),
                on_hand=snap.quantity_on_hand,
                reserved=snap.quantity_reserved,
                available=available,
                reorder_point=snap.reorder_point,
                safety_stock=snap.safety_stock,
                avg_daily_units=round(rate, 2),
                days_of_cover=days_of_cover(available, rate),
                open_po_count=len(orders),
                open_po_quantity=on_order,
                inventory_position=available + on_order,
                next_delivery=orders[0].expected_delivery_date if orders else None,
                next_delivery_overdue=bool(orders) and orders[0].is_overdue,
                open_purchase_orders=orders,
            )
        )
    return positions
