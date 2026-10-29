// Shapes of GET /api/v1/suppliers/performance and /api/v1/suppliers/{id}/performance
// (backend/app/api/v1/supplier_schemas.py; definitions in backend/app/analytics/suppliers.py).
import type { DataFreshness, PositionStatus } from "@/lib/dashboard/types";
import type { PurchaseOrder } from "@/lib/purchase-orders/types";
import type { SalesPeriod } from "@/lib/sales/types";

export type FlagCode =
  | "low_on_time"
  | "overdue_orders"
  | "lead_time_slip"
  | "at_risk_stock"
  | "declining_on_time"
  | "below_stated_reliability";

export interface AttentionFlag {
  code: FlagCode;
  label: string;
  reason: string;
}

export interface SupplierScore {
  supplier_id: string;
  supplier_name: string;
  /** From the supplier table: stated, not measured. */
  stated_reliability: number;
  stated_lead_time_days: number;
  minimum_order_quantity: number;
  orders: number;
  spend: number;
  cancelled: number;
  cancellation_rate: number | null;
  delivered: number;
  on_time: number;
  late: number;
  /** Observed: delivered on or before the promised date ÷ (delivered + overdue open). */
  on_time_rate: number | null;
  sample_size: number;
  delivered_only_on_time_rate: number | null;
  reliability_gap: number | null;
  observed_lead_time_days: number | null;
  lead_time_gap_days: number | null;
  avg_days_late: number | null;
  open_orders: number;
  open_value: number;
  overdue_orders: number;
  max_days_overdue: number | null;
  recent_on_time_rate: number | null;
  recent_sample: number;
  previous_on_time_rate: number | null;
  previous_sample: number;
  products: number;
  revenue: number;
  revenue_share: number | null;
  units_sold: number;
  stockout_days: number;
  positions: number;
  at_risk_positions: number;
  low_positions: number;
  flags: AttentionFlag[];
}

export interface SupplierNetwork {
  suppliers: number;
  flagged: number;
  orders: number;
  spend: number;
  on_time: number;
  sample_size: number;
  on_time_rate: number | null;
  overdue_orders: number;
  revenue: number;
  positions: number;
  at_risk_positions: number;
}

type Empty = { status: "empty"; freshness: DataFreshness; source: "csv" | "databricks"; reason: string };

export interface SupplierScorecard {
  status: "ok";
  freshness: DataFreshness;
  source: "csv" | "databricks";
  as_of: string;
  period: SalesPeriod | null;
  network: SupplierNetwork;
  total: number;
  items: SupplierScore[];
}

export type SupplierScorecardResponse = SupplierScorecard | Empty;

export interface SuppliedProduct {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  revenue: number;
  units_sold: number;
  stockout_days: number;
  stores: number;
  status_counts: Record<PositionStatus, number>;
  worst_status: PositionStatus | null;
  at_risk_stores: number;
  available: number;
  open_po_quantity: number;
}

export interface SupplierDetail {
  status: "ok";
  freshness: DataFreshness;
  source: "csv" | "databricks";
  as_of: string;
  period: SalesPeriod | null;
  supplier: {
    supplier_id: string;
    supplier_name: string;
    contact_email: string;
    stated_lead_time_days: number;
    minimum_order_quantity: number;
    stated_reliability: number;
  };
  scorecard: SupplierScore;
  monthly: Array<{ month: string; on_time: number; late: number; overdue: number; on_time_rate: number | null }>;
  late_distribution: Array<{ label: string; min_days: number; max_days: number | null; orders: number }>;
  products: SuppliedProduct[];
  overdue_orders: PurchaseOrder[];
  recent_orders: PurchaseOrder[];
}

export type SupplierDetailResponse = SupplierDetail | Empty;
