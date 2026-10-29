"""Response models for the replenishment endpoints (mirrors frontend/src/lib/replenishment/types.ts).

Definitions are in ``app/analytics/replenishment.py``. Everything here is read-only: no purchase
order is created or changed.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.v1.common import Money, Page
from app.api.v1.endpoints.data_source import DataSourceStatus
from app.api.v1.sales_schemas import SupplierFacet
from app.api.v1.schemas import PositionStatus

Action = Literal["order", "expedite", "watch"]
Priority = Literal["critical", "high", "medium", "low"]


class ReplenishmentSettings(BaseModel):
    demand_window_days: int
    fallback_window_days: list[int]
    min_in_stock_days: int
    review_days: int
    watch_days: int
    lead_time_basis: Literal["stated"]


class Recommendation(BaseModel):
    position_id: str = Field(description="store_id|product_id")
    store_id: str
    product_id: str
    product_name: str
    sku: str
    category: str
    supplier_id: str
    supplier_name: str
    action: Action
    priority: Priority
    priority_reason: str
    action_reason: str
    warnings: list[str] = Field(description="Shelf-life conflicts, MOQ raises, overdue deliveries, low-confidence demand")
    stock_status: PositionStatus
    on_hand: int
    reserved: int
    available: int
    safety_stock: int
    reorder_point: int
    on_order: int
    inventory_position: int = Field(description="Available + units on open orders (overdue orders included)")
    open_po_count: int
    next_delivery: date | None
    next_delivery_overdue: bool
    demand_per_day: float = Field(description="Estimated, not measured: sales ÷ in-stock days")
    demand_basis: str
    demand_confidence: Literal["high", "medium", "low"]
    demand_window_days: int | None
    in_stock_days: int | None
    units_in_window: int | None
    excluded_days: int | None = Field(description="Days in the window that started out of stock")
    days_of_cover: float | None
    run_out_date: date | None = Field(description="Projected, at the estimated demand")
    days_without_stock: int | None = Field(description="Estimate: projected run-out to the next expected delivery")
    stated_lead_time_days: int
    observed_lead_time_days: float | None
    supplier_on_time_rate: float | None
    minimum_order_quantity: int
    target_level: int
    need: int
    quantity: int = Field(description="Recommended order quantity (0 unless action is order)")
    raised_to_moq: bool
    unit_cost: Money
    order_cost: Money
    expected_arrival: date | None = Field(description="If ordered on the as-of date, at the stated lead time")
    shelf_life_days: int | None
    stock_days_after_order: float | None
    exceeds_shelf_life: bool
    explanation: list[str] = Field(description="The calculation, step by step, with this row's numbers")


class Counts(BaseModel):
    by_priority: dict[Priority, int]
    by_action: dict[Action, int]


class ReplenishmentFacets(BaseModel):
    stores: list[str]
    categories: list[str]
    suppliers: list[SupplierFacet]


class RecommendationPage(Page[Recommendation]):
    source: Literal["csv", "databricks"]
    as_of: date = Field(description="Latest inventory snapshot date (not today's date)")
    counts: Counts = Field(description="by_priority respects the action filter, by_action the priority filter; each ignores its own")
    facets: ReplenishmentFacets
    settings: ReplenishmentSettings


class PlanSupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    stated_lead_time_days: int
    expected_arrival: date | None
    lines: int
    units: int
    cost: Money
    raised_to_moq: int
    shelf_life_warnings: int
    items: list[Recommendation]


class SimulatedPlan(BaseModel):
    lines: int
    units: int
    cost: Money
    raised_to_moq: int
    shelf_life_warnings: int
    manual_review: int = Field(description="Order needed but no recent demand: no quantity recommended")
    suppliers: list[PlanSupplier]


class ReplenishmentPlanOk(BaseModel):
    status: Literal["ok"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    as_of: date = Field(description="Latest inventory snapshot date (not today's date)")
    simulation: Literal[True] = Field(description="Always true: no purchase orders are created")
    notice: str
    settings: ReplenishmentSettings
    counts: Counts
    plan: SimulatedPlan


class ReplenishmentEmpty(BaseModel):
    status: Literal["empty"]
    freshness: DataSourceStatus
    source: Literal["csv", "databricks"]
    reason: str


ReplenishmentPlanResponse = Annotated[ReplenishmentPlanOk | ReplenishmentEmpty, Field(discriminator="status")]
