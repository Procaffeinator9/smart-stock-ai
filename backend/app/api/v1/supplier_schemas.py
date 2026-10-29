"""Response models for the supplier performance endpoints (mirrors frontend/src/lib/suppliers/types.ts).

Definitions and "Needs attention" thresholds are in ``app/analytics/suppliers.py``.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.v1.endpoints.data_source import DataSourceStatus
from app.api.v1.sales_schemas import SalesPeriod
from app.api.v1.schemas import PositionStatus, PurchaseOrderOut

FlagCode = Literal[
    "low_on_time", "overdue_orders", "lead_time_slip", "at_risk_stock", "declining_on_time", "below_stated_reliability"
]


class AttentionFlag(BaseModel):
    code: FlagCode
    label: str
    reason: str = Field(description="The rule and the numbers that triggered it")


class SupplierScore(BaseModel):
    supplier_id: str
    supplier_name: str
    stated_reliability: float = Field(description="reliability_score from the supplier table: stated, not measured")
    stated_lead_time_days: int
    minimum_order_quantity: int
    orders: int
    spend: float = Field(description="Quantity × unit cost of orders that were not cancelled")
    cancelled: int
    cancellation_rate: float | None
    delivered: int
    on_time: int
    late: int
    on_time_rate: float | None = Field(description="Observed: delivered on or before the promised date ÷ (delivered + overdue open orders)")
    sample_size: int = Field(description="Orders behind the observed on-time rate: delivered + overdue open")
    delivered_only_on_time_rate: float | None
    reliability_gap: float | None = Field(description="Observed on-time rate − stated reliability")
    observed_lead_time_days: float | None = Field(description="Average order-to-delivery days, delivered orders")
    lead_time_gap_days: float | None = Field(description="Observed − stated lead time")
    avg_days_late: float | None
    open_orders: int
    open_value: float
    overdue_orders: int
    max_days_overdue: int | None
    recent_on_time_rate: float | None = Field(description="Orders promised in the last 30 days up to the as-of date")
    recent_sample: int
    previous_on_time_rate: float | None = Field(description="Orders promised in the 30 days before that")
    previous_sample: int
    products: int
    revenue: float = Field(description="Sales revenue of the products this supplier supplies, every sale date in the data")
    revenue_share: float | None
    units_sold: int
    stockout_days: int = Field(description="Store-days out of stock for those products: a correlation, not proof of supplier causation")
    positions: int
    at_risk_positions: int = Field(description="Store positions below safety stock or out of stock on the as-of date")
    low_positions: int
    flags: list[AttentionFlag]


class SupplierNetwork(BaseModel):
    suppliers: int
    flagged: int
    orders: int
    spend: float
    on_time: int
    sample_size: int
    on_time_rate: float | None
    overdue_orders: int
    revenue: float
    positions: int
    at_risk_positions: int


class SupplierScorecardOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    as_of: date = Field(description="Latest inventory snapshot date (not today's date)")
    period: SalesPeriod | None = Field(description="Sale dates covered by revenue and stockout days")
    network: SupplierNetwork = Field(description="All suppliers, whatever the search or attention filter")
    total: int = Field(description="Suppliers matching the search and attention filter")
    items: list[SupplierScore]


class SupplierDetails(BaseModel):
    supplier_id: str
    supplier_name: str
    contact_email: str
    stated_lead_time_days: int
    minimum_order_quantity: int
    stated_reliability: float


class MonthlyOnTime(BaseModel):
    month: date = Field(description="First day of the month of the promised date")
    on_time: int
    late: int
    overdue: int
    on_time_rate: float | None


class LateBucket(BaseModel):
    label: str
    min_days: int
    max_days: int | None
    orders: int


class SuppliedProduct(BaseModel):
    product_id: str
    product_name: str
    sku: str
    category: str
    revenue: float
    units_sold: int
    stockout_days: int
    stores: int
    status_counts: dict[PositionStatus, int]
    worst_status: PositionStatus | None
    at_risk_stores: int
    available: int
    open_po_quantity: int


class SupplierDetailOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    as_of: date = Field(description="Latest inventory snapshot date (not today's date)")
    period: SalesPeriod | None
    supplier: SupplierDetails
    scorecard: SupplierScore
    monthly: list[MonthlyOnTime] = Field(description="Orders with a known outcome, by month of the promised date")
    late_distribution: list[LateBucket] = Field(description="Delivered orders by days late")
    products: list[SuppliedProduct] = Field(description="Most at-risk stock first, then highest revenue")
    overdue_orders: list[PurchaseOrderOut] = Field(description="Up to 20, most overdue first")
    recent_orders: list[PurchaseOrderOut] = Field(description="The 10 most recently placed orders")


class SupplierPerformanceEmpty(BaseModel):
    status: Literal["empty"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    reason: str


SupplierScorecardResponse = Annotated[SupplierScorecardOk | SupplierPerformanceEmpty, Field(discriminator="status")]
SupplierDetailResponse = Annotated[SupplierDetailOk | SupplierPerformanceEmpty, Field(discriminator="status")]
