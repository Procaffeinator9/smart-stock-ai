"""Response model for GET /api/v1/overview (mirrors frontend/src/lib/dashboard/types.ts)."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.v1.endpoints.data_source import DataSourceStatus
from app.api.v1.schemas import PositionStatus, PurchaseOrderStatus


class OverviewMeta(BaseModel):
    schema_version: int
    source: Literal["synthetic", "csv", "databricks"]
    generator: str | None = Field(description="Set only for the offline synthetic export")
    seed: int | None = Field(description="Set only for the offline synthetic export")
    start_date: date
    end_date: date
    as_of: date = Field(description="Latest inventory snapshot date in the data (not today's date)")
    stores: list[str]
    categories: list[str]
    currency: str


class InventorySummary(BaseModel):
    inventory_value: float
    inventory_units: int
    low_stock_products: int
    stockout_risk_products: int
    positions: dict[PositionStatus, int]


class OverviewKpis(BaseModel):
    total_products: int
    categories: int
    suppliers: int
    stores: int
    current: InventorySummary
    week_before: InventorySummary | None


class DailySeries(BaseModel):
    """Aligned arrays: element i of every series belongs to dates[i]."""

    dates: list[date]
    revenue: list[float]
    units: list[int]
    category_revenue: dict[str, list[float]]
    inventory_value: list[float]
    low_stock_products: list[int]
    stockout_risk_products: list[int]


class InventoryAlert(BaseModel):
    product_id: str
    product_name: str
    sku: str
    category: str
    supplier_name: str
    store_id: str
    status: PositionStatus
    available: int
    on_hand: int
    reserved: int
    reorder_point: int
    safety_stock: int
    avg_daily_units: float
    days_of_cover: float | None
    next_delivery: date | None


class OverviewPurchaseOrder(BaseModel):
    purchase_order_id: str
    supplier_name: str
    product_name: str
    store_id: str
    quantity: int
    value: float
    order_date: date
    expected_delivery_date: date
    actual_delivery_date: date | None
    status: PurchaseOrderStatus
    is_late: bool


class PurchaseOrderSummary(BaseModel):
    open: int
    overdue: int
    delivered_last_30_days: int
    on_time_rate_last_30_days: float | None


class OverviewPurchaseOrders(BaseModel):
    summary: PurchaseOrderSummary
    recent: list[OverviewPurchaseOrder]
    overdue: list[OverviewPurchaseOrder]


class StoreHealth(BaseModel):
    store_id: str
    positions: int
    out_of_stock: int
    critical: int
    low: int
    healthy: int
    inventory_value: float


class ForecastHistoryPoint(BaseModel):
    date: date
    units: int


class ForecastPoint(BaseModel):
    date: date
    units: float
    low: int
    high: int


class Forecast(BaseModel):
    method: str
    history: list[ForecastHistoryPoint]
    projection: list[ForecastPoint]


class OverviewOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus = Field(description="Computed per request; the metrics are cached per data snapshot")
    meta: OverviewMeta
    kpis: OverviewKpis
    daily: DailySeries
    alerts: list[InventoryAlert]
    purchase_orders: OverviewPurchaseOrders
    store_health: list[StoreHealth]
    forecast: Forecast


class OverviewEmpty(BaseModel):
    status: Literal["empty"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    reason: str


OverviewResponse = Annotated[OverviewOk | OverviewEmpty, Field(discriminator="status")]
