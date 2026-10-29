// Shapes of GET /api/v1/replenishment and /api/v1/replenishment/plan
// (backend/app/api/v1/replenishment_schemas.py; definitions in backend/app/analytics/replenishment.py).
import type { DataFreshness, PositionStatus } from "@/lib/dashboard/types";
import type { SupplierFacet } from "@/lib/sales/types";

export type Action = "order" | "expedite" | "watch";
export type Priority = "critical" | "high" | "medium" | "low";

export interface ReplenishmentSettings {
  demand_window_days: number;
  fallback_window_days: number[];
  min_in_stock_days: number;
  review_days: number;
  watch_days: number;
  lead_time_basis: "stated";
}

export interface Recommendation {
  position_id: string;
  store_id: string;
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  supplier_id: string;
  supplier_name: string;
  action: Action;
  priority: Priority;
  priority_reason: string;
  action_reason: string;
  warnings: string[];
  stock_status: PositionStatus;
  on_hand: number;
  reserved: number;
  available: number;
  safety_stock: number;
  reorder_point: number;
  on_order: number;
  inventory_position: number;
  open_po_count: number;
  next_delivery: string | null;
  next_delivery_overdue: boolean;
  /** Estimated, not measured: sales ÷ in-stock days. */
  demand_per_day: number;
  demand_basis: string;
  demand_confidence: "high" | "medium" | "low";
  demand_window_days: number | null;
  in_stock_days: number | null;
  units_in_window: number | null;
  excluded_days: number | null;
  days_of_cover: number | null;
  run_out_date: string | null;
  /** Estimate: projected run-out to the next expected delivery. */
  days_without_stock: number | null;
  stated_lead_time_days: number;
  observed_lead_time_days: number | null;
  supplier_on_time_rate: number | null;
  minimum_order_quantity: number;
  target_level: number;
  need: number;
  quantity: number;
  raised_to_moq: boolean;
  unit_cost: number;
  order_cost: number;
  expected_arrival: string | null;
  shelf_life_days: number | null;
  stock_days_after_order: number | null;
  exceeds_shelf_life: boolean;
  explanation: string[];
}

export interface Counts {
  by_priority: Record<Priority, number>;
  by_action: Record<Action, number>;
}

export interface RecommendationPage {
  items: Recommendation[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  source: "csv" | "databricks";
  as_of: string;
  counts: Counts;
  facets: { stores: string[]; categories: string[]; suppliers: SupplierFacet[] };
  settings: ReplenishmentSettings;
}

export interface PlanSupplier {
  supplier_id: string;
  supplier_name: string;
  stated_lead_time_days: number;
  expected_arrival: string | null;
  lines: number;
  units: number;
  cost: number;
  raised_to_moq: number;
  shelf_life_warnings: number;
  items: Recommendation[];
}

export interface SimulatedPlan {
  lines: number;
  units: number;
  cost: number;
  raised_to_moq: number;
  shelf_life_warnings: number;
  manual_review: number;
  suppliers: PlanSupplier[];
}

export interface ReplenishmentPlan {
  status: "ok";
  freshness: DataFreshness;
  source: "csv" | "databricks";
  as_of: string;
  simulation: true;
  notice: string;
  settings: ReplenishmentSettings;
  counts: Counts;
  plan: SimulatedPlan;
}

export type ReplenishmentPlanResponse =
  | ReplenishmentPlan
  | { status: "empty"; freshness: DataFreshness; source: "csv" | "databricks"; reason: string };
