"""Response model for GET /api/v1/purchase-orders/summary (mirrors frontend/src/lib/purchase-orders/types.ts).

Definitions of every figure are in ``app/analytics/purchase_orders.py``.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.v1.endpoints.data_source import DataSourceStatus
from app.api.v1.sales_schemas import SupplierFacet
from app.api.v1.schemas import PurchaseOrderOut, PurchaseOrderStatus


class OrderAmounts(BaseModel):
    orders: int
    value: float = Field(description="Quantity ordered × unit cost")
    units: int


class StatusAmounts(OrderAmounts):
    status: PurchaseOrderStatus


class AgingBucket(OrderAmounts):
    label: str
    min_days: int
    max_days: int | None


class OverdueSummary(OrderAmounts):
    avg_days_overdue: float | None
    max_days_overdue: int | None
    aging: list[AgingBucket]
    top: list[PurchaseOrderOut] = Field(description="Up to 10 overdue orders, most days overdue first")


class DeliverySummary(BaseModel):
    delivered: int
    on_time: int = Field(description="Delivered on or before the promised date")
    late: int = Field(description="Delivered after the promised date")
    overdue_open: int
    on_time_rate: float | None
    on_time_rate_definition: str
    delivered_only_on_time_rate: float | None
    delivered_only_definition: str
    avg_days_late: float | None = Field(description="Over orders delivered late")
    max_days_late: int | None
    avg_promised_lead_days: float | None = Field(description="Promised date − order date, delivered orders")
    avg_actual_lead_days: float | None = Field(description="Delivery date − order date, delivered orders")


class CancellationSummary(BaseModel):
    orders: int
    cancelled: int
    rate: float | None
    definition: str


class InboundDay(OrderAmounts):
    date: date


class InboundSchedule(OrderAmounts):
    date_from: date = Field(description="The as-of date")
    date_to: date = Field(description="13 days after the as-of date (14 days in all)")
    days: list[InboundDay]
    later: OrderAmounts = Field(description="Open orders promised after date_to")


class _Week(BaseModel):
    week_start: date = Field(description="Monday of the week")
    date_from: date = Field(description="First day included (later than week_start for a partial week)")
    date_to: date
    days: int


class WeeklyOrders(_Week, OrderAmounts):
    cancelled: int


class WeeklyDelivery(_Week):
    on_time: int
    late: int
    overdue: int
    on_time_rate: float | None


class OrderPeriod(BaseModel):
    date_from: date | None
    date_to: date | None


class OrderFilterValues(BaseModel):
    store_id: str | None
    supplier_id: str | None
    category: str | None
    product_id: str | None


class OrderFacets(BaseModel):
    stores: list[str]
    categories: list[str]
    suppliers: list[SupplierFacet]


class PurchaseOrderSummaryOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus = Field(description="Computed per request; the figures are cached per data snapshot")
    source: Literal["csv", "databricks"]
    as_of: date = Field(description="Latest inventory snapshot date: lateness is judged as of this date (not today's date)")
    bounds: OrderPeriod = Field(description="First and last order date in the data")
    period: OrderPeriod = Field(description="Order-date window applied (null ends are open)")
    filters: OrderFilterValues
    facets: OrderFacets
    totals: OrderAmounts
    by_status: list[StatusAmounts]
    open: OrderAmounts = Field(description="Placed or in transit")
    overdue: OverdueSummary
    delivery: DeliverySummary
    cancellation: CancellationSummary
    inbound: InboundSchedule
    weekly_orders: list[WeeklyOrders] = Field(description="Orders placed per week, by order date")
    weekly_delivery: list[WeeklyDelivery] = Field(description="Delivery outcomes per week of the promised date")


class PurchaseOrderSummaryEmpty(BaseModel):
    status: Literal["empty"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    reason: str


PurchaseOrderSummaryResponse = Annotated[
    PurchaseOrderSummaryOk | PurchaseOrderSummaryEmpty, Field(discriminator="status")
]
