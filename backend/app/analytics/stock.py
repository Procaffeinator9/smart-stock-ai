"""Stock-position rules shared by the overview dashboard and the inventory API.

- available        = quantity_on_hand - quantity_reserved
- out_of_stock     : available <= 0
- critical         : available <= safety_stock            (stockout risk)
- low              : available <= reorder_point           (low stock)
- healthy          : otherwise
- days_of_cover    = available / average daily units sold over the last 14 days
- An open purchase order (PLACED or IN_TRANSIT) is late when its expected delivery date is
  before the as-of date; a delivered one is late when it arrived after the expected date.
"""

from datetime import date
from typing import Literal

from app.synthetic.generator import InventorySnapshot, PurchaseOrder

PositionStatus = Literal["out_of_stock", "critical", "low", "healthy"]

DEMAND_WINDOW_DAYS = 14
STATUS_RANK: dict[str, int] = {"out_of_stock": 0, "critical": 1, "low": 2, "healthy": 3}
OPEN_PO_STATUSES = frozenset({"PLACED", "IN_TRANSIT"})


def available_units(snapshot: InventorySnapshot) -> int:
    return snapshot.quantity_on_hand - snapshot.quantity_reserved


def position_status(snapshot: InventorySnapshot) -> PositionStatus:
    available = available_units(snapshot)
    if available <= 0:
        return "out_of_stock"
    if available <= snapshot.safety_stock:
        return "critical"
    if available <= snapshot.reorder_point:
        return "low"
    return "healthy"


def days_of_cover(available: int, avg_daily_units: float) -> float | None:
    """Days the available units last at the recent sales rate; None when nothing sold recently."""
    return round(max(available, 0) / avg_daily_units, 1) if avg_daily_units > 0 else None


def is_open(po: PurchaseOrder) -> bool:
    return po.order_status in OPEN_PO_STATUSES


def is_late(po: PurchaseOrder, as_of: date) -> bool:
    if po.actual_delivery_date is not None:
        return po.actual_delivery_date > po.expected_delivery_date
    return is_open(po) and po.expected_delivery_date < as_of


def is_open_on(po: PurchaseOrder, day: date) -> bool:
    """Placed on or before ``day``, not cancelled, and not yet received by the end of ``day``.

    At the dataset's last date this matches ``is_open``. The data has no cancellation date,
    so cancelled orders are treated as never open.
    """
    if po.order_status == "CANCELLED" or po.order_date > day:
        return False
    return po.actual_delivery_date is None or po.actual_delivery_date > day


def is_overdue_on(po: PurchaseOrder, day: date) -> bool:
    """Open on ``day`` and its expected delivery date has already passed."""
    return is_open_on(po, day) and po.expected_delivery_date < day
