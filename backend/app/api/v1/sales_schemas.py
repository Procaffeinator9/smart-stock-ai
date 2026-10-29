"""Response models for the sales analytics endpoints (mirrors frontend/src/lib/sales/types.ts).

Definitions of every figure are in ``app/analytics/sales.py``.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.v1.common import Page
from app.api.v1.endpoints.data_source import DataSourceStatus


class SalesPeriod(BaseModel):
    date_from: date
    date_to: date
    days: int


class SalesFilterValues(BaseModel):
    store_id: str | None
    category: str | None
    supplier_id: str | None
    promotion: bool | None


class SupplierFacet(BaseModel):
    supplier_id: str
    supplier_name: str


class SalesFacets(BaseModel):
    stores: list[str]
    categories: list[str]
    suppliers: list[SupplierFacet]


class SalesKpiTotals(BaseModel):
    revenue: float
    units: int
    gross_margin: float = Field(description="Revenue minus units × the product's standard unit cost")
    margin_rate: float | None = Field(description="Gross margin ÷ revenue; null without revenue")
    avg_unit_price: float | None = Field(description="Revenue ÷ units; null without units")
    sale_lines: int = Field(description="Daily store-product sales rows (not customer transactions)")
    products_sold: int
    promo_revenue: float
    promo_units: int
    promo_revenue_share: float | None
    promo_units_share: float | None
    stockout_days: int = Field(description="Store-product days ending with no available units; ignores the promotion filter")


class SalesKpis(BaseModel):
    current: SalesKpiTotals
    previous: SalesKpiTotals | None = Field(description="Same-length window just before the period; null when not covered by the data")


class SalesDailySeries(BaseModel):
    """Aligned arrays: element i of every series belongs to dates[i]. Every day in the period is present."""

    dates: list[date]
    revenue: list[float]
    units: list[int]
    gross_margin: list[float]
    promo_revenue: list[float]


class _Breakdown(BaseModel):
    revenue: float
    units: int
    gross_margin: float
    margin_rate: float | None
    share: float = Field(description="Share of the period's revenue for the current filters")
    previous_revenue: float | None
    change: float | None = Field(description="Revenue change vs the previous period, as a ratio")


class CategorySales(_Breakdown):
    category: str


class StoreSales(_Breakdown):
    store_id: str


class PromotionMetrics(BaseModel):
    promo_revenue: float
    promo_units: int
    promo_lines: int
    revenue_share: float | None
    units_share: float | None
    avg_discount: float | None = Field(description="1 − promotional revenue ÷ the same units at list price")
    promoted_products: int
    units_per_line_promo: float | None
    units_per_line_regular: float | None = Field(description="For the products promoted in the period")
    uplift: float | None = Field(description="units_per_line_promo ÷ units_per_line_regular − 1")


class SalesSummaryOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus = Field(description="Computed per request; the figures are cached per data snapshot")
    source: Literal["csv", "databricks"]
    as_of: date | None = Field(description="Latest inventory snapshot date in the data (not today's date)")
    bounds: SalesPeriod = Field(description="First and last sale date in the data")
    period: SalesPeriod = Field(description="The window used, after defaults and clamping to the data")
    previous_period: SalesPeriod | None
    filters: SalesFilterValues
    facets: SalesFacets
    kpis: SalesKpis
    daily: SalesDailySeries
    by_category: list[CategorySales]
    by_store: list[StoreSales]
    promotion: PromotionMetrics


class SalesSummaryEmpty(BaseModel):
    status: Literal["empty"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    reason: str


SalesSummaryResponse = Annotated[SalesSummaryOk | SalesSummaryEmpty, Field(discriminator="status")]


class ProductPerformanceOut(BaseModel):
    product_id: str
    product_name: str
    sku: str
    category: str
    supplier_id: str
    supplier_name: str
    revenue: float
    units: int
    gross_margin: float
    margin_rate: float | None
    avg_unit_price: float | None
    revenue_share: float | None = Field(description="Share of the period's revenue for the current filters")
    promo_revenue_share: float | None
    stores_sold: int
    stockout_days: int
    previous_revenue: float | None
    revenue_change: float | None


class ProductPerformancePage(Page[ProductPerformanceOut]):
    source: Literal["csv", "databricks"]
    period: SalesPeriod | None = Field(description="Null when the data has no sales")
    previous_period: SalesPeriod | None
