from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.analytics.sales import (
    DEFAULT_WINDOW_DAYS,
    Period,
    SalesFilters,
    previous_period,
    product_performance,
    sales_bounds,
    sales_summary,
)
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
from app.api.v1.sales_schemas import ProductPerformancePage, SalesSummaryResponse
from app.api.v1.schemas import SalesPage
from app.data.dataset import RetailDataset
from app.data.repository import Repository, get_dataset, get_repository
from app.synthetic.generator import Sale

router = APIRouter(prefix="/sales", tags=["sales"])

SaleSort = Literal["sale_date", "quantity_sold", "unit_selling_price", "revenue", "sale_id"]
ProductSort = Literal[
    "revenue",
    "units",
    "gross_margin",
    "margin_rate",
    "avg_unit_price",
    "promo_revenue_share",
    "stockout_days",
    "revenue_change",
    "product_name",
    "category",
]
MAX_WINDOW_DAYS = 366
NO_SALES_REASON = "The data source has no sales to analyse."


def _revenue(sale: Sale) -> Decimal:
    return sale.unit_selling_price * sale.quantity_sold


def sale_out(dataset: RetailDataset, sale: Sale) -> dict[str, Any]:
    product = dataset.product_by_id[sale.product_id]
    return {**asdict(sale), "product_name": product.product_name, "category": product.category, "revenue": _revenue(sale)}


@router.get("", response_model=SalesPage, summary="List sales lines")
def list_sales(
    dataset: RetailDataset = Depends(get_dataset),
    paging: PageParams = Depends(page_params),
    date_from: date | None = None,
    date_to: date | None = None,
    store_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    promotion: bool | None = None,
    sort: SaleSort = "sale_date",
    order: SortOrder = "desc",
):
    """Dates are inclusive. ``totals`` covers every matching row, not just the returned page."""
    require_date_order(date_from, date_to)
    require_choice("store_id", store_id, dataset.stores)
    require_choice("category", category, dataset.categories)
    require_known("product_id", product_id, dataset.product_by_id)

    rows = [
        s
        for s in dataset.sales
        if (date_from is None or s.sale_date >= date_from)
        and (date_to is None or s.sale_date <= date_to)
        and (store_id is None or s.store_id == store_id)
        and (product_id is None or s.product_id == product_id)
        and (category is None or dataset.product_by_id[s.product_id].category == category)
        and (promotion is None or s.promotion_applied == promotion)
    ]
    key = _revenue if sort == "revenue" else (lambda s: getattr(s, sort))
    page = paginate(sort_items(rows, key, order), paging, lambda s: sale_out(dataset, s))
    page["totals"] = {"units": sum(s.quantity_sold for s in rows), "revenue": sum((_revenue(s) for s in rows), Decimal(0))}
    return page


# --- Sales analytics (aggregates; raw rows stay on the server) ---------------------------------


@dataclass(frozen=True)
class AnalyticsQuery:
    bounds: Period
    period: Period
    filters: SalesFilters


def analytics_query(
    dataset: RetailDataset = Depends(get_dataset),
    date_from: Annotated[date | None, Query(description="First day (inclusive)")] = None,
    date_to: Annotated[date | None, Query(description="Last day (inclusive); defaults to the last sale date")] = None,
    days: Annotated[
        int | None,
        Query(ge=1, le=MAX_WINDOW_DAYS, description=f"Window ending at date_to, when date_from is not given (default {DEFAULT_WINDOW_DAYS})"),
    ] = None,
    store_id: str | None = None,
    category: str | None = None,
    supplier_id: str | None = None,
    promotion: Annotated[bool | None, Query(description="true: promotional sales only; false: regular-price only")] = None,
) -> AnalyticsQuery | None:
    """Validated filters and the resolved window, clamped to the sale dates in the data. None when
    the data has no sales."""
    if days is not None and date_from is not None:
        raise invalid_query("days", "Use either days or date_from, not both")
    require_date_order(date_from, date_to)
    require_choice("store_id", store_id, dataset.stores)
    require_choice("category", category, dataset.categories)
    require_known("supplier_id", supplier_id, dataset.supplier_by_id)

    bounds = sales_bounds(dataset)
    if bounds is None:
        return None
    end = date_to or bounds.date_to
    start = date_from or end - timedelta(days=(days or DEFAULT_WINDOW_DAYS) - 1)
    if start > bounds.date_to or end < bounds.date_from:
        raise invalid_query(
            "date_from", f"The requested dates are outside the sales data, which covers {bounds.date_from} to {bounds.date_to}"
        )
    period = Period(max(start, bounds.date_from), min(end, bounds.date_to))
    return AnalyticsQuery(bounds, period, SalesFilters(store_id, category, supplier_id, promotion))


@router.get("/summary", response_model=SalesSummaryResponse, summary="Sales analytics for a period")
def get_sales_summary(
    query: AnalyticsQuery | None = Depends(analytics_query),
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
):
    """KPIs compared with the previous period of the same length, daily series, revenue by category
    and store, and promotion metrics, for the filters given.

    The window defaults to the last 30 days of sales and is clamped to the data. Results are cached
    per data snapshot and filter combination. Returns ``status: "empty"`` when the data has no sales.
    """
    freshness = asdict(repository.freshness())
    if query is None:
        return {"status": "empty", "freshness": freshness, "source": dataset.source, "reason": NO_SALES_REASON}
    return {
        "status": "ok",
        "freshness": freshness,
        "source": dataset.source,
        "as_of": dataset.as_of,
        "bounds": query.bounds.as_dict(),
        "filters": asdict(query.filters),
        "facets": {
            "stores": dataset.stores,
            "categories": dataset.categories,
            "suppliers": [
                {"supplier_id": s.supplier_id, "supplier_name": s.supplier_name}
                for s in sorted(dataset.suppliers, key=lambda s: (s.supplier_name.lower(), s.supplier_id))
            ],
        },
        **sales_summary(dataset, query.period, query.filters, query.bounds),
    }


@router.get("/products", response_model=ProductPerformancePage, summary="Sales performance by product")
def list_product_performance(
    query: AnalyticsQuery | None = Depends(analytics_query),
    dataset: RetailDataset = Depends(get_dataset),
    paging: PageParams = Depends(page_params),
    search: SearchQuery = None,
    sort: ProductSort = "revenue",
    order: SortOrder = "desc",
):
    """One row per product matching the category and supplier filters, including products with no
    sales in the period. Same window and filters as ``/sales/summary``; search matches product name,
    SKU, or product ID. Rows with no value for the sort field (e.g. no previous period) go last."""
    if query is None:
        page = paginate([], paging)
        return {**page, "source": dataset.source, "period": None, "previous_period": None}

    rows = [
        r
        for r in product_performance(dataset, query.period, query.filters, query.bounds)
        if contains(search, r["product_name"], r["sku"], r["product_id"])
    ]
    key = (lambda r: r["product_name"].lower()) if sort == "product_name" else (lambda r: r[sort])
    prior = previous_period(query.period, query.bounds)
    return {
        **paginate(sort_items(rows, key, order), paging),
        "source": dataset.source,
        "period": query.period.as_dict(),
        "previous_period": prior.as_dict() if prior else None,
    }
