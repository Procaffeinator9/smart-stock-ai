from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.analytics.purchase_orders import (
    OrderFilters,
    days_late,
    days_overdue,
    order_date_bounds,
    order_row,
    order_value,
    orders_in_scope,
    purchase_order_summary,
)
from app.analytics.stock import is_late, is_open
from app.api.v1.common import (
    PageParams,
    SearchQuery,
    SortOrder,
    contains,
    invalid_query,
    page_params,
    paginate,
    require_choice,
    require_date_order,
    require_known,
    sort_items,
)
from app.api.v1.purchase_order_schemas import PurchaseOrderSummaryResponse
from app.api.v1.schemas import PurchaseOrderPage, PurchaseOrderStatus
from app.data.dataset import RetailDataset
from app.data.repository import Repository, get_dataset, get_repository
from app.synthetic.generator import PurchaseOrder

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])

PurchaseOrderSort = Literal[
    "order_date",
    "expected_delivery_date",
    "quantity_ordered",
    "value",
    "purchase_order_id",
    "actual_delivery_date",
    "days_overdue",
    "days_late",
]
MAX_WINDOW_DAYS = 366


def po_out(dataset: RetailDataset, po: PurchaseOrder) -> dict[str, Any]:
    return order_row(dataset, po)


def order_filters(
    dataset: RetailDataset = Depends(get_dataset),
    store_id: str | None = None,
    supplier_id: str | None = None,
    category: str | None = None,
    product_id: str | None = None,
    date_from: Annotated[date | None, Query(description="Order date on or after")] = None,
    date_to: Annotated[date | None, Query(description="Order date on or before")] = None,
    days: Annotated[
        int | None,
        Query(ge=1, le=MAX_WINDOW_DAYS, description="Orders placed in the last N days up to date_to (default: the dataset's as-of date)"),
    ] = None,
) -> OrderFilters:
    """Validated scope filters shared by the order list and the summary."""
    if days is not None and date_from is not None:
        raise invalid_query("days", "Use either days or date_from, not both")
    require_date_order(date_from, date_to)
    require_choice("store_id", store_id, dataset.stores)
    require_known("supplier_id", supplier_id, dataset.supplier_by_id)
    require_choice("category", category, dataset.categories)
    require_known("product_id", product_id, dataset.product_by_id)
    if days is not None:
        bounds = order_date_bounds(dataset)
        end = date_to or dataset.as_of or (bounds[1] if bounds else None)
        if end is not None:
            date_from, date_to = end - timedelta(days=days - 1), end
    return OrderFilters(store_id, supplier_id, category, product_id, date_from, date_to)


SORT_KEYS = {
    "value": order_value,
    "days_late": days_late,
}


@router.get("", response_model=PurchaseOrderPage, summary="List purchase orders")
def list_purchase_orders(
    dataset: RetailDataset = Depends(get_dataset),
    filters: OrderFilters = Depends(order_filters),
    paging: PageParams = Depends(page_params),
    search: SearchQuery = None,
    status: Annotated[list[PurchaseOrderStatus] | None, Query(description="Repeat to match several")] = None,
    overdue: Annotated[bool | None, Query(description="Open and past the expected delivery date")] = None,
    delivered_late: Annotated[bool | None, Query(description="Delivered after the expected delivery date")] = None,
    sort: PurchaseOrderSort = "order_date",
    order: SortOrder = "desc",
):
    """Search matches the order ID or product name. Lateness is judged as of the dataset's last date.
    Rows without a value for the sort field (e.g. days late for an on-time order) go last."""
    as_of = dataset.as_of
    rows = [
        po
        for po in orders_in_scope(dataset, filters)
        if (not status or po.order_status in status)
        and (overdue is None or (is_open(po) and as_of is not None and is_late(po, as_of)) == overdue)
        and (delivered_late is None or (days_late(po) is not None) == delivered_late)
        and contains(search, po.purchase_order_id, dataset.product_by_id[po.product_id].product_name)
    ]
    if sort == "days_overdue":
        key = (lambda po: days_overdue(po, as_of)) if as_of else (lambda po: None)
    else:
        key = SORT_KEYS.get(sort) or (lambda po: getattr(po, sort))
    page = paginate(sort_items(rows, key, order), paging, lambda po: po_out(dataset, po))
    return {**page, "source": dataset.source, "as_of": as_of}


@router.get("/summary", response_model=PurchaseOrderSummaryResponse, summary="Purchase-order metrics")
def get_purchase_order_summary(
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
    filters: OrderFilters = Depends(order_filters),
):
    """Order counts and value by status, open and overdue orders (with aging), delivery performance,
    cancellations, the 14-day inbound schedule, and weekly series, for the scope filters given.

    Status, overdue, delivered-late, and search filters apply only to the order list. The on-time rate
    counts overdue open orders as late (see ``delivery.on_time_rate_definition``); the Overview's
    30-day rate counts delivered orders only. Returns ``status: "empty"`` when there are no orders
    or no inventory snapshot to judge lateness against.
    """
    freshness = asdict(repository.freshness())
    if not dataset.purchase_orders or dataset.as_of is None:
        reason = (
            "The data source has no purchase orders."
            if not dataset.purchase_orders
            else "The data source has no inventory snapshots to judge delivery dates against."
        )
        return {"status": "empty", "freshness": freshness, "source": dataset.source, "reason": reason}
    bounds = order_date_bounds(dataset)
    return {
        "status": "ok",
        "freshness": freshness,
        "source": dataset.source,
        "as_of": dataset.as_of,
        "bounds": {"date_from": bounds[0], "date_to": bounds[1]} if bounds else {"date_from": None, "date_to": None},
        "period": {"date_from": filters.date_from, "date_to": filters.date_to},
        "filters": {k: getattr(filters, k) for k in ("store_id", "supplier_id", "category", "product_id")},
        "facets": {
            "stores": dataset.stores,
            "categories": dataset.categories,
            "suppliers": [
                {"supplier_id": s.supplier_id, "supplier_name": s.supplier_name}
                for s in sorted(dataset.suppliers, key=lambda s: (s.supplier_name.lower(), s.supplier_id))
            ],
        },
        **purchase_order_summary(dataset, filters),
    }
