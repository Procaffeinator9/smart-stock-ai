from collections import Counter
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.analytics.stock import is_open
from app.analytics.suppliers import supplier_detail, supplier_scorecard
from app.api.v1.common import Page, PageParams, SearchQuery, SortOrder, contains, page_params, paginate, sort_items
from app.api.v1.schemas import SupplierOut
from app.api.v1.supplier_schemas import SupplierDetailResponse, SupplierScorecardResponse
from app.data.dataset import RetailDataset
from app.data.repository import Repository, get_dataset, get_repository
from app.synthetic.generator import Supplier

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

SupplierSort = Literal["supplier_id", "supplier_name", "lead_time_days", "minimum_order_quantity", "reliability_score"]
SupplierScoreSort = Literal[
    "attention",
    "supplier_name",
    "on_time_rate",
    "reliability_gap",
    "stated_reliability",
    "lead_time_gap_days",
    "spend",
    "orders",
    "overdue_orders",
    "at_risk_positions",
    "revenue",
    "stockout_days",
]


def _counts(dataset: RetailDataset) -> tuple[Counter, Counter]:
    if "supplier_counts" not in dataset._cache:
        dataset._cache["supplier_counts"] = (
            Counter(p.supplier_id for p in dataset.products),
            Counter(po.supplier_id for po in dataset.purchase_orders if is_open(po)),
        )
    return dataset._cache["supplier_counts"]


def supplier_out(dataset: RetailDataset, supplier: Supplier) -> dict[str, Any]:
    products, open_orders = _counts(dataset)
    return {
        **asdict(supplier),
        "product_count": products[supplier.supplier_id],
        "open_purchase_orders": open_orders[supplier.supplier_id],
    }


@router.get("", response_model=Page[SupplierOut], summary="List suppliers")
def list_suppliers(
    dataset: RetailDataset = Depends(get_dataset),
    paging: PageParams = Depends(page_params),
    search: SearchQuery = None,
    sort: SupplierSort = "supplier_id",
    order: SortOrder = "asc",
):
    """Search matches supplier name or supplier ID."""
    rows = [s for s in dataset.suppliers if contains(search, s.supplier_name, s.supplier_id)]
    key = (lambda s: s.supplier_name.lower()) if sort == "supplier_name" else (lambda s: getattr(s, sort))
    return paginate(sort_items(rows, key, order), paging, lambda s: supplier_out(dataset, s))


def _not_ready(dataset: RetailDataset, freshness: dict[str, Any]) -> dict[str, Any] | None:
    """An "empty" response when there is nothing to score, else None."""
    if not dataset.suppliers:
        reason = "The data source has no suppliers."
    elif dataset.as_of is None:
        reason = "The data source has no inventory snapshots to judge delivery dates and stock against."
    else:
        return None
    return {"status": "empty", "freshness": freshness, "source": dataset.source, "reason": reason}


SCORE_SORT_KEYS = {
    "attention": lambda r: len(r["flags"]),
    "supplier_name": lambda r: r["supplier_name"].lower(),
}


# Declared before /{supplier_id} so "performance" is not read as a supplier ID.
@router.get("/performance", response_model=SupplierScorecardResponse, summary="Supplier performance scorecard")
def get_supplier_scorecard(
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
    search: SearchQuery = None,
    attention: Annotated[bool | None, Query(description="true: only suppliers with a Needs attention flag; false: only those without")] = None,
    sort: SupplierScoreSort = "attention",
    order: SortOrder = "desc",
):
    """One row per supplier: observed on-time rate (the Purchase Orders definition) next to the stated
    reliability, stated vs observed lead time, spend, open and overdue orders, revenue of the products
    supplied, stockout days, at-risk stock positions, and "Needs attention" flags with their reasons.

    Search matches supplier name or ID. Rows with no value for the sort field go last; ties keep
    supplier ID order. ``network`` covers every supplier regardless of the search or attention filter.
    """
    freshness = asdict(repository.freshness())
    if (empty := _not_ready(dataset, freshness)) is not None:
        return empty
    scorecard = supplier_scorecard(dataset)
    rows = [
        r
        for r in scorecard["suppliers"]
        if contains(search, r["supplier_name"], r["supplier_id"]) and (attention is None or bool(r["flags"]) == attention)
    ]
    key = SCORE_SORT_KEYS.get(sort) or (lambda r: r[sort])
    items = sort_items(rows, key, order)
    return {
        "status": "ok",
        "freshness": freshness,
        "source": dataset.source,
        "as_of": dataset.as_of,
        "period": scorecard["period"],
        "network": scorecard["network"],
        "total": len(items),
        "items": items,
    }


@router.get("/{supplier_id}/performance", response_model=SupplierDetailResponse, summary="Supplier performance detail")
def get_supplier_performance(
    supplier_id: Annotated[str, Path(max_length=32)],
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
):
    """The supplier's scorecard row plus a monthly on-time trend, delivered orders by days late, the
    products supplied with their stock status on the as-of date, overdue orders, and recent orders."""
    if supplier_id not in dataset.supplier_by_id:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")
    freshness = asdict(repository.freshness())
    if (empty := _not_ready(dataset, freshness)) is not None:
        return empty
    scorecard = supplier_scorecard(dataset)
    return {
        "status": "ok",
        "freshness": freshness,
        "source": dataset.source,
        "as_of": dataset.as_of,
        "period": scorecard["period"],
        **supplier_detail(dataset, supplier_id),
    }


@router.get("/{supplier_id}", response_model=SupplierOut, summary="Get a supplier")
def get_supplier(
    supplier_id: Annotated[str, Path(max_length=32)],
    dataset: RetailDataset = Depends(get_dataset),
):
    supplier = dataset.supplier_by_id.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")
    return supplier_out(dataset, supplier)
