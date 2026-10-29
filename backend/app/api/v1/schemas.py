"""Response models for the read-only data API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.common import Money, Page

PositionStatus = Literal["out_of_stock", "critical", "low", "healthy"]
PurchaseOrderStatus = Literal["PLACED", "IN_TRANSIT", "DELIVERED", "CANCELLED"]


class ProductOut(BaseModel):
    product_id: str
    sku: str
    product_name: str
    category: str
    unit_cost: Money
    selling_price: Money
    supplier_id: str
    supplier_name: str
    shelf_life_days: int | None
    created_at: datetime


class SupplierOut(BaseModel):
    supplier_id: str
    supplier_name: str
    contact_email: str
    lead_time_days: int
    minimum_order_quantity: int
    reliability_score: Money
    product_count: int
    open_purchase_orders: int


class SaleOut(BaseModel):
    sale_id: str
    sale_date: date
    store_id: str
    product_id: str
    product_name: str
    category: str
    quantity_sold: int
    unit_selling_price: Money
    revenue: Money
    promotion_applied: bool


class SalesTotals(BaseModel):
    units: int
    revenue: Money


class SalesPage(Page[SaleOut]):
    totals: SalesTotals  # over every row matching the filters, not just this page


class PurchaseOrderOut(BaseModel):
    purchase_order_id: str
    supplier_id: str
    supplier_name: str
    product_id: str
    product_name: str
    store_id: str
    order_date: date
    expected_delivery_date: date
    actual_delivery_date: date | None
    quantity_ordered: int
    unit_cost: Money
    value: Money
    order_status: PurchaseOrderStatus
    is_late: bool = Field(description="Delivered after the promised date, or open and past it")
    category: str
    is_overdue: bool = Field(description="Open (placed or in transit) and past the promised date as of the dataset date")
    days_overdue: int | None = Field(description="Dataset as-of date minus the promised date, for overdue orders")
    days_late: int | None = Field(description="Delivery date minus the promised date, for orders delivered late")


class PurchaseOrderPage(Page[PurchaseOrderOut]):
    source: Literal["csv", "databricks"]
    as_of: date | None = Field(description="Date lateness is judged against: the latest inventory snapshot (not today's date)")


class OpenPurchaseOrderOut(BaseModel):
    purchase_order_id: str
    supplier_id: str
    quantity: int
    order_date: date
    expected_delivery_date: date
    status: Literal["PLACED", "IN_TRANSIT", "OPEN"]
    is_overdue: bool


class InventoryPositionOut(BaseModel):
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
    inventory_position: int
    next_delivery: date | None
    next_delivery_overdue: bool
    open_purchase_orders: list[OpenPurchaseOrderOut]


class ProductDetailOut(ProductOut):
    as_of: date | None
    stock: list[InventoryPositionOut]


class InventoryFacets(BaseModel):
    stores: list[str]
    categories: list[str]


class InventoryPage(Page[InventoryPositionOut]):
    source: Literal["csv", "databricks"]
    as_of: date
    # Status counts for the current filters, ignoring the status filter itself (for filter chips).
    summary: dict[PositionStatus, int]
    facets: InventoryFacets
