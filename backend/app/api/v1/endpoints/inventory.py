from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.analytics.inventory import InventoryPosition, inventory_positions
from app.analytics.stock import STATUS_RANK
from app.api.v1.common import (
    PageParams,
    SearchQuery,
    SortOrder,
    contains,
    invalid_query,
    page_params,
    paginate,
    require_choice,
    sort_items,
)
from app.api.v1.schemas import InventoryPage, PositionStatus
from app.data.dataset import RetailDataset
from app.data.repository import DataSourceUnavailableError, get_dataset

router = APIRouter(prefix="/inventory", tags=["inventory"])

InventorySort = Literal[
    "severity",
    "product_name",
    "store_id",
    "category",
    "available",
    "days_of_cover",
    "reorder_point",
    "safety_stock",
    "inventory_position",
    "next_delivery",
]

SORT_KEYS = {
    "severity": lambda p: p.severity_key,
    "product_name": lambda p: p.product_name.lower(),
    "store_id": lambda p: p.store_id,
    "category": lambda p: p.category,
    "available": lambda p: p.available,
    "days_of_cover": lambda p: p.days_of_cover,
    "reorder_point": lambda p: p.reorder_point,
    "safety_stock": lambda p: p.safety_stock,
    "inventory_position": lambda p: p.inventory_position,
    "next_delivery": lambda p: p.next_delivery,
}


@router.get("", response_model=InventoryPage, summary="Inventory worklist by store and product")
def list_inventory(
    dataset: RetailDataset = Depends(get_dataset),
    paging: PageParams = Depends(page_params),
    snapshot_date: Annotated[date | None, Query(description="Defaults to the latest snapshot")] = None,
    search: SearchQuery = None,
    store_id: str | None = None,
    category: str | None = None,
    status: Annotated[list[PositionStatus] | None, Query(description="Repeat to match several")] = None,
    has_open_po: bool | None = None,
    sort: InventorySort = "severity",
    order: SortOrder = "asc",
):
    """One row per store and product. Search matches product name, SKU, product ID, or supplier.

    ``severity`` sorts out-of-stock first, then below safety stock, then low, then healthy, and
    within each by fewest days of cover. ``summary`` counts statuses for the current filters,
    ignoring the status filter, so filter chips can show how many rows each would add.
    """
    if dataset.as_of is None:
        raise DataSourceUnavailableError("The data source has no inventory snapshots.")
    day = snapshot_date or dataset.as_of
    if snapshot_date is not None and snapshot_date not in set(dataset.snapshot_dates):
        first, last = dataset.snapshot_dates[0], dataset.snapshot_dates[-1]
        raise invalid_query("snapshot_date", f"No inventory snapshot for {snapshot_date}. Available: {first} to {last}")
    require_choice("store_id", store_id, dataset.stores)
    require_choice("category", category, dataset.categories)

    def matches(p: InventoryPosition) -> bool:
        return (
            (store_id is None or p.store_id == store_id)
            and (category is None or p.category == category)
            and (has_open_po is None or (p.open_po_count > 0) == has_open_po)
            and contains(search, p.product_name, p.sku, p.product_id, p.supplier_name)
        )

    filtered = [p for p in inventory_positions(dataset, day) if matches(p)]
    counts = Counter(p.status for p in filtered)
    if status:
        filtered = [p for p in filtered if p.status in status]

    page = paginate(sort_items(filtered, SORT_KEYS[sort], order), paging, asdict)
    return {
        **page,
        "source": dataset.source,
        "as_of": day,
        "summary": {s: counts[s] for s in sorted(STATUS_RANK, key=STATUS_RANK.__getitem__)},
        "facets": {"stores": dataset.stores, "categories": dataset.categories},
    }
